"""Run basic axe-core accessibility checks against the Streamlit analyst UI."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from urllib import error, request

import axe_selenium_python
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

REPO_ROOT = Path(__file__).resolve().parents[3]


def _start_streamlit(port: int) -> tuple[subprocess.Popen[str], str]:
    """Launch the Streamlit UI and return the process handle and served URL."""

    env = dict(os.environ)
    env.setdefault("STREAMLIT_SERVER_PORT", str(port))
    env.setdefault("STREAMLIT_SERVER_HEADLESS", "1")
    env.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "0")
    env.setdefault("STREAMLIT_SERVER_ADDRESS", "127.0.0.1")
    existing_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{REPO_ROOT}:{existing_path}" if existing_path else str(REPO_ROOT)
    )

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "firecrawl_demo/interfaces/analyst_ui.py",
        ],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        text=True,
    )

    url = f"http://127.0.0.1:{port}"
    start = time.time()
    captured_logs: list[str] = []

    while time.time() - start < 60:
        if process.poll() is not None:
            if process.stdout:
                captured_logs.extend(process.stdout.readlines())
            raise RuntimeError(
                "Streamlit process exited early:\n" + "".join(captured_logs)
            )
        try:
            with request.urlopen(url):  # noqa: S310 - internal localhost probe
                return process, url
        except error.URLError:
            time.sleep(1)

    if process.stdout:
        captured_logs.extend(process.stdout.readlines())
    process.terminate()
    process.wait(timeout=10)
    raise RuntimeError(
        "Streamlit server did not respond within 60 seconds.\n" + "".join(captured_logs)
    )


def run_axe_audit(url: str) -> None:
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--no-sandbox")
    with webdriver.Chrome(options=chrome_options) as driver:
        driver.get(url)
        # Allow Streamlit to render the page
        time.sleep(5)
        axe = axe_selenium_python.Axe(driver)
        axe.inject()
        results = axe.run()
        ignored_rules = {
            "page-has-heading-one",  # Streamlit layout does not expose h1 by default
            "button-name",  # Streamlit widget chrome introduces icon-only buttons
            "landmark-one-main",
            "region",
        }
        violations = [
            violation
            for violation in results["violations"]
            if violation.get("id") not in ignored_rules
        ]
        if violations:
            results["violations"] = violations
            axe.write_results(results, "axe-results.json")
            summary = "\n".join(
                f"- {item['id']}: {item['description']}" for item in violations
            )
            raise AssertionError(
                f"axe-core detected {len(violations)} accessibility issues\n{summary}"
            )


def main() -> None:
    port = 8605
    process, url = _start_streamlit(port)
    try:
        run_axe_audit(url)
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


if __name__ == "__main__":
    main()
