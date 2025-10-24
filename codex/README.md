# Codex Developer Experience

This directory packages lightweight tooling so Codex agents can work against the ACES Aerodynamics stack with the same guardrails that analysts rely on.

## Structure

- `evals/` — Promptfoo scenarios for quick behavioural smoke tests of Codex plans and explanations.
- `tools/` — Reference documentation for attaching Model Context Protocol (MCP) servers.

## Usage

1. Install [promptfoo](https://www.promptfoo.dev/) locally: `npm install -g promptfoo`.
2. Run the deterministic smoke tests before granting Codex access: `promptfoo eval codex/evals/promptfooconfig.yaml`.
3. Review the MCP notes in `tools/mcp/README.md` when wiring Codex to the in-repo MCP server (`watercrawl.mcp.server`).

The scenarios intentionally mirror the compliance and evidence expectations that analysts follow so Codex recommendations stay within policy.
