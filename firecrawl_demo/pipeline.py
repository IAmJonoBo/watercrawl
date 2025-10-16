from __future__ import annotations

import logging
from collections.abc import Hashable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import pandas as pd

from . import config
from .audit import EvidenceSink, NullEvidenceSink
from .compliance import (
    canonical_domain,
    confidence_for_status,
    determine_status,
    normalize_phone,
    normalize_province,
    validate_email,
)
from .excel import EXPECTED_COLUMNS, read_dataset, write_dataset
from .models import (
    EvidenceRecord,
    PipelineReport,
    SanityCheckFinding,
    SchoolRecord,
)
from .progress import NullPipelineProgressListener, PipelineProgressListener
from .research import ResearchAdapter, ResearchFinding, build_research_adapter
from .validation import DatasetValidator

_OFFICIAL_KEYWORDS = (".gov.za", "caa.co.za", ".ac.za", ".org.za", ".mil.za")
logger = logging.getLogger(__name__)


@dataclass
class Pipeline:
    research_adapter: ResearchAdapter = field(default_factory=build_research_adapter)
    validator: DatasetValidator = field(default_factory=DatasetValidator)
    evidence_sink: EvidenceSink = field(default_factory=NullEvidenceSink)
    _last_report: PipelineReport | None = field(default=None, init=False, repr=False)

    def run_dataframe(
        self,
        frame: pd.DataFrame,
        progress: PipelineProgressListener | None = None,
    ) -> PipelineReport:
        validation = self.validator.validate_dataframe(frame)
        missing_column_errors = [
            issue for issue in validation.issues if issue.code == "missing_column"
        ]
        if missing_column_errors:
            columns = ", ".join(issue.column or "" for issue in missing_column_errors)
            raise ValueError(f"Missing expected columns: {columns}")

        working_frame = frame.copy(deep=True)
        working_frame_cast = cast(Any, working_frame)
        evidence_records: list[EvidenceRecord] = []
        enriched_rows = 0
        adapter_failures = 0
        sanity_findings: list[SanityCheckFinding] = []
        row_number_lookup: dict[Hashable, int] = {}
        listener = progress or NullPipelineProgressListener()

        listener.on_start(len(working_frame))

        for position, (idx, row) in enumerate(working_frame.iterrows()):
            original_row = row.copy()
            record = SchoolRecord.from_dataframe_row(row)
            record.province = normalize_province(record.province)
            working_frame_cast.at[idx, "Province"] = record.province
            row_id = position + 2
            row_number_lookup[idx] = row_id

            try:
                finding = self.research_adapter.lookup(record.name, record.province)
            except Exception as exc:  # pragma: no cover - defensive guard
                adapter_failures += 1
                logger.warning(
                    "Research adapter failed for %s (%s): %s",
                    record.name,
                    record.province,
                    exc,
                    exc_info=exc,
                )
                listener.on_error(exc, position)
                finding = ResearchFinding(notes=f"Research adapter failed: {exc}")

            updated = False
            sources = self._merge_sources(record, finding)

            if not record.website_url and finding.website_url:
                record.website_url = finding.website_url
                updated = True

            if not record.contact_person and finding.contact_person:
                record.contact_person = finding.contact_person
                updated = True

            previous_phone = record.contact_number
            phone_candidate = finding.contact_phone or record.contact_number
            normalized_phone, phone_issues = normalize_phone(phone_candidate)
            if normalized_phone and normalized_phone != record.contact_number:
                record.contact_number = normalized_phone
                updated = True
            elif not normalized_phone and record.contact_number:
                record.contact_number = None
                updated = True

            previous_email = record.contact_email
            email_candidate = finding.contact_email or record.contact_email
            validated_email, email_issues = validate_email(
                email_candidate, canonical_domain(record.website_url)
            )
            filtered_email_issues = [
                issue for issue in email_issues if issue != "MX lookup unavailable"
            ]
            if validated_email and validated_email != record.contact_email:
                record.contact_email = validated_email
                updated = True
            elif not validated_email and record.contact_email:
                record.contact_email = None
                updated = True

            has_named_contact = bool(record.contact_person)
            has_official_source = self._has_official_domain(sources)
            evidence_ok = self._has_official_source(sources)
            status = determine_status(
                bool(record.website_url),
                has_named_contact,
                phone_issues,
                filtered_email_issues,
                evidence_ok,
            )
            if status != record.status:
                record.status = status
                updated = True

            (
                sanity_updated,
                sanity_notes,
                row_findings,
                sources,
                cleared_columns,
            ) = self._run_sanity_checks(
                record=record,
                row_id=row_id,
                sources=sources,
                phone_issues=phone_issues,
                email_issues=filtered_email_issues,
                previous_phone=previous_phone,
                previous_email=previous_email,
            )
            if sanity_updated:
                updated = True
            if row_findings:
                sanity_findings.extend(row_findings)
            for column in cleared_columns:
                working_frame_cast.at[idx, column] = ""

            if updated:
                enriched_rows += 1
                self._apply_record(working_frame, idx, record)
                confidence = finding.confidence or confidence_for_status(
                    record.status,
                    len(phone_issues) + len(filtered_email_issues),
                )
                evidence_records.append(
                    EvidenceRecord(
                        row_id=position + 2,
                        organisation=record.name,
                        changes=self._describe_changes(original_row, record),
                        sources=sources,
                        notes=self._compose_evidence_notes(
                            finding,
                            original_row,
                            record,
                            sources=sources,
                            has_official_source=has_official_source,
                            sanity_notes=sanity_notes,
                        ),
                        confidence=confidence,
                    )
                )
            else:
                self._apply_record(working_frame, idx, record)

            listener.on_row_processed(position, updated, record)

        if evidence_records:
            self.evidence_sink.record(evidence_records)

        sanity_findings.extend(
            self._detect_duplicate_schools(working_frame, row_number_lookup)
        )

        metrics = {
            "rows_total": len(working_frame),
            "enriched_rows": enriched_rows,
            "verified_rows": int((working_frame["Status"] == "Verified").sum()),
            "issues_found": len(validation.issues),
            "adapter_failures": adapter_failures,
            "sanity_issues": len(sanity_findings),
        }
        report = PipelineReport(
            refined_dataframe=working_frame,
            validation_report=validation,
            evidence_log=evidence_records,
            metrics=metrics,
            sanity_findings=sanity_findings,
        )
        self._last_report = report
        listener.on_complete(metrics)
        return report

    def run_file(
        self,
        input_path: Path,
        output_path: Path | None = None,
        *,
        progress: PipelineProgressListener | None = None,
    ) -> PipelineReport:
        dataset = read_dataset(input_path)
        report = self.run_dataframe(dataset, progress=progress)
        if output_path:
            write_dataset(report.refined_dataframe, output_path)
        return report

    def available_tasks(self) -> dict[str, str]:
        return {
            "validate_dataset": "Validate the provided dataset",
            "enrich_dataset": "Validate and enrich the provided dataset",
            "summarize_last_run": "Summarise metrics from the most recent pipeline execution",
            "list_sanity_issues": "List outstanding sanity check findings from the latest run",
        }

    def run_task(self, task: str, payload: dict[str, object]) -> dict[str, object]:
        if task == "validate_dataset":
            frame = self._frame_from_payload(payload)
            validation_report = self.validator.validate_dataframe(frame)
            return {
                "status": "ok",
                "rows": validation_report.rows,
                "issues": [issue.__dict__ for issue in validation_report.issues],
            }
        if task == "enrich_dataset":
            frame = self._frame_from_payload(payload)
            pipeline_report = self.run_dataframe(frame)
            return {
                "status": "ok",
                "rows_enriched": pipeline_report.metrics["enriched_rows"],
                "metrics": pipeline_report.metrics,
            }
        if task == "summarize_last_run":
            return self._summarize_last_run()
        if task == "list_sanity_issues":
            return self._list_sanity_issues()
        raise KeyError(task)

    def _frame_from_payload(self, payload: dict[str, object]) -> pd.DataFrame:
        if "path" in payload:
            return read_dataset(Path(str(payload["path"])))
        if "rows" in payload:
            rows_obj = payload["rows"] or []
            if not isinstance(rows_obj, list):
                raise ValueError("Payload 'rows' must be a list of mappings")
            return pd.DataFrame(list(rows_obj), columns=list(EXPECTED_COLUMNS))
        raise ValueError("Payload must include 'path' or 'rows'")

    def _apply_record(
        self, frame: pd.DataFrame, index: Hashable, record: SchoolRecord
    ) -> None:
        frame_cast = cast(Any, frame)
        for column, value in record.as_dict().items():
            if value is not None:
                frame_cast.at[index, column] = value

    def _merge_sources(
        self, record: SchoolRecord, finding: ResearchFinding
    ) -> list[str]:
        sources: list[str] = []
        if record.website_url:
            sources.append(record.website_url)
        if finding.website_url and finding.website_url not in sources:
            sources.append(finding.website_url)
        for source in finding.sources:
            if source not in sources:
                sources.append(source)
        if not sources:
            sources.append("internal://record")
        return sources

    def _has_official_domain(self, sources: Sequence[str]) -> bool:
        for source in sources:
            candidate = source.lower()
            if any(keyword in candidate for keyword in _OFFICIAL_KEYWORDS):
                return True
        return False

    def _has_official_source(self, sources: Sequence[str]) -> bool:
        if self._has_official_domain(sources):
            return True
        # If no explicit official keyword but there are >=2 sources, consider the first as quasi-official
        return len(sources) >= 2

    def _describe_changes(self, original_row: pd.Series, record: SchoolRecord) -> str:
        changes: list[str] = []
        mapping = {
            "Website URL": record.website_url,
            "Contact Person": record.contact_person,
            "Contact Number": record.contact_number,
            "Contact Email Address": record.contact_email,
            "Status": record.status,
            "Province": record.province,
        }
        for column, new_value in mapping.items():
            original_value = str(original_row.get(column, "") or "").strip()
            if new_value and original_value != new_value:
                changes.append(f"{column} -> {new_value}")
        return "; ".join(changes) or "No changes"

    def _compose_evidence_notes(
        self,
        finding: ResearchFinding,
        original_row: pd.Series,
        record: SchoolRecord,
        *,
        sources: Sequence[str],
        has_official_source: bool,
        sanity_notes: Sequence[str] | None = None,
    ) -> str:
        notes: list[str] = []
        if finding.notes:
            notes.append(finding.notes)

        if sanity_notes:
            for note in sanity_notes:
                if note and note not in notes:
                    notes.append(note)

        if config.FEATURE_FLAGS.investigate_rebrands:
            for note in finding.investigation_notes:
                if note and note not in notes:
                    notes.append(note)

            prior_domain = canonical_domain(str(original_row.get("Website URL", "")))
            current_domain = canonical_domain(record.website_url)
            if prior_domain and current_domain and prior_domain != current_domain:
                rename_note = f"Website changed from {prior_domain} to {current_domain}; investigate potential rename or ownership change."
                if rename_note not in notes:
                    notes.append(rename_note)

            if finding.alternate_names:
                alias_block = ", ".join(sorted(set(finding.alternate_names)))
                alias_note = f"Known aliases: {alias_block}"
                if alias_note not in notes:
                    notes.append(alias_note)

            if finding.physical_address:
                address_note = (
                    f"Latest address intelligence: {finding.physical_address}"
                )
                if address_note not in notes:
                    notes.append(address_note)

        if not notes:
            notes_text = ""
        else:
            notes_text = "; ".join(notes)

        remediation_reasons: list[str] = []
        if len(sources) < 2:
            remediation_reasons.append("add a second independent source")
        if not has_official_source:
            remediation_reasons.append(
                "confirm an official (.gov.za/.caa.co.za/.ac.za/.org.za/.mil.za) source"
            )
        if remediation_reasons:
            shortfall_note = "Evidence shortfall: " + "; ".join(remediation_reasons)
            if not shortfall_note.endswith("."):
                shortfall_note += "."
            if notes_text:
                notes_text = "; ".join(filter(None, [notes_text, shortfall_note]))
            else:
                notes_text = shortfall_note

        return notes_text

    def _run_sanity_checks(
        self,
        *,
        record: SchoolRecord,
        row_id: int,
        sources: list[str],
        phone_issues: Sequence[str],
        email_issues: Sequence[str],
        previous_phone: str | None,
        previous_email: str | None,
    ) -> tuple[bool, list[str], list[SanityCheckFinding], list[str], list[str]]:
        updated = False
        notes: list[str] = []
        findings: list[SanityCheckFinding] = []
        normalized_sources = list(sources)
        cleared_columns: list[str] = []

        if record.website_url:
            parsed = urlparse(record.website_url)
            if not parsed.scheme:
                original_url = record.website_url
                normalized_url = f"https://{original_url.lstrip('/')}"
                record.website_url = normalized_url
                normalized_sources = [
                    normalized_url if source == original_url else source
                    for source in normalized_sources
                ]
                updated = True
                notes.append("Auto-normalised website URL to include https scheme.")
                findings.append(
                    SanityCheckFinding(
                        row_id=row_id,
                        organisation=record.name,
                        issue="website_url_missing_scheme",
                        remediation="Added an https:// prefix to the website URL for consistency.",
                    )
                )

        if previous_phone and record.contact_number is None and phone_issues:
            notes.append(
                "Removed invalid contact number after it failed +27 E.164 validation."
            )
            findings.append(
                SanityCheckFinding(
                    row_id=row_id,
                    organisation=record.name,
                    issue="contact_number_invalid",
                    remediation="Capture a verified +27-format contact number before publishing.",
                )
            )
            updated = True
            cleared_columns.append("Contact Number")

        if previous_email and record.contact_email is None and email_issues:
            notes.append("Removed invalid contact email after validation failures.")
            findings.append(
                SanityCheckFinding(
                    row_id=row_id,
                    organisation=record.name,
                    issue="contact_email_invalid",
                    remediation="Source a named contact email on the official organisation domain.",
                )
            )
            updated = True
            cleared_columns.append("Contact Email Address")

        if record.province == "Unknown":
            findings.append(
                SanityCheckFinding(
                    row_id=row_id,
                    organisation=record.name,
                    issue="province_unknown",
                    remediation=(
                        "Confirm the organisation's South African province and update the dataset."
                    ),
                )
            )
            notes.append("Province remains Unknown pending analyst confirmation.")

        return updated, notes, findings, normalized_sources, cleared_columns

    def _detect_duplicate_schools(
        self, frame: pd.DataFrame, row_lookup: dict[Hashable, int]
    ) -> list[SanityCheckFinding]:
        if "Name of Organisation" not in frame:
            return []
        names = frame["Name of Organisation"].fillna("").astype(str)
        normalized = names.str.strip().str.lower()
        duplicate_mask = normalized.duplicated(keep=False)
        findings: list[SanityCheckFinding] = []
        if not duplicate_mask.any():
            return findings

        for idx in frame.index[duplicate_mask]:
            row_id = row_lookup.get(idx, 0)
            organisation = names.loc[idx].strip()
            findings.append(
                SanityCheckFinding(
                    row_id=row_id,
                    organisation=organisation,
                    issue="duplicate_organisation",
                    remediation="Deduplicate or merge duplicate organisation rows before publishing.",
                )
            )
        return findings

    def _summarize_last_run(self) -> dict[str, object]:
        if self._last_report is None:
            return {
                "status": "empty",
                "message": "No pipeline runs have been executed yet.",
            }
        return {
            "status": "ok",
            "metrics": dict(self._last_report.metrics),
            "sanity_issue_count": len(self._last_report.sanity_findings),
        }

    def _list_sanity_issues(self) -> dict[str, object]:
        if self._last_report is None:
            return {"status": "empty", "findings": []}
        return {
            "status": "ok",
            "findings": [
                finding.as_dict() for finding in self._last_report.sanity_findings
            ],
        }
