"""
Collect all linter/type errors and aggregate them into problems_report.json for ephemeral runners/Codex.
"""

import json
import subprocess
from pathlib import Path

REPORT_PATH = Path("problems_report.json")

TOOLS = [
    ("ruff", ["ruff", "check", ".", "--output-format", "json"]),
    ("mypy", ["mypy", ".", "--show-error-codes", "--pretty"]),
    ("pylint", ["pylint", ".", "--output-format=json"]),
    ("bandit", ["bandit", "-r", ".", "-f", "json"]),
    ("yamllint", ["yamllint", ".", "-f", "json"]),
    ("sqlfluff", ["sqlfluff", "lint", ".", "--format", "json"]),
]


def run_tool(name, cmd):
    """
    Runs a linter or analysis tool and returns its output or error.

    Args:
        name (str): The name of the tool.
        cmd (list): The command to execute as a list of arguments.

    Returns:
        dict or None: Dictionary with tool output or error, or None if no output.
    """
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        output = result.stdout.strip()
        if output:
            return {"tool": name, "output": output}
    except (subprocess.CalledProcessError, OSError) as exc:
        return {"tool": name, "error": str(exc)}
    return None


def main():
    """
    Runs all configured linting and analysis tools, aggregates their outputs,
    and writes the results to problems_report.json.
    """
    problems = []
    for name, cmd in TOOLS:
        res = run_tool(name, cmd)
        if res:
            problems.append(res)
    with REPORT_PATH.open("w", encoding="utf-8") as f:
        json.dump(problems, f, indent=2)
    print(f"Problems report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
