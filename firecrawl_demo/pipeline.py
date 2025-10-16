from __future__ import annotations

from collections.abc import Hashable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

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
from .models import EvidenceRecord, PipelineReport, SchoolRecord
from .research import ResearchAdapter, ResearchFinding, build_research_adapter
from .validation import DatasetValidator

_OFFICIAL_KEYWORDS = (".gov.za", "caa.co.za", ".ac.za", ".org.za", ".mil.za")


@dataclass
class Pipeline:
    research_adapter: ResearchAdapter = field(default_factory=build_research_adapter)
    validator: DatasetValidator = field(default_factory=DatasetValidator)
    evidence_sink: EvidenceSink = field(default_factory=NullEvidenceSink)

    def run_dataframe(self, frame: pd.DataFrame) -> PipelineReport:
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

        for position, (idx, row) in enumerate(working_frame.iterrows()):
            original_row = row.copy()
            record = SchoolRecord.from_dataframe_row(row)
            record.province = normalize_province(record.province)
            working_frame_cast.at[idx, "Province"] = record.province

            finding = self.research_adapter.lookup(record.name, record.province)
            updated = False
            sources = self._merge_sources(record, finding)

            if not record.website_url and finding.website_url:
                record.website_url = finding.website_url
                updated = True

            if not record.contact_person and finding.contact_person:
                record.contact_person = finding.contact_person
                updated = True

            phone_candidate = finding.contact_phone or record.contact_number
            normalized_phone, phone_issues = normalize_phone(phone_candidate)
            if normalized_phone and normalized_phone != record.contact_number:
                record.contact_number = normalized_phone
                updated = True

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

            has_named_contact = bool(record.contact_person)
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
                            finding, original_row, record
                        ),
                        confidence=confidence,
                    )
                )
            else:
                self._apply_record(working_frame, idx, record)

        if evidence_records:
            self.evidence_sink.record(evidence_records)

        metrics = {
            "rows_total": len(working_frame),
            "enriched_rows": enriched_rows,
            "verified_rows": int((working_frame["Status"] == "Verified").sum()),
            "issues_found": len(validation.issues),
        }
        return PipelineReport(
            refined_dataframe=working_frame,
            validation_report=validation,
            evidence_log=evidence_records,
            metrics=metrics,
        )

    def run_file(
        self, input_path: Path, output_path: Path | None = None
    ) -> PipelineReport:
        dataset = read_dataset(input_path)
        report = self.run_dataframe(dataset)
        if output_path:
            write_dataset(report.refined_dataframe, output_path)
        return report

    def available_tasks(self) -> dict[str, str]:
        return {
            "validate_dataset": "Validate the provided dataset",
            "enrich_dataset": "Validate and enrich the provided dataset",
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

    def _has_official_source(self, sources: Sequence[str]) -> bool:
        for source in sources:
            if any(keyword in source for keyword in _OFFICIAL_KEYWORDS):
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
    ) -> str:
        notes: list[str] = []
        if finding.notes:
            notes.append(finding.notes)

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
            return ""
        return "; ".join(notes)
