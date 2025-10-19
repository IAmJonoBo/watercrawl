# GitHub Copilot setup for this repository

This repository includes a GitHub Actions workflow used by GitHub Copilot's
coding agent to preconfigure its ephemeral development environment. The
workflow ensures the agent has preinstalled runtimes and dependencies so it can
run tests, linters and other tasks reliably.

File: `.github/workflows/copilot-setup-steps.yml`

Key points

- The job name MUST be `copilot-setup-steps` — GitHub uses this exact job name
  to run before Copilot starts.

- The workflow must exist on the repository's default branch (typically
  `main`) for Copilot to pick it up.

- Only a limited set of job fields may be customized: `steps`, `permissions`,
  `runs-on`, `services`, `snapshot`, and `timeout-minutes`.

What the included workflow does

- Checks out the repo (`actions/checkout@v5`).

- Sets up Python 3.13 and installs `poetry` and project dependencies (when
  `pyproject.toml` exists).

- Sets up Node.js 20 and runs `npm ci` when `package.json` exists.

- Prints basic version info so failures are easier to debug in the Actions UI.

Security considerations

- The workflow runs with minimal GitHub permissions (`contents: read`). Only
  grant additional permissions if strictly necessary.

- If you need to provide secrets or variables for Copilot to use (for example
  API keys), add them to the `copilot` environment in repository Settings →
  Environments → `copilot` and mark sensitive values as environment secrets.

- Do not embed secrets directly in the workflow file or repository.

Testing & validation

- After merging the workflow to `main`, run it manually from the Actions tab
  (it has `workflow_dispatch`) to validate the setup steps complete.

- When Copilot starts a session, the workflow will be executed and the steps
  will be visible in the Copilot session logs.

Troubleshooting

- If the workflow fails during setup and returns a non-zero exit code,
  Copilot will proceed using the partially-prepared environment. Fix the
  failing step and re-run the workflow manually.

- If your repo uses private package registries or private dependencies, you
  must provide the appropriate credentials via the `copilot` environment
  secrets so the setup steps can fetch them.

Contact and follow-ups

- I recommend optionally pinning Actions to specific commit SHAs if your
  security policy requires exact-action pins. This repository currently uses
  the stable major tags (for example `actions/setup-python@v4`). If you want
  me to pin SHAs, I can fetch the latest SHAs and update the workflow.
