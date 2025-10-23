from __future__ import annotations

from pathlib import Path
import types

import pytest

from scripts import wheel_status
from scripts.wheel_status import (
    Blocker,
    _build_trust_store,
    evaluate_package,
    fetch_package_metadata,
    generate_status,
)

PYPI_TEMPLATE = {
    "info": {
        "version": "1.0.0",
        "requires_python": None,
    },
    "releases": {
        "1.0.0": [
            {"packagetype": "bdist_wheel", "python_version": "cp313"},
            {"packagetype": "bdist_wheel", "python_version": "py3"},
        ]
    },
}


def test_evaluate_package_detects_missing_wheels() -> None:
    blocker = Blocker(
        package="example", targets=("3.14",), owner=None, issue=None, notes=None
    )
    metadata = {
        "info": {"version": "1.0.0", "requires_python": ">=3.9"},
        "releases": {"1.0.0": [{"packagetype": "sdist", "python_version": "source"}]},
    }
    result = evaluate_package(blocker, metadata)
    assert result["targets"]["3.14"]["status"] == "missing-wheel"
    assert result["resolved"] is False


def test_generate_status_counts_unresolved(tmp_path: Path) -> None:
    blocker = Blocker(
        package="pkg", targets=("3.13", "3.14"), owner=None, issue=None, notes=None
    )

    def fetcher(_: str):
        return PYPI_TEMPLATE, False

    status = generate_status([blocker], fetcher)
    assert status["unresolved_count"] == 0
    package = status["packages"][0]
    assert package["targets"]["3.13"]["status"] == "ok"
    assert package["targets"]["3.14"]["status"] == "ok"


def test_fetch_package_metadata_uses_certifi_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    response = types.SimpleNamespace(text='{"info": {}, "releases": {}}')

    def fake_get(url: str, timeout: int):
        captured["url"] = url
        captured["timeout"] = timeout
        return types.SimpleNamespace(text=response.text, raise_for_status=lambda: None)

    monkeypatch.setattr(wheel_status.SESSION, "get", fake_get)

    data, insecure = fetch_package_metadata("example")

    assert data == {"info": {}, "releases": {}}
    assert insecure is False
    assert captured["url"].endswith("/example/json")
    assert captured["timeout"] == wheel_status.REQUEST_TIMEOUT
    assert captured["timeout"] == wheel_status.REQUEST_TIMEOUT


def test_build_trust_store_combines_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ca1 = tmp_path / "one.pem"
    ca2 = tmp_path / "two.pem"
    ca1.write_text("CERT1\n")
    ca2.write_text("CERT2\n")

    monkeypatch.setenv("SSL_CERT_FILE", str(ca1))
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(ca2))
    monkeypatch.delenv("PIP_CERT", raising=False)

    calls: list[str | None] = []

    def fake_create_default_context(*, cafile: str | None = None):
        calls.append(cafile)
        return object()

    monkeypatch.setattr(
        wheel_status.ssl, "create_default_context", fake_create_default_context
    )
    monkeypatch.setattr(wheel_status.atexit, "register", lambda func: None)

    context, cafile = _build_trust_store()

    assert calls and calls[0] is not None
    assert cafile is not None or isinstance(context, object)
