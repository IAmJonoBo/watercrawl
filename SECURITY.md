# Security Policy

## Supported Versions

We actively support the following versions of the ACES Aerodynamics Enrichment Stack:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

The ACES Aerodynamics team takes security vulnerabilities seriously. We appreciate your efforts to responsibly disclose your findings.

### How to Report

**Please do NOT report security vulnerabilities through public GitHub issues.**

Instead, please report security vulnerabilities via email to:

📧 **security@acesaero.co.za**

Please include the following information in your report:

- Type of vulnerability (e.g., XSS, SQL injection, authentication bypass)
- Full paths of source file(s) related to the vulnerability
- Location of the affected source code (tag/branch/commit or direct URL)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the vulnerability, including how an attacker might exploit it

### What to Expect

- **Acknowledgment**: We will acknowledge receipt of your vulnerability report within 48 hours.
- **Assessment**: We will investigate and validate the reported vulnerability within 7 days.
- **Updates**: We will keep you informed of our progress at least every 7 days.
- **Resolution**: Once fixed, we will notify you and publicly disclose the vulnerability (crediting you if desired).

### Vulnerability Disclosure Process

1. **Report submitted** → Security team notified
2. **Triage & validation** → 7 days
3. **Fix development** → Based on severity
4. **Fix deployed** → Coordinated disclosure
5. **Public disclosure** → CVE published if applicable

### Security Best Practices

When using the ACES Aerodynamics Enrichment Stack:

- **Secrets Management**: Never commit credentials to version control. Use environment variables or secrets managers (AWS Secrets Manager, Azure Key Vault).
- **Data Privacy**: Ensure POPIA compliance when handling personal information (POPIA s69 limits apply).
- **Evidence Sources**: Require at least 2 independent sources (≥1 official/regulatory) for all enrichment changes.
- **Network Operations**: Keep `FEATURE_ENABLE_FIRECRAWL_SDK` disabled unless explicitly required and approved.
- **Contract Enforcement**: Enable Great Expectations, dbt, and Deequ checks to validate all curated datasets.
- **MCP Safety**: Enforce plan→commit workflow with `If-Match` preconditions for all write operations.

## Security Controls

This project implements multiple security layers:

- **Dependency Scanning**: Automated vulnerability scanning via GitHub Dependabot
- **Secret Scanning**: GitHub Secret Scanning with push protection enabled
- **Static Analysis**: Bandit security linting, CodeQL analysis
- **Supply Chain**: CycloneDX SBOM generation, Sigstore artifact signing
- **Code Signing**: Gitsign OIDC-backed commit signing
- **OpenSSF Scorecard**: Weekly security posture assessments (target ≥7/10)

## Compliance & Frameworks

- **NIST SSDF v1.1**: Secure Software Development Framework
- **OWASP ASVS L2**: Application Security Verification Standard
- **OWASP LLM Top-10**: LLM-specific security controls
- **SLSA Level 2**: Supply-chain Levels for Software Artifacts (aspirational)
- **POPIA**: Protection of Personal Information Act (South Africa)

## Related Documentation

- [Threat Model ADR](docs/adr/0003-threat-model-stride-mitre.md) - STRIDE/MITRE mappings
- [MCP Audit Policy](docs/mcp-audit-policy.md) - Write safety and audit logging
- [Data Quality Documentation](docs/data-quality.md) - Evidence and validation requirements
- [Security Summary](SECURITY_SUMMARY.md) - Recent hardening efforts and status

## Acknowledgments

We recognize and appreciate security researchers who help us maintain a secure platform. With your permission, we will credit you in our security advisories and release notes.

---

**Last Updated**: 2025-10-21  
**Contact**: security@acesaero.co.za  
**PGP Key**: Available upon request
