"""Central configuration and environment-driven settings for the enrichment stack."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

# Optional .env loading -----------------------------------------------------
try:  # pragma: no cover - optional dependency
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - handled gracefully
    load_dotenv = None  # type: ignore


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if load_dotenv is not None:  # pragma: no branch - small guard
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()


# Base paths ----------------------------------------------------------------
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
CACHE_DIR = DATA_DIR / "cache"
LOGS_DIR = DATA_DIR / "logs"


# Input / output artefacts ---------------------------------------------------
SOURCE_XLSX = PROJECT_ROOT / "SACAA Flight Schools - FINAL copy.xlsx"
ENRICHED_XLSX = PROCESSED_DIR / "SACAA Flight Schools - ENRICHED.xlsx"
ENRICHED_JSONL = PROCESSED_DIR / "firecrawl_enriched.jsonl"
PROVENANCE_CSV = PROCESSED_DIR / "firecrawl_provenance.csv"
EVIDENCE_LOG = INTERIM_DIR / "evidence_log.csv"
RELATIONSHIPS_CSV = PROJECT_ROOT / "data" / "processed" / "relationships.csv"
SUMMARY_TXT = PROCESSED_DIR / "enrichment_summary.txt"


# Shared constants -----------------------------------------------------------
CLEANED_SHEET = "Cleaned"
ISSUES_SHEET = "Issues"
LISTS_SHEET = "Lists"


# Compliance constants -----------------------------------------------------
PROVINCES = [
    "Eastern Cape",
    "Free State",
    "Gauteng",
    "KwaZulu-Natal",
    "Limpopo",
    "Mpumalanga",
    "Northern Cape",
    "North West",
    "Western Cape",
]

CANONICAL_STATUSES = [
    "Verified",
    "Candidate",
    "Needs Review",
    "Duplicate",
    "Do Not Contact (Compliance)",
]

MIN_EVIDENCE_SOURCES = 2
DEFAULT_CONFIDENCE_BY_STATUS = {
    "Verified": 95,
    "Candidate": 70,
    "Needs Review": 40,
    "Duplicate": 0,
    "Do Not Contact (Compliance)": 0,
}

EVIDENCE_QUERIES = [
    "{name} {province} Civil Aviation Authority",
    "{name} training accreditation",
    "{name} SACAA site:.za",
]


# Dataclasses for richer configuration --------------------------------------
@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    initial_delay: float
    max_delay: float
    backoff_factor: float


@dataclass(frozen=True)
class ThrottlePolicy:
    max_concurrency: int
    min_interval: float


@dataclass(frozen=True)
class FirecrawlBehaviour:
    search_limit: int
    map_limit: int
    timeout_seconds: float
    proxy_mode: str
    only_main_content: bool
    scrape_formats: List[Any]
    parsers: List[Any]


@dataclass(frozen=True)
class FirecrawlSettings:
    api_key: Optional[str]
    api_url: Optional[str]
    retry: RetryPolicy
    throttle: ThrottlePolicy
    behaviour: FirecrawlBehaviour


# Helper parsers -------------------------------------------------------------
def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_json(name: str) -> Optional[Any]:
    value = os.getenv(name)
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _default_scrape_formats() -> List[Any]:
    return [
        "markdown",
        {
            "type": "json",
            "prompt": "Extract company mission, contact details, certifications, and fleet information.",
        },
    ]


def _default_parsers() -> List[Any]:
    return []


# Cache defaults -------------------------------------------------------------
CACHE_TTL_HOURS = _env_float("FIRECRAWL_CACHE_TTL_HOURS", 24.0)
MX_LOOKUP_TIMEOUT = _env_float("FIRECRAWL_MX_LOOKUP_TIMEOUT", 3.0)


# Firecrawl behaviour --------------------------------------------------------
RAW_SCRAPE_FORMATS = _env_json("FIRECRAWL_SCRAPE_FORMATS") or _default_scrape_formats()
RAW_PARSERS = _env_json("FIRECRAWL_PARSERS") or _default_parsers()

BEHAVIOUR = FirecrawlBehaviour(
    search_limit=_env_int("FIRECRAWL_SEARCH_LIMIT", 3),
    map_limit=_env_int("FIRECRAWL_MAP_LIMIT", 8),
    timeout_seconds=_env_float("FIRECRAWL_TIMEOUT_SECONDS", 30.0),
    proxy_mode=os.getenv("FIRECRAWL_PROXY_MODE", "basic"),
    only_main_content=os.getenv("FIRECRAWL_ONLY_MAIN_CONTENT", "true").lower()
    == "true",
    scrape_formats=list(RAW_SCRAPE_FORMATS),
    parsers=list(RAW_PARSERS),
)

RETRY = RetryPolicy(
    max_attempts=_env_int("FIRECRAWL_RETRY_MAX_ATTEMPTS", 3),
    initial_delay=_env_float("FIRECRAWL_RETRY_INITIAL_DELAY", 1.0),
    max_delay=_env_float("FIRECRAWL_RETRY_MAX_DELAY", 10.0),
    backoff_factor=_env_float("FIRECRAWL_RETRY_BACKOFF_FACTOR", 2.0),
)

THROTTLE = ThrottlePolicy(
    max_concurrency=_env_int("FIRECRAWL_MAX_CONCURRENCY", 3),
    min_interval=_env_float("FIRECRAWL_MIN_INTERVAL_SECONDS", 1.0),
)


FIRECRAWL = FirecrawlSettings(
    api_key=os.getenv("FIRECRAWL_API_KEY"),
    api_url=os.getenv("FIRECRAWL_API_URL"),
    retry=RETRY,
    throttle=THROTTLE,
    behaviour=BEHAVIOUR,
)


# Pipeline tuning ------------------------------------------------------------
BATCH_SIZE = _env_int("FIRECRAWL_BATCH_SIZE", 20)
REQUEST_DELAY_SECONDS = _env_float("FIRECRAWL_REQUEST_DELAY_SECONDS", 1.0)


def resolve_api_key(explicit: Optional[str] = None) -> str:
    """Return the API key, prioritising explicit overrides."""

    key = explicit or FIRECRAWL.api_key
    if not key:
        raise ValueError(
            "Firecrawl API key is required. Set FIRECRAWL_API_KEY env variable or pass api_key explicitly."
        )
    return key
