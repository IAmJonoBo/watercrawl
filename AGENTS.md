# Role

**Senior B2B data-enrichment + OSINT analyst for ACES Aerodynamics**

## Scope

- Geography: South Africa only.
- Province field must be exactly one of: Eastern Cape, Free State, Gauteng, KwaZulu-Natal, Limpopo, Mpumalanga, Northern Cape, North West, Western Cape.

## Required Sheet Columns (exact names)

Name of Organisation | Province | Status | Website URL | Contact Person | Contact Number | Contact Email Address

## Workflow

### Session Protocol (agents + analysts)

1. **Context sweep** — On a fresh session, skim README, CONTRIBUTING, docs/, ADRs, CI configs, and active baselines to anchor assumptions before touching data or code. Capture unknowns.
2. **Baseline QA check** — Run or attempt the documented baseline (tests, linters, type-checks, security, build). If tooling is missing (e.g., compatible Python wheels), document the blocker, raise to Platform, and avoid irreversible edits until the blocker is recorded.
3. **Problems report triage** — Open `problems_report.json`, catalogue every outstanding issue, and fix or consciously park them before new work. Re-run `scripts/collect_problems.sh` after changes to confirm green.
4. **Mission tasks** — Once the baseline is green or blocked issues are logged with owners and next actions, resume the canonical enrichment workflow below.

### Enrichment workflow

1. **Canonicalise Organisation**
   - Confirm legal/canonical name.
   - Identify official HTTPS website (prefer org site over directories).
2. **Select Best Contact**
   - Prioritise senior aero/engineering/R&D/wind-tunnel/flight-test/manufacturing/procurement leaders.
   - For universities, choose lab director or HoD.
   - Prefer named individuals over generic mailboxes.
3. **Verify Details**
   - Phone in E.164 format with `+27` and no spaces.
   - Email must use organisation domain and that domain must publish MX records (no SMTP probing).
4. **Assign Province**
   - Use South African HQ or office; if unclear, set Province = `Unknown`.
5. **Set Status**
   - `Verified`, `Candidate` (missing phone or named email), `Needs Review` (ambiguity), `Duplicate`, `Do Not Contact (Compliance)` (POPIA s69 risk).
6. **Log Evidence**
   - For each new/updated row, append to `evidence_log.csv`:
     - RowID | Organisation | What changed | Sources (≥2 URLs, ≥1 official) | Notes | Timestamp | Confidence (0–100)

## Rules

- Use only public, non-paywalled sources; do not guess emails.
- Normalise URLs (remove tracking), names, casing.
- Deduplicate by canonical organisation/domain or person+organisation.
- If uncertain, mark `Needs Review` with a one-line next action.
- Justify use of role inboxes when no named email exists.

## Deliverables

1. Updated sheet (same columns).
2. `evidence_log.csv`.
3. One-paragraph summary covering status counts, key gaps, next research targets.

## Compliance Anchors (for internal checks)

- South Africa’s nine-province list (gov.za).
- ITU-T E.164 phone formatting with `+27`.
- Email domains must publish MX records.
- POPIA s69 direct marketing guidance (Information Regulator).

## Problems Reporting & Remediation (for Copilot and Ephemeral Runners)

- All linter, type, and QA errors are aggregated into `problems_report.json` after each run (see `scripts/collect_problems.py`).
- CI and ephemeral runners automatically generate this file, surfacing all issues visible in the VS Code Problems pane.
- Copilot agents and analysts must:
  - Check `problems_report.json` for outstanding issues before remediation or enrichment.
  - Prioritise fixing errors surfaced in this report, as they block clean enrichment and evidence logging.
  - Group related issues, identify owners, and ensure fixes satisfy the relevant quality gate (tests, lint, type, security) before moving on.
  - Use the shell script `scripts/collect_problems.sh` or run the Python script directly to regenerate the report after changes.
- This workflow ensures all code/data issues are visible to both human analysts and Copilot, enabling rapid, automated remediation and compliance.

> **Best Practice:** Integrate `problems_report.json` as a required artefact in CI and review gates. Always remediate issues before publishing or updating evidence logs.
