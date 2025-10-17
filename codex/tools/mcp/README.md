# MCP servers for ACES Aerodynamics Codex agents

Codex can attach to the in-repo MCP server so agents can invoke the same validation and enrichment routines analysts use.

## Local server

```bash
poetry run python -m firecrawl_demo.mcp.server
```

This exposes JSON-RPC tools for validation, enrichment, and evidence export. Point Codex at the server by adding the following entry to `~/.codex/config.toml`:

```toml
[mcp_servers.watercrawl]
command = "poetry"
args = ["run", "python", "-m", "firecrawl_demo.mcp.server"]
```

Inspect active servers inside the Codex TUI with `/mcp`. Disable the server once the session finishes to avoid unintended writes.

## External context servers

Optional read-only helpers:

- `codex mcp add context7 -- npx -y @upstash/context7-mcp`
- `codex mcp add openterms -- npx -y @opentermsarchive/mcp`

Always review the provided tools and only grant access necessary for the task at hand.
