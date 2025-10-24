from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Iterable

try:
    import pandas as pd

    _PANDAS_AVAILABLE = True
except ImportError:
    pd = None  # type: ignore
    _PANDAS_AVAILABLE = False

from watercrawl.core import config
from watercrawl.domain import relationships
from watercrawl.domain.compliance import canonical_domain

from .models import EXPECTED_COLUMNS, ValidationIssue, ValidationReport


_PHONE_RE = re.compile(config.PHONE_E164_REGEX)
_EMAIL_RE = re.compile(config.EMAIL_REGEX)


def _clean_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


@dataclass(frozen=True)
class ContactRow:
    row_number: int
    organisation: str
    canonical_org_id: str
    website_domain: str | None
    person: str | None
    person_normalized: str | None
    canonical_person_id: str | None
    role: str | None
    role_normalized: str | None
    email: str | None
    normalized_email: str | None
    canonical_email_id: str | None
    phone: str | None
    normalized_phone: str | None


ContactIndex = dict[str, list[ContactRow]]
Validator = Callable[[Any, ContactIndex], Iterable[ValidationIssue]]


@dataclass(frozen=True)
class DatasetValidator:
    """Validates input datasets for mandatory columns and value constraints."""

    validators: tuple[Validator, ...] | None = None

    def __post_init__(self) -> None:
        if self.validators is None:
            object.__setattr__(
                self,
                "validators",
                (
                    self._validate_provinces,
                    self._validate_statuses,
                    self._validate_contact_hygiene,
                    self._validate_duplicates,
                    self._validate_multi_contact_conflicts,
                ),
            )

    def validate_dataframe(self, frame: Any) -> ValidationReport:
        issues: list[ValidationIssue] = []
        frame_columns = getattr(frame, "columns", [])
        frame_attrs = getattr(frame, "attrs", {})
        missing_from_attrs = {
            str(column)
            for column in frame_attrs.get("missing_columns", ())
            if column is not None
        }
        missing_from_structure = {
            col for col in EXPECTED_COLUMNS if col not in frame_columns
        }
        missing_columns = sorted(missing_from_attrs | missing_from_structure)
        for column in missing_columns:
            issues.append(
                ValidationIssue(
                    code="missing_column",
                    message=f"Missing expected column: {column}",
                    column=column,
                )
            )

        if missing_columns:
            return ValidationReport(issues=issues, rows=len(frame))

        contact_index = self._build_contact_index(frame)
        for validator in self.validators or ():
            issues.extend(validator(frame, contact_index))
        return ValidationReport(issues=list(issues), rows=len(frame))

    def _validate_provinces(
        self, frame: Any, _: ContactIndex
    ) -> Iterable[ValidationIssue]:
        allowed = {province.lower(): province for province in config.PROVINCES}
        province_series = frame["Province"].fillna("")
        issues: list[ValidationIssue] = []
        for offset, (_, raw_value) in enumerate(province_series.items(), start=2):
            cleaned = str(raw_value).strip().lower()
            if cleaned and cleaned in allowed:
                continue
            if cleaned == "unknown" or not cleaned:
                continue
            issues.append(
                ValidationIssue(
                    code="invalid_province",
                    message=f"Province '{raw_value}' is not recognised",
                    row=offset,
                    column="Province",
                )
            )
        return issues

    def _validate_statuses(
        self, frame: Any, _: ContactIndex
    ) -> Iterable[ValidationIssue]:
        allowed = {status.lower() for status in config.CANONICAL_STATUSES}
        issues: list[ValidationIssue] = []
        for offset, (_, raw_value) in enumerate(
            frame["Status"].fillna("").items(), start=2
        ):
            cleaned = str(raw_value).strip().lower()
            if not cleaned:
                issues.append(
                    ValidationIssue(
                        code="missing_status",
                        message="Status is empty",
                        row=offset,
                        column="Status",
                    )
                )
                continue
            if cleaned not in allowed:
                issues.append(
                    ValidationIssue(
                        code="invalid_status",
                        message=f"Status '{raw_value}' is not permitted",
                        row=offset,
                        column="Status",
                    )
                )
        return issues

    def _validate_contact_hygiene(
        self, _: Any, contact_index: ContactIndex
    ) -> Iterable[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for contacts in contact_index.values():
            for contact in contacts:
                if not contact.phone:
                    issues.append(
                        ValidationIssue(
                            code="missing_phone",
                            message="Contact number is missing",
                            row=contact.row_number,
                            column="Contact Number",
                        )
                    )
                else:
                    if not contact.normalized_phone or not _PHONE_RE.fullmatch(contact.normalized_phone):
                        issues.append(
                            ValidationIssue(
                                code="invalid_phone_format",
                                message="Contact number is not in the required E.164 format",
                                row=contact.row_number,
                                column="Contact Number",
                            )
                        )

                if not contact.email:
                    issues.append(
                        ValidationIssue(
                            code="missing_email",
                            message="Contact email address is missing",
                            row=contact.row_number,
                            column="Contact Email Address",
                        )
                    )
                    continue

                if not _EMAIL_RE.fullmatch(contact.email):
                    issues.append(
                        ValidationIssue(
                            code="invalid_email_format",
                            message="Contact email address is invalid",
                            row=contact.row_number,
                            column="Contact Email Address",
                        )
                    )
                    continue

                if (
                    config.EMAIL_REQUIRE_DOMAIN_MATCH
                    and contact.website_domain
                    and contact.normalized_email
                ):
                    email_domain = contact.normalized_email.split("@", 1)[-1]
                    if email_domain != contact.website_domain.lower() and not email_domain.endswith('.' + contact.website_domain.lower()):
                        issues.append(
                            ValidationIssue(
                                code="email_domain_mismatch",
                                message=(
                                    "Contact email domain does not match the organisation website"
                                ),
                                row=contact.row_number,
                                column="Contact Email Address",
                            )
                        )
        return issues

    def _validate_duplicates(
        self, _: Any, contact_index: ContactIndex
    ) -> Iterable[ValidationIssue]:
        issues: list[ValidationIssue] = []
        seen_org: dict[str, ContactRow] = {}
        seen_contact_edges: dict[tuple[str, str], ContactRow] = {}
        seen_emails: dict[str, ContactRow] = {}

        for org_id, contacts in contact_index.items():
            ordered = sorted(contacts, key=lambda entry: entry.row_number)
            first_contact = seen_org.get(org_id)
            if first_contact:
                for entry in ordered:
                    if entry.row_number != first_contact.row_number:
                        issues.append(
                            ValidationIssue(
                                code="duplicate_organisation",
                                message=(
                                    f"Organisation '{entry.organisation}' appears multiple times"
                                ),
                                row=entry.row_number,
                                column="Name of Organisation",
                            )
                        )
            else:
                seen_org[org_id] = ordered[0]

            for entry in ordered:
                if entry.canonical_person_id:
                    edge_key = (entry.canonical_person_id, org_id)
                    existing = seen_contact_edges.get(edge_key)
                    if existing and existing.row_number != entry.row_number:
                        issues.append(
                            ValidationIssue(
                                code="duplicate_contact",
                                message=(
                                    f"Contact '{entry.person}' is duplicated for the organisation"
                                ),
                                row=entry.row_number,
                                column="Contact Person",
                            )
                        )
                    else:
                        seen_contact_edges[edge_key] = entry

                if entry.canonical_email_id:
                    existing_email = seen_emails.get(entry.canonical_email_id)
                    if existing_email and existing_email.canonical_org_id != org_id:
                        issues.append(
                            ValidationIssue(
                                code="email_reused_across_organisations",
                                message=(
                                    "Contact email address is reused across multiple organisations"
                                ),
                                row=entry.row_number,
                                column="Contact Email Address",
                            )
                        )
                    elif existing_email and existing_email.row_number != entry.row_number:
                        issues.append(
                            ValidationIssue(
                                code="duplicate_contact_email",
                                message="Contact email address is duplicated",
                                row=entry.row_number,
                                column="Contact Email Address",
                            )
                        )
                    else:
                        seen_emails[entry.canonical_email_id] = entry
        return issues

    def _validate_multi_contact_conflicts(
        self, _: Any, contact_index: ContactIndex
    ) -> Iterable[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for contacts in contact_index.values():
            if len(contacts) <= 1:
                continue

            ordered = sorted(contacts, key=lambda entry: entry.row_number)
            reference = ordered[0]
            people = {
                entry.person_normalized
                for entry in ordered
                if entry.person_normalized is not None
            }
            emails = {
                entry.normalized_email
                for entry in ordered
                if entry.normalized_email is not None
            }
            roles = {
                entry.role_normalized
                for entry in ordered
                if entry.role_normalized is not None
            }

            if len(people) > 1:
                display_names = sorted(
                    {entry.person for entry in ordered if entry.person}
                )
                issues.append(
                    ValidationIssue(
                        code="multiple_contacts",
                        message=(
                            f"Organisation '{reference.organisation}' lists multiple contacts:"
                            f" {', '.join(display_names)}"
                        ),
                        row=reference.row_number,
                        column="Contact Person",
                    )
                )

            if len(emails) > 1:
                display_emails = sorted(
                    {entry.email for entry in ordered if entry.email}
                )
                issues.append(
                    ValidationIssue(
                        code="conflicting_contact_emails",
                        message=(
                            "Organisation has multiple different contact email addresses: "
                            + ", ".join(display_emails)
                        ),
                        row=reference.row_number,
                        column="Contact Email Address",
                    )
                )

            if len(roles) > 1:
                display_roles = sorted(
                    {entry.role for entry in ordered if entry.role}
                )
                issues.append(
                    ValidationIssue(
                        code="conflicting_contact_roles",
                        message=(
                            "Organisation has conflicting contact roles: "
                            + ", ".join(display_roles)
                        ),
                        row=reference.row_number,
                        column="Contact Person",
                    )
                )
        return issues

    def _build_contact_index(self, frame: Any) -> ContactIndex:
        contact_index: ContactIndex = defaultdict(list)
        role_column = self._contact_role_column(frame)

        if _PANDAS_AVAILABLE and hasattr(frame, "iterrows"):
            row_iterable = (
                (offset, data)
                for offset, (_, data) in enumerate(frame.iterrows(), start=2)
            )
        else:
            row_iterable = ((offset, data) for offset, data in enumerate(frame, start=2))

        for offset, data in row_iterable:

            organisation = _clean_value(data.get("Name of Organisation")) or ""
            org_identifier = organisation or f"row-{offset}"
            canonical_org_id = relationships.canonical_id("organisation", org_identifier)

            website = _clean_value(data.get("Website URL"))
            website_domain = canonical_domain(website) if website else None
            person = _clean_value(data.get("Contact Person"))
            role = _clean_value(data.get(role_column)) if role_column else None
            email = _clean_value(data.get("Contact Email Address"))
            phone = _clean_value(data.get("Contact Number"))

            normalized_email = email.lower() if email else None
            normalized_phone = re.sub(r"[\s().-]", "", phone) if phone else None
            canonical_person_id = (
                relationships.canonical_id("person", person)
                if person is not None
                else None
            )
            canonical_email_id = (
                relationships.canonical_id("email", normalized_email)
                if normalized_email
                else None
            )

            contact_index[canonical_org_id].append(
                ContactRow(
                    row_number=offset,
                    organisation=organisation,
                    canonical_org_id=canonical_org_id,
                    website_domain=website_domain,
                    person=person,
                    person_normalized=person.casefold() if person else None,
                    canonical_person_id=canonical_person_id,
                    role=role,
                    role_normalized=role.casefold() if role else None,
                    email=email,
                    normalized_email=normalized_email,
                    canonical_email_id=canonical_email_id,
                    phone=phone,
                    normalized_phone=normalized_phone,
                )
            )

        return contact_index

    def _contact_role_column(self, frame: Any) -> str | None:
        columns = getattr(frame, "columns", [])
        for candidate in ("Contact Role", "Role"):
            if candidate in columns:
                return candidate
        return None
