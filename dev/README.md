# Development Workspace

The `dev/` directory captures guidance, scaffolding, and notebooks for analyst and developer iterations. Use this space to
prototype adapters, rehearse lineage workflows, and document experiments that should never reach distribution builds.

Key principles:

- Treat this area as ephemeral. Anything promoted into production must move into the `app/` or `dist/` trees with the
  relevant quality gates.
- Codex agents may operate here, but every session must pass the Promptfoo smoke tests (`promptfoo eval codex/evals/promptfooconfig.yaml`) before tools are enabled.
- Document assumptions, toggles, and pending migrations so the Platform team can trace changes during Phase 2/3 hand-offs.
