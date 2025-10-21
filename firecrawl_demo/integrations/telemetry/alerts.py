"""Alert routing helpers for telemetry integrations."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import requests

from firecrawl_demo.integrations.telemetry.drift import DriftReport

logger = logging.getLogger(__name__)


def _format_top_alerts(
    report: DriftReport, limit: int = 5
) -> Sequence[tuple[str, str, float]]:
    alerts = sorted(
        (
            (alert.column, alert.category, alert.difference)
            for alert in report.whylogs_alerts
        ),
        key=lambda item: item[2],
        reverse=True,
    )
    return alerts[:limit]


def _build_slack_payload(
    *,
    report: DriftReport,
    dataset: str,
    run_id: str,
    run_timestamp: str,
    dashboard_url: str | None = None,
) -> dict[str, Any]:
    alert_count = len(report.whylogs_alerts)
    exceeded_text = "Yes" if report.exceeded_threshold else "No"
    header = f"Whylogs drift report for `{dataset}` (run `{run_id}`)"
    summary_lines = [
        f"*Alerts:* {alert_count}",
        f"*Threshold exceeded:* {exceeded_text}",
        f"*Threshold:* {report.threshold}",
        f"*Generated:* {run_timestamp}",
    ]
    if dashboard_url:
        summary_lines.append(f"*Dashboard:* {dashboard_url}")

    top_alerts = _format_top_alerts(report)
    if top_alerts:
        alert_lines = "\n".join(
            f"- {column} `{category}` Δ={difference:.4f}"
            for column, category, difference in top_alerts
        )
    else:
        alert_lines = "- No column/category deviations recorded"

    return {
        "text": header,
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": header}},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n".join(summary_lines)},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Top drift categories:*\n" + alert_lines,
                },
            },
        ],
    }


def send_slack_alert(
    *,
    report: DriftReport,
    webhook_url: str,
    dataset: str,
    run_id: str,
    run_timestamp: str,
    dashboard_url: str | None = None,
    timeout: float = 5.0,
) -> bool:
    """Post the drift report summary to a Slack webhook endpoint."""

    if not webhook_url:
        return False

    payload = _build_slack_payload(
        report=report,
        dataset=dataset,
        run_id=run_id,
        run_timestamp=run_timestamp,
        dashboard_url=dashboard_url,
    )
    try:
        response = requests.post(webhook_url, json=payload, timeout=timeout)
    except requests.RequestException:
        logger.warning("telemetry.slack_post_failed", exc_info=True)
        return False

    if response.status_code >= 400:
        logger.warning(
            "telemetry.slack_post_failed",
            extra={"status_code": response.status_code, "body": response.text},
        )
        return False

    return True


__all__ = ["send_slack_alert"]
