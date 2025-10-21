# MCP Audit Log Policy

## Overview

This document defines the ownership, storage, retention, and access policies for MCP (Model Context Protocol) audit logs as required by the plan→diff→commit safety gate (WC-05).

## Scope

All MCP write operations that modify repository state, including:
- Code changes via `commit_patch` or equivalent
- Configuration updates
- Data transformations
- Evidence log modifications

## Audit Log Specification

### Log Format
- **Format**: Newline-delimited JSON (JSONL)
- **Location**: `data/logs/plan_commit_audit.jsonl` (relative to repository root)
- **Encoding**: UTF-8

### Required Fields

Each audit entry MUST contain:

```json
{
  "timestamp": "2025-10-21T16:00:00.000Z",
  "actor": "copilot-agent-id or user-id",
  "operation": "commit_patch | plan_review | etc",
  "plan_artifact": "path/to/*.plan",
  "commit_artifact": "path/to/*.commit",
  "if_match": "etag-value-or-hash",
  "rag_metrics": {
    "faithfulness": 0.95,
    "context_precision": 0.92
  },
  "tool": "tool-name",
  "inputs": {
    "summarized": "input-summary-max-1kb"
  },
  "result": "success | failure | blocked",
  "block_reason": "optional-reason-if-blocked"
}
```

## Ownership and Responsibility

### Primary Owner
- **Team**: Platform/Security
- **Contact**: Security team lead
- **Escalation**: Platform team lead

### Responsibilities
1. **Platform Team**:
   - Maintain audit log infrastructure
   - Ensure log writes are atomic and durable
   - Monitor disk space and rotation
   - Implement log shipping to centralized observability (future)

2. **Security Team**:
   - Define retention policies
   - Review audit logs for anomalies
   - Respond to security incidents involving MCP operations
   - Conduct quarterly access reviews

## Storage

### Location
- **Development/Local**: `data/logs/plan_commit_audit.jsonl` in repository root
- **CI/CD**: Artifact upload to workflow run artifacts
- **Production**: To be determined based on deployment target (see Assumptions)

### Backup Strategy
- Local: Committed to git as part of evidence trail (subject to size limits)
- CI/CD: Stored as GitHub Actions artifacts (90-day retention default)
- Production: TBD - requires selection of observability backend

### Rotation Policy
- **File Size Limit**: 10 MB per file
- **Rotation**: Automatic when size limit reached
- **Naming**: `plan_commit_audit_YYYYMMDD_HHMMSS.jsonl`
- **Compressed Archives**: Rotated files moved to `data/logs/archive/` and gzip compressed

## Retention

### Retention Periods
- **Active logs**: 90 days (aligned with GitHub Actions artifact retention)
- **Archived logs**: 1 year
- **Compliance logs**: 7 years (if required by regulatory requirements)

### Deletion Process
1. Automated: Logs older than retention period are eligible for deletion
2. Manual: Security team approval required for early deletion
3. Legal hold: Logs subject to legal hold are exempt from deletion

## Access Controls

### Read Access
- **Development**: Repository collaborators with read access
- **CI/CD**: Workflow runs with repository access token
- **Production**: Limited to Platform and Security teams

### Write Access
- **Automated**: MCP server process (via plan→commit guard)
- **Manual**: Prohibited - all writes must be programmatic

### Audit of Audits
- Log access is itself logged in system audit trail
- Quarterly reviews of access patterns

## Monitoring and Alerting

### Metrics
- Audit log write failures
- Log rotation events
- Disk space utilization
- Anomalous operation patterns (e.g., high frequency, unusual actors)

### Alerts
- **Critical**: Audit log write failure (page Security team)
- **Warning**: Disk space >80% (notify Platform team)
- **Info**: Daily summary of MCP operations (email Security team)

## Compliance

### Standards Alignment
- **NIST SSDF**: RV.1.1 (logging of security-relevant events)
- **OWASP SAMM**: Governance 1.2 (audit trail for privileged operations)
- **OWASP ASVS**: V9.1 (logging of security-sensitive events)

### Audit Requirements
- Logs MUST be tamper-evident (consider cryptographic signatures in future)
- Logs MUST be append-only
- Log access MUST be audited

## Review and Updates

- **Review Frequency**: Quarterly or when operational context changes
- **Last Reviewed**: 2025-10-21
- **Next Review**: 2026-01-21
- **Document Owner**: Platform/Security teams

## Assumptions and Open Items

1. **Deployment Target**: Storage location for production deployments TBD
   - Options: Cloud object storage (S3, Azure Blob), centralized logging (ELK, Splunk), lakehouse integration
   - Decision required by: M4 milestone (2025-12-05)

2. **Data Residency**: Compliance requirements for log storage location TBD
   - Consult legal/compliance team for POPIA requirements

3. **Centralized Logging**: Integration with observability platform TBD
   - Consider: Grafana Loki, ELK stack, Datadog, or vendor-specific solution

4. **Cryptographic Signing**: Future enhancement to ensure tamper-evidence
   - Investigate: Sigstore transparency log integration

## References

- [ADR-0003: Threat Model](adr/0003-threat-model-stride-mitre.md)
- [MCP Documentation](mcp.md)
- [Operations Runbook](operations.md)
- [Next Steps](../Next_Steps.md) - WC-05 gate requirements
