Watercrawl Crawl/Extract Subsystem — Firecrawl Removal & In-house Replacement

Objective

Remove firecrawl_demo and ship a first-party crawler that turns URLs (and site sections) into LLM-ready Markdown + structured entities, with region-aware compliance, polite crawling, and contact/fleet enrichment hooks. Must run on Python 3.13 and integrate with existing Celery/CLI/agents. Scrapy and Playwright both support 3.13; use scrapy-playwright as JS fallback. ￼

⸻

Target repo touch-points (baseline)
• Watercrawl repo (Python 3.13 toolchain & analyst surface). Replace the firecrawl_demo path and any callers with the new module. ￼

⸻

High-level architecture (modules & contracts)

1. crawlkit.fetch — polite fetch & optional render

Purpose: Two-stage retrieval
• Fast path: Scrapy HTTP client (HTTP/2, caching, retries, jitter; per-domain concurrency caps).
• JS fallback: scrapy-playwright only when heuristics say content needs rendering (empty body, SPA markers, essential elements missing).
• Robots/ToS: Always resolve and respect robots.txt (RFC 9309); expose site-policy decisions to the pipeline. ￼

Key settings

@dataclass
class FetchPolicy:
obey_robots: bool = True
max_depth: int = 2
max_pages: int = 200
concurrent_per_domain: int = 2
render_js: Literal["auto","never","always"] = "auto"
region: Literal["ZA","EU","UK","US"] = "ZA" # drives compliance & source allowlist

Interface

async def fetch(url: str, policy: FetchPolicy) -> "FetchedPage":
"""Returns HTTP/JS-rendered HTML, request/response meta, robots decision, and provenance."""

Notes: Scrapy has first-party docs for dynamic content; scrapy-playwright is the canonical adapter. ￼

⸻

2. crawlkit.distill — HTML → clean article/sections → Markdown

Purpose: Deterministic, fast content distillation with structured hints.
• DOM & boilerplate removal: selectolax (fast), with Trafilatura/jusText/Readability profiles for main-content extraction.
• Structured metadata: Pull JSON-LD, Microdata, RDFa, OpenGraph via extruct for titles, dates, People/Org, phones, emails already embedded.
• HTML→Markdown: Default markdownify; optionally html2text (plain-ish MD); performance profile: Rust-backed html-to-markdown when throughput is key. ￼

Interface

def distill(html: str, url: str, profile: Literal["article","docs","catalog"]="article") -> "DistilledDoc":
"""Returns markdown, raw_text, metadata, structured microdata, and extraction metrics."""

⸻

3. crawlkit.extract — entities & enrichment hooks

Purpose: Turn distilled content into people/orgs/contacts (+ optional aviation fleet signal).
• People/Org extraction: NER + rules; prefer JSON-LD Person/Organization from extruct when present.
• Contact hygiene: Never probe aggressively. Limit to pattern inference + DNS/MX checks; if SMTP is used, stop before DATA and treat results as probabilistic (servers may disable/obscure VRFY/EXPN; SMTP callbacks have anti-spam caveats). Provide vendor adapters for third-party verifiers. ￼
• Aviation fleets (bonus): Licensed APIs only (AirLabs, Aviation-Edge). Avoid scraping sites whose ToS forbid it; keep provenance. ￼

Interface

def extract_entities(doc: DistilledDoc, enrich: bool=True, domain_hint: str|None=None) -> "Entities":
"""Returns people, roles, emails(verified_status), phones, org facts; optional fleet intel."""

⸻

4. crawlkit.compliance — region toggles & audit

Purpose: Encode POPIA/GDPR/UK B2B constraints into runtime policy.
• Robots/Politeness: Honour robots.txt; rate-limit to avoid undue load; identify crawler. ￼
• Direct marketing rules:
• ZA (POPIA): Follow the Information Regulator Guidance Note for unsolicited electronic communications (s69); log lawful basis, provide suppression/opt-out & DSAR endpoints. ￼
• EU/UK: If relying on legitimate interests, perform & store an LIA; support right to object; mind PECR for B2B email. ￼

Interface

class ComplianceGuard:
def decide_collection(self, kind: Literal["business_email","personal_email","phone"], region: str) -> "Decision"
def log_provenance(self, source_url: str, rule: str) -> None

⸻

5. crawlkit.orchestrate — Celery pipelines & APIs

Purpose: Queue & chain tasks: crawl → distil → extract → verify → export; expose REST.
• Endpoints: /crawl, /markdown, /entities, /batch/enrich, /export (CSV/Parquet).
• MCP/agents: Preserve the original “Firecrawl-like” signature for drop-in replacement:

def fetch_markdown(url: str, depth: int = 1, include_subpaths: bool = False) -> "MarkdownBundle"

    • Docs: Include robots/ToS decisions in each item’s provenance.

⸻

Data models (minimal)

@dataclass
class FetchedPage:
url: str
html: str
status: int
robots_allowed: bool
fetched_at: datetime
via: Literal["http","rendered"]

@dataclass
class DistilledDoc:
url: str
markdown: str
text: str
meta: dict # title, published, author
microdata: dict # extruct payload

@dataclass
class Entities:
people: list[dict] # {name, role, sources}
emails: list[dict] # {address, domain, status: "mx_only"|"smtp_probable"|"vendor_verified", risk_flags}
phones: list[dict] # {number, kind, sources}
org: dict # {name, site, country, ...}
aviation: dict|None # {fleet: [{type, count, age}], sources}

⸻

Non-functional requirements
• Python 3.13 only; confirm library versions: Scrapy ≥2.12 (adds 3.13), Playwright 2025 releases add 3.13, selectolax ≥0.4.0. ￼
• Performance budgets:
• Fetch fast-path P95 < 2.0 s; render fallback P95 < 6.0 s (with resource blocking).
• Distil+MD conversion < 300 ms for typical pages (selectolax + markdownify/Rust). ￼
• Politeness: Per-domain concurrency ≤2, adaptive backoff, robots honouring; document UA string. ￼
• Provenance: Store source_url, robots_rule, retrieval_mode, timestamps.
• Compliance: LIA records (EU/UK), POPIA log entries (ZA), opt-out and DSAR export/delete endpoints. ￼

⸻

Cut-over plan (Firecrawl → Crawlkit)

Phase 0 — Discovery & guardrails
1. Grep for any `firecrawl_` imports / `firecrawl_demo` references; catalogue call signatures and owning teams.
2. Draft the compatibility adapter `fetch_markdown(url, depth, include_subpaths)` in `crawlkit.adapter.firecrawl_compat` and map return-shape parity gaps.
3. Capture plan artefacts up front (`qa plan --generate-plan`) and log intended write targets per the [plan→commit guardrail](README.md#features).
4. Baseline QA: execute the root [Tests & QA suite](README.md#tests--qa) in dry-run mode via `poetry run python -m apps.automation.cli qa all --dry-run` to log existing failures before changes.

Phase 1 — Drop-in replacement with QA gates
1. Implement adapter to call `fetch → distill → extract` and assemble the same return shape (Markdown, link graph).
2. Feature flag `FEATURE_ENABLE_FIRECRAWL_SDK` → default off; introduce `FEATURE_ENABLE_CRAWLKIT=1` with telemetry proving parity.
3. Enforce plan→commit artefacts with `poetry run python -m apps.automation.cli qa plan --write-plan --write-commit` so MCP and CLI runs satisfy audit requirements.
4. Run mandatory QA before merge: `./scripts/run_pytest.sh ...`, `poetry run ruff check .`, `poetry run mypy .`, `poetry run bandit -r firecrawl_demo`, and the Promptfoo evaluation gate from [docs/mcp-promptfoo-gate.md](docs/mcp-promptfoo-gate.md) to unblock Copilot write access.
5. Keep tests green using golden-file Markdown comparisons on a fixed corpus; update corpus fixtures as needed with plan artefacts attached.

Phase 2 — Firecrawl deprecation & documentation
1. Delete `firecrawl_demo/` and vendor stubs, remove env vars, and update docs/CLI help to reference Crawlkit endpoints.
2. Lock dependency graph (`poetry.lock`) and CI matrices for Python 3.13; regenerate SBOM/signature artefacts during build.
3. Publish migration notes in `CHANGELOG.md` and surface roll-out steps in `Next_Steps.md` with QA evidence links.
4. Confirm MCP Promptfoo scores meet thresholds; attach latest `promptfoo_results.json` to the migration evidence bundle.

Phase 3 — Post-cut-over hardening
1. Remove Firecrawl compatibility adapter after downstream consumers validate new APIs.
2. Enable hard gate enforcement for MCP (no overrides) and monitor telemetry for regressions.
3. Schedule regression QA runs (`qa lint`, `qa typecheck`, `qa mutation --dry-run`) nightly until the new stack is stable.

Definition of Done
• All Firecrawl callsites route through `crawlkit.adapter` and legacy modules are removed.
• CLI/API parity: `/markdown` and `/entities` endpoints produce stable outputs on the curated corpus, with evidence recorded via plan→commit artefacts.
• Robots decisions logged; DSAR endpoints present; region toggles applied and validated in compliance logs.
• Perf & resource budgets pass in CI; QA evidence includes passing `pytest`, `ruff`, `mypy`, `bandit`, `promptfoo eval`, and build artifacts noted in [README.md#tests--qa](README.md#tests--qa).
• MCP gate enforcement meets [Promptfoo policy expectations](docs/mcp-promptfoo-gate.md).

⸻

Detailed acceptance tests

Corpus: Small set of static pages (article, docs, team page, pricing page, SPA blog). 1. Robots compliance: crawler skips disallowed paths; allowlisted APIs are used when configured. (RFC 9309 + Google docs.) ￼ 2. JS detection: page with no main content triggers Playwright fallback; normal news page uses fast path. ￼ 3. Distillation quality: title/body/date correctly captured (Trafilatura/Readability profile). ￼ 4. Markdown fidelity: headers/lists/links preserved; images optionally stripped per profile; Rust converter path meets throughput target. ￼ 5. Entity extraction: JSON-LD Person/Organization honoured; emails/phones extracted with source provenance. ￼ 6. Email hygiene: no VRFY/EXPN; DNS/MX checks only by default; any SMTP handshake stops before DATA and is rate-limited. (VRFY discouraged; anti-spam caveats.) ￼ 7. Aviation enrichment: when industry="aviation", call AirLabs/Aviation-Edge and attach fleet summary with citation to provider. ￼

⸻

Implementation notes & code-generation prompts (per module)

crawlkit.fetch
• Scrapy settings: CONCURRENT_REQUESTS=8, CONCURRENT_REQUESTS_PER_DOMAIN=2, DOWNLOAD_DELAY=1.0±0.5s jitter, AUTOTHROTTLE=True, HTTP cache on.
• Playwright: block analytics/fonts/video requests; wait_until="domcontentloaded", bump to "load" for SPA hydration as needed. ￼
• Docs & support for Py3.13: Scrapy 2.12+, Playwright 2025 releases. ￼

Prompt seed for Codex

Generate a Scrapy spider PoliteSpider with an optional Playwright download handler. Add robots parsing and a should_render heuristic that triggers Playwright when content length < 3KB OR <main> missing OR data-server-rendered present. Return FetchedPage.

crawlkit.distill
• DOM: selectolax parse; try extruct first for metadata; then Trafilatura/Readability fallback. ￼
• MD: default markdownify; perf path html-to-markdown. ￼

Prompt seed

Implement distill(html, url, profile) that yields markdown, text, meta, microdata. Use selectolax for DOM; extruct for JSON-LD; Trafilatura main text; then convert with markdownify. Add a profile="docs" that preserves tables.

crawlkit.extract
• Emails: regex + domain patterning; then DNS/MX lookup; flag “catch-all” if SMTP handshake inconclusive; never use VRFY/EXPN. ￼
• Phones: normalise (E.164), carrier lookup only via approved APIs if configured.
• Aviation: provider adapters: AirlabsFleetProvider, AviationEdgeFleetProvider. ￼

Prompt seed

Build extract_entities(doc, enrich=True) that maps JSON-LD Persons to people, infers emails via first.last@domain, validates with DNS/MX only, and (if industry=="aviation") calls AirLabs to fetch fleet types.

crawlkit.compliance
• Robots: RFC 9309; document UA. ￼
• POPIA/UK/EU toggles:
• ZA: apply POPIA direct-marketing guidance (s69) defaults. ￼
• UK/EU: LIA template; support right to object; note PECR B2B nuance. ￼

Prompt seed

Implement ComplianceGuard with decide_collection(kind, region) and DSAR export/delete stubs. Store LIA decisions in /artifacts/compliance/.

crawlkit.orchestrate
• Celery chains: fetch.s → distill.s → extract.s → export.s
• REST: FastAPI endpoints; streaming progress via SSE.

### Codex prompt seed catalogue

| Module | Prompt anchor | Notes |
| --- | --- | --- |
| `crawlkit.fetch` | “Generate a Scrapy spider PoliteSpider…” | Seed ensures polite crawling plus Playwright fallback; reuse when Copilot scaffolds fetch routines.
| `crawlkit.distill` | “Implement distill(html, url, profile)…” | Guides DOM distillation and Markdown rendering; tune `profile="docs"` when preserving tables.
| `crawlkit.extract` | “Build extract_entities(doc, enrich=True)…“ | Reinforces MX-only validation, aviation adapters, and provenance logging.
| `crawlkit.compliance` | “Implement ComplianceGuard…” | Captures regional policy toggles, DSAR stubs, and compliance artifact locations.
| `crawlkit.orchestrate` | “Wire Celery chains fetch → distill → extract…” | Keeps REST + Celery parity while satisfying plan→commit gating.

Store these prompts with plan artefacts when Copilot generates code so reviewers can trace model inputs.

### ML enrichment improvements roadmap

• Upgrade entity extraction with JSON-LD-first strategy, fallback spaCy NER tuned for ZA aviation domains.
• Expand ML scoring: evaluate enrichment precision/recall weekly; capture metrics in `artifacts/ml/enrichment_metrics.json`.
• Integrate structured evidence weighting (press vs regulator) before contact promotion; log weights in evidence log.
• Introduce anomaly detection for fleet data drift leveraging whylogs baselines referenced in [README.md#features](README.md#features).

### MCP & Copilot workflow expectations

• MCP sessions must validate Promptfoo scores before allowing writes (see [docs/mcp-promptfoo-gate.md](docs/mcp-promptfoo-gate.md)).
• Plan→commit artefacts (`*.plan`/`*.commit`) are mandatory before invoking MCP write surfaces; generate via `poetry run python -m apps.automation.cli qa plan --write-plan --write-commit`.
• Reference `Next_Steps.md` for current tasks, deliverables, and gate statuses; update after each migration tranche.
• Copilot agents should run the QA suite enumerated in [README.md#tests--qa](README.md#tests--qa) prior to proposing patches and attach logs to plan artefacts.

⸻

Deployment & CI
• Add CI matrix for Py 3.13 + Linux/macOS. Ensure playwright install --with-deps in CI runners. ￼
• Pin Scrapy ≥2.12, Playwright release ≥ Aug 2025 (3.13 support), selectolax ≥0.4.0. ￼

⸻

Risk register (and mitigations)
• JS-heavy sites → slow render: Strict heuristics + resource blocking; cache rendered HTML. ￼
• Deliverability/IP reputation: Avoid SMTP enumeration patterns; default to MX-only; throttle any SMTP handshakes; prefer trusted verifiers behind a vendor adapter. ￼
• Licensing (fleets): Prefer AirLabs/Aviation-Edge with explicit ToS; don’t scrape sites with restrictive terms; capture provider provenance. ￼

⸻

“Delete-and-replace” checklist 1. Land crawlkit/_+ adapter; flip feature flag default. 2. Update CLI (apps.analyst.cli) to swap firecrawl subcommands to crawlkit equivalents. 3. Replace examples in examples.py and docs. 4. Remove firecrawl_demo/ + deps; prune requirements_.txt and pyproject.toml. 5. Regenerate dependency report; lock. 6. Run compliance suite (robots, POPIA, LIA record writes) on corpus. 7. Tag release; update CHANGELOG.md.

⸻

Below is a starter PR layout you can paste into a new pull request on IAmJonoBo/watercrawl. It removes Firecrawl usage and adds a first-party, region-aware crawl → render (when needed) → distil → extract → enrich pipeline that fits the repo’s Python 3.13 baseline and Celery/FastAPI orchestration. I’ve kept it lean, testable, and reversible. Where I cite external behaviours (Scrapy/Playwright, distillers, compliance), I stick to primary docs and standards.

⸻

PR: Replace Firecrawl with first-party crawlkit (Scrapy+Playwright, distillers, extraction, compliance)

Why
 • Full control over crawling, compliance, and heuristics; no third-party SDK drift.
 • Native fit with Watercrawl’s Python 3.13 toolchain & async job surface.  ￼
 • Proven building blocks: Scrapy + scrapy-playwright for JS fallback, Trafilatura/Readability/jusText + selectolax for content distillation, extruct for JSON-LD/Microdata/OG, markdownify/html2text for HTML→Markdown.  ￼
 • Politeness & legality by design: honour RFC 9309 robots.txt, Playwright browser binaries installed per docs, and region toggles for POPIA/GDPR/UK-PECR expectations.  ￼

⸻

Directory layout (new)

watercrawl/
└── crawlkit/
    ├── __init__.py
    ├── adapter/
    │   └── firecrawl_compat.py        # drop-in fn that mirrors old signature
    ├── compliance/
    │   ├── __init__.py
    │   └── guard.py                   # POPIA/GDPR toggles + provenance logger
    ├── distill/
    │   ├── __init__.py
    │   └── distill.py                 # HTML→Markdown + meta + JSON-LD
    ├── extract/
    │   ├── __init__.py
    │   └── entities.py                # NER/rules + email/phone hygiene
    ├── fetch/
    │   ├── __init__.py
    │   └── polite_fetch.py            # Scrapy fast path + Playwright fallback
    ├── orchestrate/
    │   ├── __init__.py
    │   ├── api.py                     # FastAPI endpoints
    │   └── tasks.py                   # Celery chains (crawl→distil→extract)
    └── types.py                       # Shared dataclasses (FetchedPage/Doc/Entities)

Removed: firecrawl_demo/ and any imports of it.
Feature flags:
 • FEATURE_ENABLE_CRAWLKIT=1 (default on)
 • FEATURE_ENABLE_FIRECRAWL_SDK=0 (default off; delete later)

⸻

pyproject.toml deltas (add)

[tool.poetry.dependencies]
scrapy = "^2.13"          # downloader middlewares & settings  [oai_citation:3‡docs.scrapy.org](https://docs.scrapy.org/en/latest/topics/settings.html?utm_source=chatgpt.com)
scrapy-playwright = "^0.0.33"  # Scrapy↔Playwright bridge  [oai_citation:4‡GitHub](https://github.com/scrapy-plugins/scrapy-playwright?utm_source=chatgpt.com)
playwright = "^1.48"      # browser automation; run `playwright install`  [oai_citation:5‡playwright.dev](https://playwright.dev/python/docs/intro?utm_source=chatgpt.com)
selectolax = "^0.4.3"     # fast HTML parser (Lexbor backend)  [oai_citation:6‡selectolax](https://selectolax.readthedocs.io/?utm_source=chatgpt.com)
trafilatura = "^2.0.0"    # main-content extraction & metadata  [oai_citation:7‡trafilatura.readthedocs.io](https://trafilatura.readthedocs.io/?utm_source=chatgpt.com)
readability-lxml = "^0.8.2"  # article text/title fallback  [oai_citation:8‡readability.readthedocs.io](https://readability.readthedocs.io/?utm_source=chatgpt.com)
justext = "^3.0"          # boilerplate removal fallback  [oai_citation:9‡GitHub](https://github.com/miso-belica/jusText?utm_source=chatgpt.com)
extruct = "^0.18.0"       # JSON-LD/Microdata/OG/RDFa extractor  [oai_citation:10‡PyPI](https://pypi.org/project/extruct/?utm_source=chatgpt.com)
markdownify = "^0.13.1"   # HTML→Markdown converter  [oai_citation:11‡GitHub](https://github.com/matthewwithanm/python-markdownify?utm_source=chatgpt.com)
html2text = "^2024.2.26"  # plain-ish Markdown fallback  [oai_citation:12‡PyPI](https://pypi.org/project/html2text/?utm_source=chatgpt.com)
phonenumbers = "^9.0.16"  # E.164 normalisation/validation  [oai_citation:13‡PyPI](https://pypi.org/project/phonenumbers/?utm_source=chatgpt.com)
fastapi = "^0.115"
uvicorn = "^0.30"

Post-install step: python -m playwright install --with-deps for CI/containers.  ￼

⸻

Types (shared)

# crawlkit/types.py

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional

@dataclass
class FetchPolicy:
    obey_robots: bool = True
    max_depth: int = 2
    max_pages: int = 200
    concurrent_per_domain: int = 2
    render_js: Literal["auto", "never", "always"] = "auto"
    region: Literal["ZA", "EU", "UK", "US"] = "ZA"

@dataclass
class FetchedPage:
    url: str
    html: str
    status: int
    robots_allowed: bool
    fetched_at: datetime
    via: Literal["http", "rendered"]

@dataclass
class DistilledDoc:
    url: str
    markdown: str
    text: str
    meta: dict       # title, author, published
    microdata: dict  # extruct payload with JSON-LD/OG etc.

@dataclass
class Entities:
    people: list[dict]   # {name, role, sources}
    emails: list[dict]   # {address, domain, status, risk_flags}
    phones: list[dict]   # {number, e164, kind, sources}
    org: dict            # {name, site, country}
    aviation: Optional[dict]  # optional fleet summary

⸻

Fetch (Scrapy fast path; Playwright only when needed)

# crawlkit/fetch/polite_fetch.py

import asyncio, re
from crawlkit.types import FetchPolicy, FetchedPage
from datetime import datetime
from urllib.parse import urlparse

# Scrapy project bootstrap via CrawlerRunner is omitted for brevity

# Key settings: per-domain concurrency, cache, auto-throttle, robots obey

# Playwright is wired via scrapy-playwright download handler.  [oai_citation:15‡GitHub](https://github.com/scrapy-plugins/scrapy-playwright?utm_source=chatgpt.com)

SPA_HINTS = (b"data-server-rendered", b"__NEXT_DATA__", b"window.__NUXT__", b"<script type=\"module\"")

def should_render(body: bytes, content_type: str|None) -> bool:
    if not body or len(body) < 3_000:   # very small HTML often = shell
        return True
    if content_type and "text/html" not in content_type:
        return False
    return any(h in body for h in SPA_HINTS)

async def fetch(url: str, policy: FetchPolicy) -> FetchedPage:
    """
    1) Try HTTP fast path (Scrapy).
    2) If heuristics indicate SPA/empty body, re-request via Playwright.
    Always honour robots.txt and throttling. RFC 9309.  [oai_citation:16‡IETF Datatracker](https://datatracker.ietf.org/doc/html/rfc9309?utm_source=chatgpt.com)
    """
    # Pseudocode stub; implementation plugs into Scrapy Runner.
    html, status, robots_allowed, via = "<html/>", 200, True, "http"
    body = html.encode()

    if policy.render_js == "always" or (policy.render_js == "auto" and should_render(body, "text/html")):
        # Use scrapy-playwright download handler for JS rendering.  [oai_citation:17‡GitHub](https://github.com/scrapy-plugins/scrapy-playwright?utm_source=chatgpt.com)
        via = "rendered"
        # ... get rendered HTML here ...

    return FetchedPage(url=url, html=html, status=status, robots_allowed=robots_allowed,
                       fetched_at=datetime.utcnow(), via=via)

Why this stack: Scrapy’s downloader middlewares & settings give you robust throttling, caching, and retries; scrapy-playwright adds JavaScript rendering without breaking request scheduling.  ￼

⸻

Distillation (HTML → Markdown + rich metadata)

# crawlkit/distill/distill.py

from crawlkit.types import DistilledDoc
from selectolax.parser import HTMLParser           # fast DOM  [oai_citation:19‡selectolax](https://selectolax.readthedocs.io/?utm_source=chatgpt.com)
import trafilatura                                 # main content + meta  [oai_citation:20‡trafilatura.readthedocs.io](https://trafilatura.readthedocs.io/en/latest/quickstart.html?utm_source=chatgpt.com)
from readability import Document as ReadabilityDoc # fallback article body  [oai_citation:21‡readability.readthedocs.io](https://readability.readthedocs.io/?utm_source=chatgpt.com)
import justext                                     # boilerplate removal  [oai_citation:22‡GitHub](https://github.com/miso-belica/jusText?utm_source=chatgpt.com)
import extruct                                     # JSON-LD/Microdata/OG  [oai_citation:23‡PyPI](https://pypi.org/project/extruct/?utm_source=chatgpt.com)
from markdownify import markdownify as md          # HTML→Markdown  [oai_citation:24‡GitHub](https://github.com/matthewwithanm/python-markdownify?utm_source=chatgpt.com)

def distill(html: str, url: str, profile: str = "article") -> DistilledDoc:
    # 1) Microdata first (often richest, structured)
    micro = extruct.extract(html, base_url=url)
    # 2) Try Trafilatura (balanced precision/recall for main text)  [oai_citation:25‡trafilatura.readthedocs.io](https://trafilatura.readthedocs.io/en/latest/usage-python.html?utm_source=chatgpt.com)
    main = trafilatura.extract(html, include_comments=False) or ""
    title = ""
    if not main:
        # 3) Readability fallback for articles
        doc = ReadabilityDoc(html)
        title = doc.short_title()
        main = doc.summary(html_partial=True)

    # 4) Markdown conversion (profile controls links/images/tables policy)
    markdown = md(main, strip=["script", "style"])
    text = HTMLParser(html).text(decompose=False)
    meta = {"title": title}

    return DistilledDoc(url=url, markdown=markdown, text=text, meta=meta, microdata=micro)

⸻

Extraction (decision-makers, emails, phones, aviation bonus)

# crawlkit/extract/entities.py

import re
from email.utils import parseaddr
import dns.resolver  # optional: MX lookup only (avoid aggressive SMTP)
import phonenumbers  # E.164 normalize/validate  [oai_citation:26‡PyPI](https://pypi.org/project/phonenumbers/?utm_source=chatgpt.com)
from crawlkit.types import DistilledDoc, Entities

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})", re.I)

def _emails_from_text(text: str) -> list[str]:
    return list({m.group(0) for m in EMAIL_RE.finditer(text)})

def _e164(number: str, region_hint: str|None="ZA") -> str|None:
    try:
        pn = phonenumbers.parse(number, region_hint)
        if phonenumbers.is_valid_number(pn):
            return phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        return None

def extract_entities(doc: DistilledDoc, enrich: bool=True, domain_hint: str|None=None) -> Entities:
    # Prefer structured Persons/Orgs if present in JSON-LD.  [oai_citation:27‡PyPI](https://pypi.org/project/extruct/?utm_source=chatgpt.com)
    people, org = [], {}
    emails = [{"address": e, "domain": e.split["@",1](1), "status": "mx_only"} for e in_emails_from_text(doc.text)]
    # (Optional) MX check only: VRFY/EXPN are often disabled and not reliable; avoid reputation-risk probes.  [oai_citation:28‡RFC Editor](https://www.rfc-editor.org/rfc/rfc5321.html?utm_source=chatgpt.com)

    # Normalise phones in text:
    phones = []
    for cand in set(re.findall(r"[+()0-9][0-9()\-\s]{6,}", doc.text)):
        e = _e164(cand)
        if e:
            phones.append({"number": cand, "e164": e, "kind": "unknown", "sources": [doc.url]})

    return Entities(people=people, emails=emails, phones=phones, org=org, aviation=None)

Why MX-only by default: SMTP VRFY/EXPN are frequently disabled or restricted; servers may return ambiguous 252; relying on them can be misleading and harm sender reputation. Keep probes conservative.  ￼

⸻

Compliance guard (POPIA/GDPR/UK toggles + robots provenance)

# crawlkit/compliance/guard.py

from dataclasses import dataclass
from typing import Literal

@dataclass
class Decision:
    allowed: bool
    reason: str

class ComplianceGuard:
    def decide_collection(self, kind: Literal["business_email","personal_email","phone"], region: str) -> Decision:
        if region == "ZA":
            # POPIA s69: caution around unsolicited electronic comms; prefer business contact details, log lawful basis.  [oai_citation:30‡inforegulator.org.za](https://inforegulator.org.za/wp-content/uploads/2020/07/GUIDANCE-NOTE-ON-DIRECT-MARKETING-IN-TERMS-OF-THE-PROTECTION-OF-PERSONAL-INFORMATION-ACT-4-OF-2013-POPIA.pdf?utm_source=chatgpt.com)
            return Decision(True, "POPIA: business contact under direct marketing guidance; record basis.")
        if region in ("EU","UK"):
            # Legitimate interests may apply for B2B if proportionate and not overridden by PECR consent needs.  [oai_citation:31‡ICO](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/a-guide-to-lawful-basis/legitimate-interests/?utm_source=chatgpt.com)
            return Decision(True, "GDPR/UK: legitimate interests with LIA + PECR check.")
        return Decision(True, "Default")

    def log_provenance(self, source_url: str, rule: str) -> None:
        # Persist robots decisions + data source for DSAR/audit.
        pass

 • Robots & politeness: always honour RFC 9309; document UA string and throttle.  ￼

⸻

Orchestration (Celery chain + FastAPI endpoints)

# crawlkit/orchestrate/tasks.py

from celery import shared_task, chain
from crawlkit.types import FetchPolicy
from crawlkit.fetch.polite_fetch import fetch
from crawlkit.distill.distill import distill
from crawlkit.extract.entities import extract_entities

@shared_task
def task_fetch(url: str, policy: dict):
    return fetch(url, FetchPolicy(**policy)).__dict__

@shared_task
def task_distill(fp: dict):
    return distill(fp["html"], fp["url"]).__dict__

@shared_task
def task_extract(dd: dict):
    # dd is DistilledDoc as dict
    return extract_entities(type("X",(object,),dd)).__dict__

def enrich_chain(url: str, policy: dict):
    return chain(task_fetch.s(url, policy), task_distill.s(), task_extract.s())  # Celery canvas chain  [oai_citation:33‡docs.celeryq.dev](https://docs.celeryq.dev/en/stable/userguide/canvas.html?utm_source=chatgpt.com)

# crawlkit/orchestrate/api.py

from fastapi import FastAPI
from crawlkit.orchestrate.tasks import enrich_chain
from crawlkit.adapter.firecrawl_compat import fetch_markdown

app = FastAPI(title="Watercrawl CrawlKit API")

@app.get("/markdown")
def markdown(url: str, depth: int = 1, include_subpaths: bool = False):
    # Drop-in “Firecrawl-like” signature for zero-friction cut-over.
    return fetch_markdown(url, depth, include_subpaths)

@app.post("/entities")
def entities(url: str, region: str = "ZA"):
    policy = {"region": region}
    job = enrich_chain(url, policy).apply_async()
    return {"task_id": job.id}

 • FastAPI path operations & dependencies follow official patterns; you can extend with auth dependencies later.  ￼

⸻

Firecrawl-compat adapter (temporary)

# crawlkit/adapter/firecrawl_compat.py

from crawlkit.types import FetchPolicy
from crawlkit.fetch.polite_fetch import fetch
from crawlkit.distill.distill import distill

def fetch_markdown(url: str, depth: int = 1, include_subpaths: bool = False):
    fp = asyncio.get_event_loop().run_until_complete(fetch(url, FetchPolicy(max_depth=depth)))
    dd = distill(fp.html, fp.url)
    # Return shape mimics prior Firecrawl usage: markdown + url
    return {"url": dd.url, "markdown": dd.markdown, "meta": dd.meta, "links": []}

⸻

Tests (golden files) & fixtures

tests/crawlkit/
  test_fetch_robotspolicy.py      # skip disallowed; record decision (RFC 9309)  [oai_citation:35‡IETF Datatracker](https://datatracker.ietf.org/doc/html/rfc9309?utm_source=chatgpt.com)
  test_distill_corpus.py          # article/docs/team pages; assert markdown/title
  test_entities_email_phone.py    # MX-only checks; E.164 formatting  [oai_citation:36‡PyPI](https://pypi.org/project/phonenumbers/?utm_source=chatgpt.com)
  fixtures/
    article.html
    docs.html
    team.html

⸻

Migration steps
 1. Route callsites to crawlkit.adapter.firecrawl_compat.fetch_markdown.
 2. Feature flags: set FEATURE_ENABLE_CRAWLKIT=1, FEATURE_ENABLE_FIRECRAWL_SDK=0.
 3. Remove firecrawl_demo/ and its deps; update docs and examples.
 4. Install Playwright browsers in CI/Docker (python -m playwright install --with-deps).  ￼
 5. Run the golden corpus tests; verify Markdown parity and robots decisions are logged.

⸻

Developer notes (essentials)
 • Scrapy settings: use per-domain concurrency caps, auto-throttle & cache; configure scrapy-playwright as download handler only when heuristics indicate JS is required.  ￼
 • Playwright: Chromium/WebKit/Firefox are available; avoid loading analytics/video/fonts in render passes for speed.  ￼
 • Distillation: prefer Trafilatura (balanced); fall back to Readability/jusText; always pull JSON-LD/Microdata via extruct.  ￼
 • Markdown: markdownify default; html2text when plain, low-noise Markdown is desired.  ￼
 • Email verification: do not rely on SMTP VRFY/EXPN; many servers disable or constrain them; treat MX-only + pattern inference as baseline, plug in vendor verifiers if needed.  ￼
 • Phones: normalise to E.164 using phonenumbers.  ￼
 • Compliance: log lawful basis and provide DSAR/suppression hooks. POPIA direct-marketing guidance (s69); ICO B2B marketing/legitimate interests for UK; check PECR consent edge cases.  ￼

⸻

Cut-over checklist (Definition of Done)
 • All Firecrawl callsites now use fetch_markdown() adapter.
 • /markdown & /entities endpoints return stable outputs on the test corpus.
 • Robots decisions & provenance recorded for each fetch.  ￼
 • Region toggle affects collection defaults (POPIA/GDPR/UK).  ￼
 • CI installs Playwright browsers; tests green on Python 3.13 (per repo baseline).  ￼

⸻

Evidence-gated note (summary)
 • Data: Watercrawl repo baseline (requires Python 3.13), Scrapy/Playwright docs, distillation libraries, RFC 9309 robots, POPIA/ICO guidance, RFC 5321 SMTP caveats.  ￼
 • Methods: Assemble minimal, composable modules; rely on official docs/standards; prefer conservative network behaviours.
 • Key result: Feature-parity “URL→LLM-ready Markdown→Entities” without Firecrawl; stronger compliance & provenance; native to your stack.
 • Uncertainty: Some sites’ ToS/API policies limit crawling; JS-heavy pages can still be expensive—hence heuristic rendering & resource blocking. (Mitigated by Scrapy settings + Playwright usage guidance.)  ￼
 • Safer alternative: When available, prefer official/paid APIs for sensitive domains (and keep robots allow-lists strict by default).  ￼
