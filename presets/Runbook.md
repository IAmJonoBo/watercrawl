# ACES Aerodynamics — OSINT Enrichment Runbook (Lightweight, Frontier-Grade)

**Goal:** Fill missing fields accurately and compliantly for the sheet with columns  
`Name of Organisation | Province | Status | Website URL | Contact Person | Contact Number | Contact Email Address`  
while keeping costs at zero and running a local Firecrawl instance.

---

## 1) Scope & success criteria

- **Geography:** South Africa. Province ∈ {Eastern Cape, Free State, Gauteng, KwaZulu-Natal, Limpopo, Mpumalanga, Northern Cape, North West, Western Cape}.
- **Definition of Done (per non-duplicate row):** canonical org + valid province + HTTPS home page + named contact (if lawful) + phone in **+27** E.164 + deliverable on-domain email (MX present) + justified **Status** + evidence entry.

**Status options:** Verified | Candidate | Needs Review | Duplicate | Do Not Contact (Compliance).

---

## 2) Evidence standard (two-source rule)

Every changed/added row gets an evidence_log entry with ≥2 sources (≥1 official/regulatory) + timestamp + confidence.

- **90–100:** official + independent corroboration ≤12 months; clean MX; stable phone.
- **70–89:** official + credible secondary; minor gaps (e.g., role inbox only).
- **40–69:** partial triangulation or stale/ambiguous → **Needs Review**.

**Why:** Lateral reading and SIFT consistently outperform single-source reading for web claims. Bellingcat’s verification handbooks give low-friction OSINT hygiene.

---

## 3) Workflow (do not skip steps)

1. **Pre-register the plan (one paragraph):** objective; inclusion/exclusion; what counts as Verified/Candidate/Needs Review; province logic.
2. **Identify the canonical organisation:** official site → regulator/association → reputable press; only then directories. Resolve naming via domain/footer/address/leadership.
   - If ambiguous, mark **Needs Review** and state a one-line next action.
3. **Website & domain hygiene:** store HTTPS home; strip tracking. If multiple domains → choose the most official/current; otherwise **Needs Review**.
4. **Best contact (precision over volume):** prefer senior technical/ops (CFI/Engineering/Procurement/HoD). Prefer a named person to “info@”. If none public, keep **Candidate**.
5. **Contact verification:**
   - Phone → **+27XXXXXXXXX** (no spaces).
   - Email → on org domain **with MX** (non-invasive DNS check).
   - Government units or personal emails without a lawful basis → **Do Not Contact (Compliance)** (POPIA s69).
6. **Province:** HQ or SA office province. If unclear → **Unknown** and log reason.
7. **Set Status** strictly per rubric.
8. **Log evidence** (see §7 template).
9. **Quality gates** (see §5).

---

## 4) Firecrawl (local) — minimal presets & commands

Assume your self-hosted endpoint is `http://localhost:3002/v1`. Adjust as needed.

### 4.1 Map preset (discover key pages)

`presets/firecrawl_map.json`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "url": "https://EXAMPLE.co.za",
  "search": "",
  "sitemap": "include",
  "includeSubdomains": false,
  "limit": 80,
  "ignoreQueryParameters": true
}
```

**Run:**

```bash
curl -sS -X POST http://localhost:3002/v1/map   -H "Content-Type: application/json"   -d @presets/firecrawl_map.json > out/map_EXAMPLE.json
```

### 4.2 Scrape preset (pull contact/leadership pages)

`presets/firecrawl_scrape.json`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "url": "https://EXAMPLE.co.za/contact",
  "formats": ["markdown", "links"],
  "parsers": ["pdf"],
  "onlyMainContent": true,
  "includeTags": [],
  "excludeTags": [],
  "waitFor": 800,
  "actions": [{ "type": "scroll", "direction": "down" }],
  "mobile": false,
  "skipTlsVerification": false,
  "removeBase64Images": true,
  "storeInCache": true,
  "maxAge": 86400
}
```

**Run:**

```bash
curl -sS -X POST http://localhost:3002/v1/scrape   -H "Content-Type: application/json"   -d @presets/firecrawl_scrape.json > out/scrape_EXAMPLE.json
```

### 4.3 Crawl preset (optional, shallow)

`presets/firecrawl_crawl.json`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "url": "https://EXAMPLE.co.za",
  "includePaths": [
    "/about",
    "/contact",
    "/team",
    "/leadership",
    "/training",
    "/facult",
    "/engineering"
  ],
  "excludePaths": ["/privacy", "/terms", "/wp-json"],
  "maxDiscoveryDepth": 2,
  "sitemap": "include",
  "limit": 120,
  "allowExternalLinks": false,
  "allowSubdomains": false,
  "crawlEntireDomain": false,
  "delay": 500,
  "maxConcurrency": 3,
  "scrapeOptions": {
    "formats": ["markdown", "links"],
    "parsers": ["pdf"],
    "onlyMainContent": true,
    "waitFor": 800,
    "mobile": false,
    "skipTlsVerification": false,
    "removeBase64Images": true
  }
}
```

**Run:**

```bash
curl -sS -X POST http://localhost:3002/v1/crawl   -H "Content-Type: application/json"   -d @presets/firecrawl_crawl.json > out/crawl_EXAMPLE.json
```

---

## 5) Quality gates (clipboard-ready)

**Gate A — Canonicality**  
☑ URL is HTTPS and current official domain.  
☑ Name matches footer/regulator.  
☑ Wayback shows continuity or discrepancy is explained.

**Gate B — Contact integrity**  
☑ Named person aligned to our ICP. If none → **Candidate**.  
☑ Phone normalised to **+27** E.164.  
☑ Email on org domain with MX present (log “MX present @ time”).

**Gate C — Compliance**  
☑ POPIA s69 risk assessed; uncertain → **Do Not Contact (Compliance)** with one-line reason.

**Gate D — Evidence**  
☑ Two sources (≥1 official/regulator).  
☑ Timestamp + confidence recorded.

---

## 6) Data normalisation rules

- **Names:** use legal/canonical trading name; unify casing; remove tracking/UTM from URLs.
- **Phones:** `+27` followed by digits (no spaces). If an extension is necessary, note in the evidence log.
- **Emails:** on org domain; confirm MX.
- **Province:** choose HQ or SA office; else `Unknown` with reason.
- **Dedupe:** same canonical name/domain → mark later rows **Duplicate** and link RowIDs in evidence log.

---

## 7) Templates

### 7.1 evidence_log.csv (columns)

```text
RowID | Organisation | What changed | Sources (URLs) | Verification notes | Time stamp | Confidence
```

**Example row:**

```text
42 | Vulcan Aviation | Added named CFI email + phone; URL normalised |
https://www.flyvulcan.co.za/meet-the-team/ ; https://www.flyvulcan.co.za/contact/ |
Named person and email on-domain; phone reformatted to +27 | 2025-10-16 02:10:42Z | 95
```

### 7.2 relationships.csv (optional “free knowledge graph”)

```text
org | person | role | email_domain | phone | province | source_url1 | source_url2
```

---

## 8) Reasoning upgrades (no heavy tooling)

- **Self‑consistency sampling:** for ambiguous rows, draft 3 brief justifications with different search paths; accept only if they converge on same identity/contact.
- **Adversarial check:** ask “If this were wrong, what would contradict it?” then search for that (e.g., different domain on regulator page, recent rebrand).
- **Negative search:** “{org} rebrand”, “{org} new domain”, “{org} acquisition” within last 12–18 months.

---

## 9) Troubleshooting

- If a site is dynamic, add a small `waitFor` and one `scroll` action in the scrape preset.
- If Firecrawl returns partial content, scrape specific contact/team URLs instead of crawling.
- If Wayback is read‑only or rate‑limited, just note “Wayback unavailable” and proceed with other sources.

---

_Prepared: 2025-10-16 02:10:42Z_
