from __future__ import annotations

from types import SimpleNamespace

import pytest
import requests

from firecrawl_demo.integrations.telemetry.alerts import send_slack_alert
from firecrawl_demo.integrations.telemetry.drift import DriftMetric, DriftReport


def _mock_report(exceeded: bool = True) -> DriftReport:
    metric = DriftMetric(
        baseline_count=10,
        observed_count=5,
        baseline_ratio=0.5,
        observed_ratio=0.2,
        difference=0.3,
    )
    return DriftReport(
        status_drift={"Candidate": metric},
        province_drift={"Gauteng": metric},
        exceeded_threshold=exceeded,
        threshold=0.2,
        whylogs_alerts=[],
    )


def test_send_slack_alert_no_webhook_returns_false(monkeypatch) -> None:
    report = _mock_report()
    called = False

    def fake_post(*args, **kwargs):
        nonlocal called
        called = True
        return SimpleNamespace(status_code=200, text="")

    monkeypatch.setattr("requests.post", fake_post)

    result = send_slack_alert(
        report=report,
        webhook_url="",
        dataset="flight-schools",
        run_id="run-1",
        run_timestamp="2025-10-20T10:00:00+00:00",
    )

    assert result is False
    assert called is False


def test_send_slack_alert_handles_http_errors(monkeypatch) -> None:
    report = _mock_report()

    def fake_post(*args, **kwargs):
        return SimpleNamespace(status_code=500, text="error")

    monkeypatch.setattr("requests.post", fake_post)

    result = send_slack_alert(
        report=report,
        webhook_url="https://hooks.slack.com/services/test",
        dataset="flight-schools",
        run_id="run-1",
        run_timestamp="2025-10-20T10:00:00+00:00",
    )

    assert result is False


def test_send_slack_alert_success(monkeypatch) -> None:
    report = _mock_report()
    payload: dict[str, dict] = {}

    def fake_post(url, *, json, timeout):
        assert url == "https://hooks.slack.com/services/test"
        payload["data"] = json
        return SimpleNamespace(status_code=200, text="")

    monkeypatch.setattr("requests.post", fake_post)

    result = send_slack_alert(
        report=report,
        webhook_url="https://hooks.slack.com/services/test",
        dataset="flight-schools",
        run_id="run-1",
        run_timestamp="2025-10-20T10:00:00+00:00",
        dashboard_url="https://grafana.example/dashboard",
    )

    assert result is True
    assert "data" in payload
    blocks = payload["data"]["blocks"]
    assert blocks[0]["text"]["text"].startswith("Whylogs drift report")


def test_send_slack_alert_handles_request_exception(monkeypatch) -> None:
    report = _mock_report()

    def fake_post(*args, **kwargs):
        raise requests.RequestException("network down")

    monkeypatch.setattr("requests.post", fake_post)

    result = send_slack_alert(
        report=report,
        webhook_url="https://hooks.slack.com/services/test",
        dataset="flight-schools",
        run_id="run-1",
        run_timestamp="2025-10-20T10:00:00+00:00",
    )

    assert result is False
