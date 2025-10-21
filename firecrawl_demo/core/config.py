"""Central configuration and secrets-backed settings for the enrichment stack."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from firecrawl_demo.core.profiles import (
    NumericUnitRule,
    ProfileError,
    RefinementProfile,
    discover_profile,
    load_profile,
)
from firecrawl_demo.governance.secrets import (
    SecretsProvider,
    build_provider_from_environment,
)

try:  # pragma: no cover - optional dependency
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - handled gracefully at runtime
    load_dotenv = None  # type: ignore


PACKAGE_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = PACKAGE_ROOT.parent

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


# Profile loading -----------------------------------------------------------
PROFILE: RefinementProfile
PROFILE_PATH: Path


def _resolve_profile_from_env() -> tuple[RefinementProfile, Path]:
    profile_id = os.environ.get("REFINEMENT_PROFILE", "za_flight_schools")
    profile_path_env = os.environ.get("REFINEMENT_PROFILE_PATH")
    try:
        if profile_path_env:
            resolved_path = Path(profile_path_env).expanduser().resolve()
        else:
            resolved_path = discover_profile(PROJECT_ROOT, profile_id)
        profile = load_profile(resolved_path)
        return profile, resolved_path
    except ProfileError as exc:  # pragma: no cover - configuration failure
        raise RuntimeError(f"Failed to load refinement profile: {exc}") from exc


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
EXPECTED_COLUMNS: list[str]
PROVINCES: list[str]
CANONICAL_STATUSES: list[str]
DEFAULT_STATUS: str

MIN_EVIDENCE_SOURCES: int
DEFAULT_CONFIDENCE_BY_STATUS: dict[str, int]
OFFICIAL_SOURCE_KEYWORDS: tuple[str, ...]
EVIDENCE_QUERIES: list[str]

PHONE_COUNTRY_CODE: str
PHONE_E164_REGEX: str
PHONE_NATIONAL_PREFIXES: tuple[str, ...]
PHONE_NATIONAL_NUMBER_LENGTH: int | None

EMAIL_REGEX: str
ROLE_INBOX_PREFIXES: tuple[str, ...]
EMAIL_REQUIRE_DOMAIN_MATCH: bool

RESEARCH_QUERIES: list[str]

NUMERIC_UNIT_RULES: tuple[NumericUnitRule, ...]


def _apply_profile(profile: RefinementProfile, profile_path: Path) -> None:
    global PROFILE, PROFILE_PATH
    global EXPECTED_COLUMNS, PROVINCES, CANONICAL_STATUSES, DEFAULT_STATUS
    global MIN_EVIDENCE_SOURCES, DEFAULT_CONFIDENCE_BY_STATUS, OFFICIAL_SOURCE_KEYWORDS
    global EVIDENCE_QUERIES, PHONE_COUNTRY_CODE, PHONE_E164_REGEX
    global PHONE_NATIONAL_PREFIXES, PHONE_NATIONAL_NUMBER_LENGTH
    global EMAIL_REGEX, ROLE_INBOX_PREFIXES, EMAIL_REQUIRE_DOMAIN_MATCH
    global RESEARCH_QUERIES, NUMERIC_UNIT_RULES

    PROFILE = profile
    PROFILE_PATH = profile_path

    EXPECTED_COLUMNS = list(profile.dataset.expected_columns)
    PROVINCES = list(profile.provinces)
    CANONICAL_STATUSES = list(profile.statuses)
    DEFAULT_STATUS = profile.default_status

    MIN_EVIDENCE_SOURCES = profile.compliance.min_evidence_sources
    DEFAULT_CONFIDENCE_BY_STATUS = dict(profile.compliance.default_confidence)
    OFFICIAL_SOURCE_KEYWORDS = tuple(profile.compliance.official_source_keywords)
    EVIDENCE_QUERIES = list(profile.compliance.evidence_queries)

    PHONE_COUNTRY_CODE = profile.contact.phone.country_code
    PHONE_E164_REGEX = profile.contact.phone.e164_regex
    PHONE_NATIONAL_PREFIXES = tuple(profile.contact.phone.national_prefixes)
    PHONE_NATIONAL_NUMBER_LENGTH = profile.contact.phone.national_number_length

    EMAIL_REGEX = profile.contact.email.regex
    ROLE_INBOX_PREFIXES = tuple(profile.contact.email.role_prefixes)
    EMAIL_REQUIRE_DOMAIN_MATCH = profile.contact.email.require_domain_match

    RESEARCH_QUERIES = list(profile.research.queries)
    NUMERIC_UNIT_RULES = tuple(profile.dataset.numeric_units)


_profile_init, _profile_path_init = _resolve_profile_from_env()
_apply_profile(_profile_init, _profile_path_init)


def switch_profile(
    *,
    profile_id: str | None = None,
    profile_path: Path | None = None,
) -> RefinementProfile:
    """Switch the active refinement profile at runtime."""

    if profile_path:
        resolved = Path(profile_path).expanduser().resolve()
        profile = load_profile(resolved)
        _apply_profile(profile, resolved)
        return profile
    if profile_id:
        resolved = discover_profile(PROJECT_ROOT, profile_id)
        profile = load_profile(resolved)
        _apply_profile(profile, resolved)
        return profile
    raise ProfileError("switch_profile requires either profile_id or profile_path")


def list_profiles() -> list[dict[str, object]]:
    """Return available profiles with metadata."""

    profiles: list[dict[str, object]] = []
    profiles_dir = PROJECT_ROOT / "profiles"
    if not profiles_dir.exists():
        return profiles
    for path in sorted(profiles_dir.glob("*.y*ml")):
        try:
            profile = load_profile(path)
        except ProfileError:
            continue
        profiles.append(
            {
                "id": profile.identifier,
                "name": profile.name,
                "description": profile.description,
                "path": str(path),
                "active": path.resolve() == PROFILE_PATH.resolve(),
            }
        )
    return profiles


# Dataclasses for richer configuration --------------------------------------
@dataclass(frozen=True)
class FeatureFlags:
    enable_firecrawl_sdk: bool = False
    enable_press_research: bool = True
    enable_regulator_lookup: bool = True
    enable_ml_inference: bool = True
    investigate_rebrands: bool = True


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
    scrape_formats: list[Any]
    parsers: list[Any]


@dataclass(frozen=True)
class FirecrawlSettings:
    api_key: str | None
    api_url: str | None
    retry: RetryPolicy
    throttle: ThrottlePolicy
    behaviour: FirecrawlBehaviour


@dataclass(frozen=True)
class EvidenceSinkSettings:
    backend: str = "csv"
    stream_transport: str = "rest"
    stream_enabled: bool = False
    rest_endpoint: str | None = None
    kafka_topic: str | None = None


@dataclass(frozen=True)
class CrawlerInfrastructureSettings:
    frontier_backend: str = "scrapy"
    scheduler_mode: str = "priority"
    politeness_delay_seconds: float = 1.0
    max_depth: int = 6
    max_pages: int = 5000
    trap_rules_path: Path | None = None
    user_agent: str = "ACESCrawler/1.0"
    robots_cache_hours: float = 6.0


@dataclass(frozen=True)
class HealthProbeSettings:
    port: int = 8080
    liveness_path: str = "/healthz"
    readiness_path: str = "/readyz"
    startup_path: str = "/startupz"


@dataclass(frozen=True)
class SLOSettings:
    availability_target: float = 99.5
    latency_p95_ms: float = 500.0
    error_budget_percent: float = 2.0


@dataclass(frozen=True)
class ObservabilitySettings:
    probes: HealthProbeSettings = field(default_factory=HealthProbeSettings)
    slos: SLOSettings = field(default_factory=SLOSettings)
    alert_routes: tuple[str, ...] = ("slack",)


@dataclass(frozen=True)
class PolicySettings:
    bundle_path: Path | None = None
    decision_path: str = "opa/allow"
    enforcement_mode: str = "enforce"
    cache_seconds: int = 30


@dataclass(frozen=True)
class PlanCommitSettings:
    require_plan: bool = True
    diff_format: str = "markdown"
    audit_topic: str = "audit.plan-commit"
    allow_force_commit: bool = False
    require_commit: bool = True
    require_if_match: bool = True
    audit_log_path: Path = field(
        default_factory=lambda: DATA_DIR / "logs" / "plan_commit_audit.jsonl"
    )
    max_diff_size: int = 5000
    blocked_domains: tuple[str, ...] = ()
    blocked_keywords: tuple[str, ...] = (
        "rm -rf",
        "drop database",
        "curl http://",
        "wget http://",
    )
    rag_faithfulness_threshold: float = 0.75
    rag_context_precision_threshold: float = 0.7
    rag_answer_relevancy_threshold: float = 0.7


@dataclass(frozen=True)
class LineageSettings:
    enabled: bool = True
    namespace: str = "aces-aerodynamics"
    job_name: str = "enrichment"
    dataset_name: str = "flight-schools"
    artifact_root: Path = field(default_factory=lambda: PROJECT_ROOT / "artifacts")
    transport: str = "file"
    endpoint: str | None = None
    api_key: str | None = None
    kafka_topic: str | None = None
    kafka_bootstrap_servers: str | None = None


@dataclass(frozen=True)
class LakehouseSettings:
    enabled: bool = True
    backend: str = "delta"
    root_path: Path = field(default_factory=lambda: DATA_DIR / "lakehouse")
    table_name: str = "flight_schools"


@dataclass(frozen=True)
class DeploymentSettings:
    profile: str = "dev"
    codex_enabled: bool = True
    crawler_mode: str = "full"


@dataclass(frozen=True)
class VersioningSettings:
    enabled: bool = True
    strategy: str = "manifest"
    metadata_root: Path = field(default_factory=lambda: DATA_DIR / "versioning")
    dvc_remote: str | None = None
    lakefs_repo: str | None = None
    reproduce_command: tuple[str, ...] = (
        "poetry",
        "run",
        "python",
        "-m",
        "firecrawl_demo.interfaces.cli",
        "enrich",
    )


@dataclass(frozen=True)
class GraphSemanticsSettings:
    enabled: bool = True
    min_organisation_nodes: int = 1
    min_province_nodes: int = 1
    max_province_nodes: int = len(PROVINCES)
    min_status_nodes: int = 1
    max_status_nodes: int = len(CANONICAL_STATUSES)
    min_edge_count: int = 2
    min_average_degree: float = 1.5
    max_average_degree: float = 4.0


@dataclass(frozen=True)
class DriftSettings:
    enabled: bool = True
    threshold: float = 0.15
    baseline_path: Path | None = None
    whylogs_baseline_path: Path | None = None
    whylogs_output_dir: Path = field(
        default_factory=lambda: DATA_DIR / "observability" / "whylogs"
    )
    require_baseline: bool = True
    require_whylogs_metadata: bool = True
    alert_output_path: Path = field(
        default_factory=lambda: DATA_DIR / "observability" / "whylogs" / "alerts.json"
    )
    prometheus_output_path: Path = field(
        default_factory=lambda: DATA_DIR / "observability" / "whylogs" / "metrics.prom"
    )
    slack_webhook: str | None = None
    dashboard_url: str | None = None


DRIFT: DriftSettings = DriftSettings()
GRAPH_SEMANTICS: GraphSemanticsSettings = GraphSemanticsSettings()


def _build_deployment_settings(provider: SecretsProvider) -> DeploymentSettings:
    profile = (_get_value("DEPLOYMENT_PROFILE", "dev", provider) or "dev").lower()
    override = _get_value("DEPLOYMENT_CODEX_ENABLED", None, provider)
    codex_enabled = (
        override.strip().lower() in {"1", "true", "yes", "on"}
        if override is not None
        else profile != "dist"
    )
    crawler_mode = _get_value("CRAWLER_MODE", "full", provider) or "full"
    return DeploymentSettings(
        profile=profile,
        codex_enabled=codex_enabled,
        crawler_mode=crawler_mode,
    )


def _build_versioning_settings(provider: SecretsProvider) -> VersioningSettings:
    enabled = _env_bool("VERSIONING_ENABLED", True, provider)
    strategy = _get_value("VERSIONING_STRATEGY", "manifest", provider) or "manifest"
    metadata_root = _env_path("VERSIONING_METADATA_ROOT", provider)
    default_command = (
        "poetry",
        "run",
        "python",
        "-m",
        "firecrawl_demo.interfaces.cli",
        "enrich",
    )
    command_list = _env_list("VERSIONING_REPRODUCE_COMMAND", provider)
    reproduce_command = tuple(command_list) if command_list else default_command
    return VersioningSettings(
        enabled=enabled,
        strategy=strategy,
        metadata_root=metadata_root or DATA_DIR / "versioning",
        dvc_remote=_get_value("VERSIONING_DVC_REMOTE", None, provider),
        lakefs_repo=_get_value("VERSIONING_LAKEFS_REPO", None, provider),
        reproduce_command=reproduce_command,
    )


def _build_drift_settings(provider: SecretsProvider) -> DriftSettings:
    enabled = _env_bool("DRIFT_ENABLED", True, provider)
    threshold_raw = _get_value("DRIFT_THRESHOLD", None, provider)
    try:
        threshold = float(threshold_raw) if threshold_raw is not None else 0.15
    except ValueError:
        threshold = 0.15
    baseline_path = _env_path("DRIFT_BASELINE_PATH", provider)
    whylogs_baseline_path = _env_path("DRIFT_WHYLOGS_BASELINE", provider)
    whylogs_output = _env_path("DRIFT_WHYLOGS_OUTPUT", provider)
    if whylogs_output is None:
        whylogs_output = DATA_DIR / "observability" / "whylogs"
    alert_output = _env_path("DRIFT_ALERT_OUTPUT", provider)
    prometheus_output = _env_path("DRIFT_PROMETHEUS_OUTPUT", provider)
    slack_webhook = _get_value("DRIFT_SLACK_WEBHOOK", None, provider)
    dashboard_url = _get_value("DRIFT_DASHBOARD_URL", None, provider)
    return DriftSettings(
        enabled=enabled,
        threshold=threshold,
        baseline_path=baseline_path,
        whylogs_baseline_path=whylogs_baseline_path,
        whylogs_output_dir=whylogs_output,
        require_baseline=_env_bool("DRIFT_REQUIRE_BASELINE", True, provider),
        require_whylogs_metadata=_env_bool(
            "DRIFT_REQUIRE_WHYLOGS_METADATA", True, provider
        ),
        alert_output_path=alert_output
        or (DATA_DIR / "observability" / "whylogs" / "alerts.json"),
        prometheus_output_path=prometheus_output
        or (DATA_DIR / "observability" / "whylogs" / "metrics.prom"),
        slack_webhook=slack_webhook,
        dashboard_url=dashboard_url,
    )


def _get_value(name: str, default: str | None, provider: SecretsProvider) -> str | None:
    value = provider.get(name)
    return value if value is not None else default


def _env_bool(name: str, default: bool, provider: SecretsProvider) -> bool:
    value = _get_value(name, None, provider)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, provider: SecretsProvider) -> int:
    value = _get_value(name, None, provider)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float, provider: SecretsProvider) -> float:
    value = _get_value(name, None, provider)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_json(name: str, provider: SecretsProvider) -> Any | None:
    value = _get_value(name, None, provider)
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _env_list(name: str, provider: SecretsProvider) -> list[str]:
    value = _get_value(name, None, provider)
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
        return list(parsed)
    return [part.strip() for part in value.split(",") if part.strip()]


def _env_path(name: str, provider: SecretsProvider) -> Path | None:
    value = _get_value(name, None, provider)
    if not value:
        return None
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _default_scrape_formats() -> list[Any]:
    return [
        "markdown",
        {
            "type": "json",
            "prompt": "Extract company mission, contact details, certifications, and fleet information.",
        },
    ]


def _default_parsers() -> list[Any]:
    return []


@dataclass(slots=True)
class Settings:
    provider: SecretsProvider
    FIRECRAWL_API_KEY: str | None = field(init=False)
    FIRECRAWL_API_URL: str = field(init=False)

    def __post_init__(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.FIRECRAWL_API_KEY = _get_value("FIRECRAWL_API_KEY", None, self.provider)
        self.FIRECRAWL_API_URL = (
            _get_value("FIRECRAWL_API_URL", "https://api.firecrawl.com", self.provider)
            or "https://api.firecrawl.com"
        )


settings: Settings
FEATURE_FLAGS: FeatureFlags
ALLOW_NETWORK_RESEARCH: bool
CACHE_TTL_HOURS: float
MX_LOOKUP_TIMEOUT: float
RAW_SCRAPE_FORMATS: list[Any]
RAW_PARSERS: list[Any]
BEHAVIOUR: FirecrawlBehaviour
RETRY: RetryPolicy
THROTTLE: ThrottlePolicy
FIRECRAWL: FirecrawlSettings
BATCH_SIZE: int
REQUEST_DELAY_SECONDS: float
SECRETS_PROVIDER: SecretsProvider
EVIDENCE_SINK: EvidenceSinkSettings
CRAWLER_INFRASTRUCTURE: CrawlerInfrastructureSettings
OBSERVABILITY: ObservabilitySettings
POLICY_GUARDS: PolicySettings
PLAN_COMMIT: PlanCommitSettings
LINEAGE: LineageSettings
LAKEHOUSE: LakehouseSettings
DEPLOYMENT: DeploymentSettings
VERSIONING: VersioningSettings


def _build_firecrawl_settings(provider: SecretsProvider) -> FirecrawlSettings:
    retry = RetryPolicy(
        max_attempts=_env_int("FIRECRAWL_RETRY_MAX_ATTEMPTS", 3, provider),
        initial_delay=_env_float("FIRECRAWL_RETRY_INITIAL_DELAY", 1.0, provider),
        max_delay=_env_float("FIRECRAWL_RETRY_MAX_DELAY", 10.0, provider),
        backoff_factor=_env_float("FIRECRAWL_RETRY_BACKOFF_FACTOR", 2.0, provider),
    )

    throttle = ThrottlePolicy(
        max_concurrency=_env_int("FIRECRAWL_MAX_CONCURRENCY", 3, provider),
        min_interval=_env_float("FIRECRAWL_MIN_INTERVAL_SECONDS", 1.0, provider),
    )

    scrape_formats = (
        _env_json("FIRECRAWL_SCRAPE_FORMATS", provider) or _default_scrape_formats()
    )
    parsers = _env_json("FIRECRAWL_PARSERS", provider) or _default_parsers()

    behaviour = FirecrawlBehaviour(
        search_limit=_env_int("FIRECRAWL_SEARCH_LIMIT", 3, provider),
        map_limit=_env_int("FIRECRAWL_MAP_LIMIT", 8, provider),
        timeout_seconds=_env_float("FIRECRAWL_TIMEOUT_SECONDS", 30.0, provider),
        proxy_mode=_get_value("FIRECRAWL_PROXY_MODE", "basic", provider) or "basic",
        only_main_content=(
            (
                _get_value("FIRECRAWL_ONLY_MAIN_CONTENT", "true", provider) or "true"
            ).lower()
            == "true"
        ),
        scrape_formats=list(scrape_formats),
        parsers=list(parsers),
    )

    api_url = _get_value("FIRECRAWL_API_URL", "https://api.firecrawl.com", provider)

    return FirecrawlSettings(
        api_key=_get_value("FIRECRAWL_API_KEY", None, provider),
        api_url=api_url,
        retry=retry,
        throttle=throttle,
        behaviour=behaviour,
    )


def configure(provider: SecretsProvider | None = None) -> None:
    """Initialise configuration from the supplied secrets provider."""

    global SECRETS_PROVIDER
    global settings
    global FEATURE_FLAGS
    global ALLOW_NETWORK_RESEARCH
    global CACHE_TTL_HOURS
    global MX_LOOKUP_TIMEOUT
    global RAW_SCRAPE_FORMATS
    global RAW_PARSERS
    global BEHAVIOUR
    global RETRY
    global THROTTLE
    global FIRECRAWL
    global BATCH_SIZE
    global REQUEST_DELAY_SECONDS
    global EVIDENCE_SINK
    global CRAWLER_INFRASTRUCTURE
    global OBSERVABILITY
    global POLICY_GUARDS
    global PLAN_COMMIT
    global GRAPH_SEMANTICS
    global LINEAGE
    global LAKEHOUSE
    global DEPLOYMENT
    global VERSIONING
    global DRIFT

    SECRETS_PROVIDER = provider or build_provider_from_environment()

    settings = Settings(provider=SECRETS_PROVIDER)

    FEATURE_FLAGS = FeatureFlags(
        enable_firecrawl_sdk=_env_bool(
            "FEATURE_ENABLE_FIRECRAWL_SDK", False, SECRETS_PROVIDER
        ),
        enable_press_research=_env_bool(
            "FEATURE_ENABLE_PRESS_RESEARCH", True, SECRETS_PROVIDER
        ),
        enable_regulator_lookup=_env_bool(
            "FEATURE_ENABLE_REGULATOR_LOOKUP", True, SECRETS_PROVIDER
        ),
        enable_ml_inference=_env_bool(
            "FEATURE_ENABLE_ML_INFERENCE", True, SECRETS_PROVIDER
        ),
        investigate_rebrands=_env_bool(
            "FEATURE_INVESTIGATE_REBRANDS", True, SECRETS_PROVIDER
        ),
    )

    ALLOW_NETWORK_RESEARCH = _env_bool(
        "ALLOW_NETWORK_RESEARCH", False, SECRETS_PROVIDER
    )

    CACHE_TTL_HOURS = _env_float("FIRECRAWL_CACHE_TTL_HOURS", 24.0, SECRETS_PROVIDER)
    MX_LOOKUP_TIMEOUT = _env_float("FIRECRAWL_MX_LOOKUP_TIMEOUT", 3.0, SECRETS_PROVIDER)

    firecrawl_settings = _build_firecrawl_settings(SECRETS_PROVIDER)
    RETRY = firecrawl_settings.retry
    THROTTLE = firecrawl_settings.throttle
    BEHAVIOUR = firecrawl_settings.behaviour
    FIRECRAWL = FirecrawlSettings(
        api_key=settings.FIRECRAWL_API_KEY,
        api_url=settings.FIRECRAWL_API_URL,
        retry=RETRY,
        throttle=THROTTLE,
        behaviour=BEHAVIOUR,
    )

    RAW_SCRAPE_FORMATS = list(FIRECRAWL.behaviour.scrape_formats)
    RAW_PARSERS = list(FIRECRAWL.behaviour.parsers)

    BATCH_SIZE = _env_int("FIRECRAWL_BATCH_SIZE", 20, SECRETS_PROVIDER)
    REQUEST_DELAY_SECONDS = _env_float(
        "FIRECRAWL_REQUEST_DELAY_SECONDS", 1.0, SECRETS_PROVIDER
    )

    sink_backend = (
        _get_value("EVIDENCE_SINK_BACKEND", "csv", SECRETS_PROVIDER) or "csv"
    ).lower()
    stream_transport = (
        _get_value("EVIDENCE_STREAM_TRANSPORT", "rest", SECRETS_PROVIDER) or "rest"
    ).lower()
    EVIDENCE_SINK = EvidenceSinkSettings(
        backend=sink_backend,
        stream_transport=stream_transport,
        stream_enabled=_env_bool("EVIDENCE_STREAM_ENABLED", False, SECRETS_PROVIDER),
        rest_endpoint=_get_value(
            "EVIDENCE_STREAM_REST_ENDPOINT", None, SECRETS_PROVIDER
        ),
        kafka_topic=_get_value("EVIDENCE_STREAM_KAFKA_TOPIC", None, SECRETS_PROVIDER),
    )

    CRAWLER_INFRASTRUCTURE = CrawlerInfrastructureSettings(
        frontier_backend=_get_value(
            "CRAWLER_FRONTIER_BACKEND", "scrapy", SECRETS_PROVIDER
        )
        or "scrapy",
        scheduler_mode=_get_value(
            "CRAWLER_SCHEDULER_MODE", "priority", SECRETS_PROVIDER
        )
        or "priority",
        politeness_delay_seconds=_env_float(
            "CRAWLER_POLITENESS_DELAY_SECONDS", 1.0, SECRETS_PROVIDER
        ),
        max_depth=_env_int("CRAWLER_MAX_DEPTH", 6, SECRETS_PROVIDER),
        max_pages=_env_int("CRAWLER_MAX_PAGES", 5000, SECRETS_PROVIDER),
        trap_rules_path=_env_path("CRAWLER_TRAP_RULES_PATH", SECRETS_PROVIDER),
        user_agent=_get_value("CRAWLER_USER_AGENT", "ACESCrawler/1.0", SECRETS_PROVIDER)
        or "ACESCrawler/1.0",
        robots_cache_hours=_env_float(
            "CRAWLER_ROBOTS_CACHE_HOURS", 6.0, SECRETS_PROVIDER
        ),
    )

    probes = HealthProbeSettings(
        port=_env_int("OBSERVABILITY_PORT", 8080, SECRETS_PROVIDER),
        liveness_path=_get_value(
            "OBSERVABILITY_LIVENESS_PATH", "/healthz", SECRETS_PROVIDER
        )
        or "/healthz",
        readiness_path=_get_value(
            "OBSERVABILITY_READINESS_PATH", "/readyz", SECRETS_PROVIDER
        )
        or "/readyz",
        startup_path=_get_value(
            "OBSERVABILITY_STARTUP_PATH", "/startupz", SECRETS_PROVIDER
        )
        or "/startupz",
    )
    slos = SLOSettings(
        availability_target=_env_float(
            "SLO_AVAILABILITY_TARGET", 99.5, SECRETS_PROVIDER
        ),
        latency_p95_ms=_env_float("SLO_LATENCY_P95_MS", 500.0, SECRETS_PROVIDER),
        error_budget_percent=_env_float(
            "SLO_ERROR_BUDGET_PERCENT", 2.0, SECRETS_PROVIDER
        ),
    )
    alert_routes = _env_list("OBSERVABILITY_ALERT_ROUTES", SECRETS_PROVIDER)
    OBSERVABILITY = ObservabilitySettings(
        probes=probes,
        slos=slos,
        alert_routes=tuple(alert_routes) if alert_routes else ("slack",),
    )

    POLICY_GUARDS = PolicySettings(
        bundle_path=_env_path("OPA_BUNDLE_PATH", SECRETS_PROVIDER),
        decision_path=_get_value("OPA_DECISION_PATH", "opa/allow", SECRETS_PROVIDER)
        or "opa/allow",
        enforcement_mode=_get_value("OPA_ENFORCEMENT_MODE", "enforce", SECRETS_PROVIDER)
        or "enforce",
        cache_seconds=_env_int("OPA_CACHE_SECONDS", 30, SECRETS_PROVIDER),
    )

    blocked_keyword_env = _env_list("PLAN_COMMIT_BLOCKED_KEYWORDS", SECRETS_PROVIDER)
    default_blocked_keywords = [
        "rm -rf",
        "drop database",
        "curl http://",
        "wget http://",
    ]
    if blocked_keyword_env:
        combined_keywords = list(
            dict.fromkeys(blocked_keyword_env + default_blocked_keywords)
        )
    else:
        combined_keywords = default_blocked_keywords

    PLAN_COMMIT = PlanCommitSettings(
        require_plan=_env_bool("PLAN_COMMIT_REQUIRED", True, SECRETS_PROVIDER),
        diff_format=_get_value("PLAN_COMMIT_DIFF_FORMAT", "markdown", SECRETS_PROVIDER)
        or "markdown",
        audit_topic=_get_value(
            "PLAN_COMMIT_AUDIT_TOPIC", "audit.plan-commit", SECRETS_PROVIDER
        )
        or "audit.plan-commit",
        allow_force_commit=_env_bool(
            "PLAN_COMMIT_ALLOW_FORCE", False, SECRETS_PROVIDER
        ),
        require_commit=_env_bool("PLAN_COMMIT_REQUIRE_COMMIT", True, SECRETS_PROVIDER),
        require_if_match=_env_bool(
            "PLAN_COMMIT_REQUIRE_IF_MATCH", True, SECRETS_PROVIDER
        ),
        audit_log_path=_env_path("PLAN_COMMIT_AUDIT_LOG_PATH", SECRETS_PROVIDER)
        or (DATA_DIR / "logs" / "plan_commit_audit.jsonl"),
        max_diff_size=_env_int("PLAN_COMMIT_MAX_DIFF_SIZE", 5000, SECRETS_PROVIDER),
        blocked_domains=tuple(
            _env_list("PLAN_COMMIT_BLOCKED_DOMAINS", SECRETS_PROVIDER)
        ),
        blocked_keywords=tuple(combined_keywords),
        rag_faithfulness_threshold=_env_float(
            "PLAN_COMMIT_RAG_FAITHFULNESS", 0.75, SECRETS_PROVIDER
        ),
        rag_context_precision_threshold=_env_float(
            "PLAN_COMMIT_RAG_CONTEXT_PRECISION", 0.7, SECRETS_PROVIDER
        ),
        rag_answer_relevancy_threshold=_env_float(
            "PLAN_COMMIT_RAG_ANSWER_RELEVANCY", 0.7, SECRETS_PROVIDER
        ),
    )

    GRAPH_SEMANTICS = GraphSemanticsSettings(
        enabled=_env_bool("GRAPH_SEMANTICS_ENABLED", True, SECRETS_PROVIDER),
        min_organisation_nodes=_env_int(
            "GRAPH_MIN_ORGANISATION_NODES", 1, SECRETS_PROVIDER
        ),
        min_province_nodes=_env_int("GRAPH_MIN_PROVINCE_NODES", 1, SECRETS_PROVIDER),
        max_province_nodes=_env_int(
            "GRAPH_MAX_PROVINCE_NODES", len(PROVINCES), SECRETS_PROVIDER
        ),
        min_status_nodes=_env_int("GRAPH_MIN_STATUS_NODES", 1, SECRETS_PROVIDER),
        max_status_nodes=_env_int(
            "GRAPH_MAX_STATUS_NODES", len(CANONICAL_STATUSES), SECRETS_PROVIDER
        ),
        min_edge_count=_env_int("GRAPH_MIN_EDGE_COUNT", 2, SECRETS_PROVIDER),
        min_average_degree=_env_float("GRAPH_MIN_AVG_DEGREE", 1.5, SECRETS_PROVIDER),
        max_average_degree=_env_float("GRAPH_MAX_AVG_DEGREE", 4.0, SECRETS_PROVIDER),
    )

    lineage_root = _env_path("LINEAGE_ARTIFACT_ROOT", SECRETS_PROVIDER) or (
        PROJECT_ROOT / "artifacts"
    )
    lineage_transport = (
        _get_value("OPENLINEAGE_TRANSPORT", None, SECRETS_PROVIDER)
        or _get_value("LINEAGE_TRANSPORT", "file", SECRETS_PROVIDER)
        or "file"
    )
    lineage_endpoint = _get_value(
        "OPENLINEAGE_URL", None, SECRETS_PROVIDER
    ) or _get_value("LINEAGE_ENDPOINT", None, SECRETS_PROVIDER)
    lineage_api_key = _get_value(
        "OPENLINEAGE_API_KEY", None, SECRETS_PROVIDER
    ) or _get_value("LINEAGE_API_KEY", None, SECRETS_PROVIDER)
    lineage_kafka_topic = _get_value(
        "OPENLINEAGE_KAFKA_TOPIC", None, SECRETS_PROVIDER
    ) or _get_value("LINEAGE_KAFKA_TOPIC", None, SECRETS_PROVIDER)
    lineage_kafka_bootstrap = _get_value(
        "OPENLINEAGE_KAFKA_BOOTSTRAP", None, SECRETS_PROVIDER
    ) or _get_value("LINEAGE_KAFKA_BOOTSTRAP", None, SECRETS_PROVIDER)
    lineage_namespace = (
        _get_value("OPENLINEAGE_NAMESPACE", None, SECRETS_PROVIDER)
        or _get_value("LINEAGE_NAMESPACE", "aces-aerodynamics", SECRETS_PROVIDER)
        or "aces-aerodynamics"
    )
    LINEAGE = LineageSettings(
        enabled=_env_bool("LINEAGE_ENABLED", True, SECRETS_PROVIDER),
        namespace=lineage_namespace,
        job_name=_get_value("LINEAGE_JOB_NAME", "enrichment", SECRETS_PROVIDER)
        or "enrichment",
        dataset_name=_get_value(
            "LINEAGE_DATASET_NAME", "flight-schools", SECRETS_PROVIDER
        )
        or "flight-schools",
        artifact_root=lineage_root,
        transport=lineage_transport,
        endpoint=lineage_endpoint,
        api_key=lineage_api_key,
        kafka_topic=lineage_kafka_topic,
        kafka_bootstrap_servers=lineage_kafka_bootstrap,
    )

    lakehouse_root = _env_path("LAKEHOUSE_ROOT", SECRETS_PROVIDER) or (
        DATA_DIR / "lakehouse"
    )
    LAKEHOUSE = LakehouseSettings(
        enabled=_env_bool("LAKEHOUSE_ENABLED", True, SECRETS_PROVIDER),
        backend=_get_value("LAKEHOUSE_BACKEND", "delta", SECRETS_PROVIDER) or "delta",
        root_path=lakehouse_root,
        table_name=_get_value(
            "LAKEHOUSE_TABLE_NAME", "flight_schools", SECRETS_PROVIDER
        )
        or "flight_schools",
    )

    DEPLOYMENT = _build_deployment_settings(SECRETS_PROVIDER)
    VERSIONING = _build_versioning_settings(SECRETS_PROVIDER)
    DRIFT = _build_drift_settings(SECRETS_PROVIDER)


def resolve_api_key(
    explicit: str | None = None, *, provider: SecretsProvider | None = None
) -> str:
    """Return the Firecrawl API key, prioritising explicit overrides."""

    active_provider = provider or SECRETS_PROVIDER
    if explicit:
        return explicit
    key = settings.FIRECRAWL_API_KEY or active_provider.get("FIRECRAWL_API_KEY")
    if not key:
        raise ValueError(
            "Firecrawl API key is required. Set FIRECRAWL_API_KEY in the secrets provider or pass api_key explicitly."
        )
    return key


# Initialise module state on import.
configure()
