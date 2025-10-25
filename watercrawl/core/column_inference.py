"""Column inference heuristics for dataset alignment."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable, Iterable, Mapping, Sequence

import pandas as pd

from .profiles import ColumnDescriptor

DetectionHook = Callable[
    [str, Sequence[str], ColumnDescriptor], "DetectionSignal | None"
]


@dataclass(frozen=True)
class DetectionSignal:
    """Structured signal produced by a detection hook."""

    score: float
    reason: str


@dataclass(frozen=True)
class ColumnMatch:
    """Represent the strongest inferred mapping for a single column."""

    source: str
    canonical: str
    score: float
    matched_label: str
    reasons: tuple[str, ...]
    sample_size: int

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "canonical": self.canonical,
            "score": round(self.score, 4),
            "matched_label": self.matched_label,
            "reasons": list(self.reasons),
            "sample_size": self.sample_size,
        }


@dataclass(frozen=True)
class ColumnInferenceResult:
    """Outcome of running the column inference engine on a dataframe."""

    matches: tuple[ColumnMatch, ...]
    unmatched_sources: tuple[str, ...]
    missing_targets: tuple[str, ...]
    rename_map: Mapping[str, str]

    def to_dict(self) -> dict[str, object]:
        return {
            "matches": [match.to_dict() for match in self.matches],
            "unmatched_sources": list(self.unmatched_sources),
            "missing_targets": list(self.missing_targets),
            "rename_map": dict(self.rename_map),
        }

    @classmethod
    def merge(
        cls, results: Iterable["ColumnInferenceResult"]
    ) -> "ColumnInferenceResult":
        matches_by_source: dict[str, ColumnMatch] = {}
        unmatched: set[str] = set()
        missing: set[str] = set()

        for result in results:
            unmatched.update(result.unmatched_sources)
            missing.update(result.missing_targets)
            for match in result.matches:
                existing = matches_by_source.get(match.source)
                if existing is None or match.score > existing.score:
                    matches_by_source[match.source] = match

        matched_sources = set(matches_by_source)
        unmatched = {source for source in unmatched if source not in matched_sources}
        matched_targets = {match.canonical for match in matches_by_source.values()}
        missing = {target for target in missing if target not in matched_targets}

        sorted_matches = tuple(
            sorted(
                matches_by_source.values(),
                key=lambda item: (item.canonical, item.source),
            )
        )
        rename_map = {
            match.source: match.canonical
            for match in sorted_matches
            if match.source != match.canonical
        }
        return cls(
            matches=sorted_matches,
            unmatched_sources=tuple(sorted(unmatched)),
            missing_targets=tuple(sorted(missing)),
            rename_map=rename_map,
        )


class ColumnInferenceEngine:
    """Score candidate matches between dataframe columns and descriptors."""

    _MIN_ASSIGNMENT_SCORE = 0.5
    _MIN_CANDIDATE_SCORE = 0.35

    def __init__(
        self,
        descriptors: Sequence[ColumnDescriptor],
        *,
        detection_hooks: Mapping[str, DetectionHook] | None = None,
    ) -> None:
        self._descriptors = list(descriptors)
        self._hooks = dict(_DEFAULT_HOOKS)
        if detection_hooks:
            self._hooks.update(detection_hooks)

    def infer(self, frame: pd.DataFrame) -> ColumnInferenceResult:
        candidate_matches: dict[str, list[ColumnMatch]] = {}

        for column in frame.columns:
            samples = _sample_values(frame[column])
            matches_for_column: list[ColumnMatch] = []
            for descriptor in self._descriptors:
                match = self._score_descriptor(column, descriptor, samples)
                if match is not None:
                    matches_for_column.append(match)
            if matches_for_column:
                matches_for_column.sort(key=lambda match: match.score, reverse=True)
                candidate_matches[column] = matches_for_column

        assigned_sources: set[str] = set()
        assigned_targets: set[str] = set()
        chosen_matches: list[ColumnMatch] = []

        all_candidates = sorted(
            (match for matches in candidate_matches.values() for match in matches),
            key=lambda match: match.score,
            reverse=True,
        )

        for candidate in all_candidates:
            if candidate.score < self._MIN_ASSIGNMENT_SCORE:
                continue
            if candidate.source in assigned_sources:
                continue
            if candidate.canonical in assigned_targets:
                continue
            assigned_sources.add(candidate.source)
            assigned_targets.add(candidate.canonical)
            chosen_matches.append(candidate)

        unmatched_sources = [
            column for column in frame.columns if column not in assigned_sources
        ]
        missing_targets = [
            descriptor.name
            for descriptor in self._descriptors
            if descriptor.name not in assigned_targets
        ]

        rename_map = {
            match.source: match.canonical
            for match in chosen_matches
            if match.source != match.canonical
        }

        return ColumnInferenceResult(
            matches=tuple(
                sorted(chosen_matches, key=lambda item: (item.canonical, item.source))
            ),
            unmatched_sources=tuple(sorted(unmatched_sources)),
            missing_targets=tuple(sorted(missing_targets)),
            rename_map=rename_map,
        )

    def _score_descriptor(
        self,
        column_name: str,
        descriptor: ColumnDescriptor,
        sample_values: Sequence[str],
    ) -> ColumnMatch | None:
        best_score = 0.0
        best_label = descriptor.name
        reasons: list[str] = []

        for label in descriptor.candidate_labels():
            score, reason = _score_label(column_name, label, descriptor.name)
            if score > best_score:
                best_score = score
                best_label = label
                reasons = [reason] if reason else []
            elif score and reason and reason not in reasons:
                reasons.append(reason)

        hook_names = list(descriptor.detection_hooks)
        if descriptor.allowed_values and "allowed_values" not in hook_names:
            hook_names.append("allowed_values")

        for hook_name in hook_names:
            hook = self._hooks.get(hook_name)
            if hook is None:
                continue
            signal = hook(column_name, sample_values, descriptor)
            if signal is None:
                continue
            reasons.append(signal.reason)
            best_score = max(best_score, min(1.0, signal.score))

        if best_score < self._MIN_CANDIDATE_SCORE:
            return None
        deduped_reasons = []
        for reason in reasons:
            if reason and reason not in deduped_reasons:
                deduped_reasons.append(reason)
        return ColumnMatch(
            source=column_name,
            canonical=descriptor.name,
            score=min(best_score, 1.0),
            matched_label=best_label,
            reasons=tuple(deduped_reasons),
            sample_size=len(sample_values),
        )


def _sample_values(series: pd.Series, limit: int = 50) -> list[str]:
    values: list[str] = []
    for value in series.dropna().tolist():
        text = str(value).strip()
        if not text:
            continue
        values.append(text)
        if len(values) >= limit:
            break
    return values


def _normalize(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def _token_overlap_score(lhs: str, rhs: str) -> float:
    lhs_tokens = set(_WORD_RE.findall(lhs.lower()))
    rhs_tokens = set(_WORD_RE.findall(rhs.lower()))
    if not lhs_tokens or not rhs_tokens:
        return 0.0
    intersection = lhs_tokens & rhs_tokens
    if not intersection:
        return 0.0
    coverage = len(intersection) / len(rhs_tokens)
    if coverage < 0.5:
        return 0.0
    return 0.6 + 0.4 * coverage


def _score_label(
    column_name: str, candidate_label: str, canonical_name: str
) -> tuple[float, str | None]:
    normalized_column = _normalize(column_name)
    normalized_label = _normalize(candidate_label)
    if not normalized_column or not normalized_label:
        return 0.0, None
    if normalized_column == normalized_label:
        if candidate_label == canonical_name:
            return 1.0, "Exact canonical name match"
        return 0.95, f"Synonym match: '{candidate_label}'"
    ratio = SequenceMatcher(None, normalized_column, normalized_label).ratio()
    if ratio >= 0.6:
        return ratio * 0.9, f"Fuzzy match with '{candidate_label}' ({ratio:.2f})"
    overlap_score = _token_overlap_score(column_name, candidate_label)
    if overlap_score:
        return (
            overlap_score,
            f"Token overlap with '{candidate_label}' ({overlap_score:.2f})",
        )
    return 0.0, None


def _detect_allowed_values(
    column_name: str, sample_values: Sequence[str], descriptor: ColumnDescriptor
) -> DetectionSignal | None:
    if not descriptor.allowed_values:
        return None
    allowed = {value.casefold() for value in descriptor.allowed_values}
    if not allowed:
        return None
    observed = [value for value in sample_values if value]
    if not observed:
        return None
    matches = sum(1 for value in observed if value.casefold() in allowed)
    ratio = matches / len(observed)
    if ratio < 0.5:
        return None
    score = 0.6 + 0.4 * ratio
    return DetectionSignal(
        score=score, reason=f"{ratio:.0%} of values match allowed ontology"
    )


def _detect_email_pattern(
    column_name: str, sample_values: Sequence[str], descriptor: ColumnDescriptor
) -> DetectionSignal | None:
    observed = [value for value in sample_values if value]
    if not observed:
        return None
    matches = sum(1 for value in observed if _EMAIL_RE.match(value))
    ratio = matches / len(observed)
    if ratio < 0.5:
        return None
    score = 0.7 + 0.3 * ratio
    return DetectionSignal(
        score=score, reason=f"{ratio:.0%} of values look like email addresses"
    )


def _detect_url_pattern(
    column_name: str, sample_values: Sequence[str], descriptor: ColumnDescriptor
) -> DetectionSignal | None:
    observed = [value for value in sample_values if value]
    if not observed:
        return None
    matches = sum(
        1 for value in observed if value.startswith("http") or _URL_RE.search(value)
    )
    ratio = matches / len(observed)
    if ratio < 0.5:
        return None
    score = 0.7 + 0.3 * ratio
    return DetectionSignal(score=score, reason=f"{ratio:.0%} of values look like URLs")


def _detect_phone_pattern(
    column_name: str, sample_values: Sequence[str], descriptor: ColumnDescriptor
) -> DetectionSignal | None:
    observed = [value for value in sample_values if value]
    if not observed:
        return None
    matches = 0
    for value in observed:
        digits = [ch for ch in value if ch.isdigit()]
        if len(digits) >= 9:
            matches += 1
    ratio = matches / len(observed)
    if ratio < 0.5:
        return None
    score = 0.65 + 0.35 * ratio
    return DetectionSignal(
        score=score, reason=f"{ratio:.0%} of values look like phone numbers"
    )


def _detect_numeric_values(
    column_name: str, sample_values: Sequence[str], descriptor: ColumnDescriptor
) -> DetectionSignal | None:
    observed = [value for value in sample_values if value]
    if not observed:
        return None
    matches = 0
    for value in observed:
        try:
            float(str(value).replace(",", ""))
        except ValueError:
            continue
        else:
            matches += 1
    ratio = matches / len(observed)
    if ratio < 0.5:
        return None
    score = 0.6 + 0.4 * ratio
    return DetectionSignal(
        score=score, reason=f"{ratio:.0%} of values parse as numbers"
    )


_WORD_RE = re.compile(r"[a-z0-9]+")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL_RE = re.compile(r"https?://|\.[a-z]{2,}", re.IGNORECASE)

_DEFAULT_HOOKS: dict[str, DetectionHook] = {
    "allowed_values": _detect_allowed_values,
    "email_pattern": _detect_email_pattern,
    "url_pattern": _detect_url_pattern,
    "phone_pattern": _detect_phone_pattern,
    "numeric_values": _detect_numeric_values,
}
