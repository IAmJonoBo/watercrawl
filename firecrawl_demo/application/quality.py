"""Quality gate that defends against hallucinated or low-trust enrichments."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from firecrawl_demo.domain.compliance import canonical_domain
from firecrawl_demo.domain.models import SchoolRecord
from firecrawl_demo.integrations.adapters.research import ResearchFinding


@dataclass(frozen=True)
class QualityFinding:
    code: str
    severity: Literal["block", "warn"]
    message: str
    remediation: str


@dataclass(frozen=True)
class QualityGateDecision:
    accepted: bool
    findings: list[QualityFinding]
    fallback_record: SchoolRecord | None = None

    @property
    def blocking_findings(self) -> list[QualityFinding]:
        return [finding for finding in self.findings if finding.severity == "block"]


class QualityGate:
    """Evaluates proposed enrichment updates before they touch curated data."""

    def __init__(
        self,
        *,
        min_confidence: int = 70,
        require_official_source: bool = True,
    ) -> None:
        self.min_confidence = min_confidence
        self.require_official_source = require_official_source

    def evaluate(
        self,
        *,
        original: SchoolRecord,
        proposed: SchoolRecord,
        finding: ResearchFinding,
        changed_columns: Mapping[str, tuple[str | None, str | None]],
        phone_issues: Sequence[str],
        email_issues: Sequence[str],
        total_source_count: int,
        fresh_source_count: int,
        official_source_count: int,
        official_fresh_source_count: int,
    ) -> QualityGateDecision:
        changes = dict(changed_columns)
        if not changes:
            return QualityGateDecision(True, [])

        findings: list[QualityFinding] = []
        blocking = False
        high_risk_columns = {
            "Website URL",
            "Contact Person",
            "Contact Number",
            "Contact Email Address",
        }

        def _normalize_url_text(url: str | None) -> str:
            if not url:
                return ""
            domain = canonical_domain(url)
            if domain:
                return domain
            text = url.strip().lower()
            if text.startswith("http://"):
                text = text[7:]
            elif text.startswith("https://"):
                text = text[8:]
            if text.startswith("www."):
                text = text[4:]
            return text

        def _is_meaningful(column: str) -> bool:
            if column == "Website URL":
                return _normalize_url_text(original.website_url) != _normalize_url_text(
                    proposed.website_url
                )
            if column in {"Contact Person", "Contact Number", "Contact Email Address"}:
                return bool(changes[column][1])
            return True

        meaningful_high_risk = {
            column
            for column in changes
            if column in high_risk_columns and _is_meaningful(column)
        }

        if meaningful_high_risk:
            high_risk_changed = any(
                column in meaningful_high_risk and (values[1] or "")
                for column, values in changes.items()
            )
            if high_risk_changed and total_source_count < 2:
                blocking = True
                findings.append(
                    QualityFinding(
                        code="insufficient_evidence",
                        severity="block",
                        message=(
                            "Proposed enrichment needs at least two independent sources before "
                            "updating high-risk fields."
                        ),
                        remediation=(
                            "Collect corroborating evidence from at least two independent sources "
                            "before retrying the enrichment."
                        ),
                    )
                )
            if high_risk_changed and fresh_source_count == 0:
                blocking = True
                findings.append(
                    QualityFinding(
                        code="no_fresh_evidence",
                        severity="block",
                        message=(
                            "Proposed enrichment only references existing dataset sources and "
                            "introduces no fresh evidence."
                        ),
                        remediation=(
                            "Capture new, independent evidence that directly supports the "
                            "proposed changes before accepting them."
                        ),
                    )
                )
            if self.require_official_source and high_risk_changed:
                if official_source_count == 0:
                    blocking = True
                    findings.append(
                        QualityFinding(
                            code="missing_official_source",
                            severity="block",
                            message=(
                                "No official or regulator-backed source corroborates the "
                                "proposed enrichment."
                            ),
                            remediation=(
                                "Identify an official (.gov.za/.caa.co.za/.ac.za/.org.za/.mil.za) "
                                "source that validates the change before publishing."
                            ),
                        )
                    )
                elif official_fresh_source_count == 0:
                    blocking = True
                    findings.append(
                        QualityFinding(
                            code="official_source_not_fresh",
                            severity="block",
                            message=(
                                "Official corroboration relies on legacy dataset evidence rather "
                                "than fresh supporting sources."
                            ),
                            remediation=(
                                "Gather a new official or regulator-backed source that confirms "
                                "the proposed changes."
                            ),
                        )
                    )

        effective_confidence = finding.confidence
        if (
            effective_confidence is not None
            and effective_confidence < self.min_confidence
        ):
            if any(
                column in meaningful_high_risk and (changes[column][1] or "")
                for column in changes
            ):
                blocking = True
                findings.append(
                    QualityFinding(
                        code="low_confidence",
                        severity="block",
                        message=(
                            "Adapter confidence "
                            f"{effective_confidence} is below the {self.min_confidence} "
                            "threshold for contact/website changes."
                        ),
                        remediation=(
                            "Corroborate the finding with authoritative sources or raise the "
                            "adapter confidence before retrying."
                        ),
                    )
                )

        if phone_issues and proposed.contact_number and "Contact Number" in changes:
            blocking = True
            findings.append(
                QualityFinding(
                    code="invalid_phone",
                    severity="block",
                    message="Proposed contact number failed +27 E.164 validation.",
                    remediation="Capture a callable +27 number or omit the phone field until verified.",
                )
            )

        if (
            email_issues
            and proposed.contact_email
            and "Contact Email Address" in changes
        ):
            blocking = True
            issues_text = "; ".join(sorted(set(email_issues)))
            findings.append(
                QualityFinding(
                    code="invalid_email",
                    severity="block",
                    message=f"Proposed contact email failed validation: {issues_text}.",
                    remediation=(
                        "Provide a domain-aligned email with MX records or leave the field blank "
                        "until confirmed."
                    ),
                )
            )

        if "Website URL" in changes:
            proposed_domain = canonical_domain(proposed.website_url)
            original_domain = canonical_domain(original.website_url)
            if (
                proposed_domain
                and original_domain
                and proposed_domain != original_domain
            ):
                if official_source_count == 0:
                    blocking = True
                    findings.append(
                        QualityFinding(
                            code="website_domain_unverified",
                            severity="block",
                            message=(
                                "Website domain changed without corroborating official sources, "
                                f"from {original_domain or 'unknown'} to {proposed_domain}."
                            ),
                            remediation=(
                                "Confirm the new domain via regulator or official announcements "
                                "before applying the change."
                            ),
                        )
                    )

        if not blocking:
            return QualityGateDecision(True, findings)

        fallback = replace(original)
        if original.status != "Needs Review":
            fallback = replace(fallback, status="Needs Review")

        return QualityGateDecision(False, findings, fallback)
