import json
from pathlib import Path

import pytest

from watercrawl.core import config as project_config
from watercrawl.core import presets


def _write_preset(monkeypatch, tmp_path: Path, name: str, payload: dict[str, object]):
    preset_dir = tmp_path / "presets"
    preset_dir.mkdir(exist_ok=True)
    path = preset_dir / f"firecrawl_{name}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(project_config, "PROJECT_ROOT", tmp_path)


def test_load_preset_template_reads_json(monkeypatch, tmp_path):
    payload = {"url": "https://example.org", "limit": 10}
    _write_preset(monkeypatch, tmp_path, "map", payload)

    loaded = presets.load_preset_template("map")
    assert loaded == payload


def test_load_preset_template_rejects_unknown_name(monkeypatch, tmp_path):
    _write_preset(monkeypatch, tmp_path, "map", {"url": "https://example.org"})
    with pytest.raises(ValueError):
        presets.load_preset_template("unknown")


def test_payload_helpers_customize_templates(monkeypatch, tmp_path):
    map_payload = {"url": "", "limit": 5}
    scrape_payload = {"url": ""}
    crawl_payload = {"url": "", "includePaths": []}

    for name, payload in {
        "map": map_payload,
        "scrape": scrape_payload,
        "crawl": crawl_payload,
    }.items():
        _write_preset(monkeypatch, tmp_path, name, payload)

    mapped = presets.map_payload("https://example.org", limit=25)
    assert mapped["url"] == "https://example.org"
    assert mapped["limit"] == 25

    scraped = presets.scrape_payload("https://example.org/page")
    assert scraped["url"] == "https://example.org/page"

    crawled = presets.crawl_payload(
        "https://example.org", include_paths=["/about", "/programmes"]
    )
    assert crawled["includePaths"] == ["/about", "/programmes"]


def test_render_curl_command_supports_output_redirection(tmp_path):
    payload_path = tmp_path / "payload.json"
    output_path = tmp_path / "output.json"
    command = presets.render_curl_command(
        "https://api.example.org", payload_path, output_path
    )
    assert "curl" in command
    assert "-X POST" in command
    assert str(payload_path) in command
    assert str(output_path) in command
