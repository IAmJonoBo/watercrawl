---
title: "ADR 0003: Threat Model & STRIDE/MITRE Mapping"
---

- **Status:** Accepted
- **Date:** 2025-10-20
- **Decision Makers:** Security & Platform Architecture Guild
- **Context:**
  - Prior audits (see Red Team playbook §3.2) noted the absence of a formal threat model for the enrichment stack’s critical entrypoints (analyst CLI, MCP server, automation QA).
  - Plan→commit safeguards and LLM safety controls have been introduced, but the risk register lacked a canonical STRIDE analysis or linkage to MITRE ATT&CK techniques.
  - Upcoming roadmap items (WC-05/06) require traceable mitigations and recurring tabletop reviews aligned to vendor assessments and POPIA obligations.
- **Decision:**
  - Adopt STRIDE as the primary taxonomy for cataloguing risks across trust boundaries and map each scenario to high-signal MITRE ATT&CK techniques to drive control selection.
  - Capture the baseline threat model in this ADR, including a component matrix, mitigation status, and owners; update it alongside major architectural changes or on a quarterly cadence (tabletop review).
  - Integrate the threat model artefact into the MCP/plan→commit checklist so new surfaces cannot launch without explicit STRIDE/MITRE coverage.
- **Consequences:**
  - Security reviews, backlog prioritisation, and Next_Steps gating now reference a single artefact, reducing duplication in playbooks and audits.
  - New capabilities (e.g., streaming evidence sinks, Firecrawl SDK enablement) must add rows to the matrix before GA, ensuring early design reviews.
  - Runbooks and automated tooling can build on the codified mappings (e.g., Semgrep policies keyed by MITRE IDs, SOC alert routing) without re-deriving threat context.

## Component Threat Matrix

| Component / Boundary | STRIDE Categories | MITRE Techniques (examples) | Existing Controls | Planned Enhancements |
| --- | --- | --- | --- | --- |
| Analyst & Automation CLIs → Pipeline | Spoofing, Tampering, Repudiation | T1078 (Valid Accounts), T1565.002 (Stored Data Manipulation) | Plan→commit guard (plan & commit artefacts, `If-Match`), quality gate rejects unsafe enrichments, audit log JSONL | Policy-as-code enforcement for destructive commands, Semgrep policy for CLI diff review |
| MCP Server (JSON-RPC) | Spoofing, Elevation of Privilege, Repudiation | T1550 (Use of Web Credentials), T1210 (Exploitation of Remote Services) | Plan→commit enforcement for `enrich_dataset`, typed payload validation, LLM safety checks (prompt injection, blocked domains), audit logging | Signed MCP session manifests, automated fuzzing & replay tests, mutual auth for future network transport |
| Evidence Sinks & Lakehouse | Tampering, Information Disclosure, Denial of Service | T1565.001 (Data Manipulation), T1530 (Data from Cloud Storage), T1499 (Endpoint DoS) | Offline-first CSV sink, versioned manifests, drift alerts via whylogs, provenance bundles (OpenLineage, PROV-O) | Streaming sink authN/Z, continuous drift alert routing, storage-level immutability guarantees |
| Research Adapters & External Lookups | Tampering, Info Disclosure, Elevation of Privilege | T1595 (Active Scanning), T1190 (Exploit Public-Facing Apps) | Feature flags default to offline adapters, tenacity retry with throttling, no outbound network unless explicitly enabled | Adapter sandboxing (timeout/allowlists), telemetry for adapter failures, credential vault integration for third-party APIs |
| Secrets & Policy Providers | Spoofing, Information Disclosure, Repudiation | T1552 (Unsecured Credentials), T1485 (Data Destruction) | Secrets provider abstraction (ENV/AWS/Azure), policy plan (OPA), audit of plan→commit usage | Rotation playbooks with Sigstore attestations, automated secrets scanning & SBOM diff alerts |
| LLM Safety & Plan→Commit Policy | Tampering, Elevation of Privilege | T1609 (Container Administration), T1531 (Account Access Removal) | RAG score thresholds, prompt-injection heuristics, blocked keywords/domains, diff size enforcement | Ragas-based evaluation in CI, red-team automation covering OWASP LLM Top-10 scenarios |

## Review & Maintenance

- Annual tabletop exercises will rehearse MCP compromise, evidence tampering, and adapter exfiltration scenarios; outcomes update this ADR and Red Team playbook.
- STRIDE/MITRE mappings feed the risk log (Next_Steps §1) and CI guardrails: failing controls must be marked as “Needs Review” with linked mitigations.
- When introducing new surfaces (e.g., Backstage TechDocs, streaming evidence sinks), engineering teams add entries to the matrix before merging feature ADRs.
