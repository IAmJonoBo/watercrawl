from pathlib import Path

import pytest

pytest.importorskip("yaml")

from watercrawl.core.profiles import load_profile


TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "profiles" / "templates"


def test_profile_templates_directory_exists() -> None:
    assert TEMPLATES_DIR.exists(), "profiles/templates directory is missing"


@pytest.mark.parametrize(
    "template_path",
    sorted(TEMPLATES_DIR.glob("*.y*ml")),
)
def test_profile_templates_are_valid(template_path: Path) -> None:
    profile = load_profile(template_path)
    assert profile.identifier.startswith("template-"), "Template identifiers must be namespaced"
    assert profile.description, "Template profiles should include a description"


def test_templates_cover_multiple_industries() -> None:
    identifiers = {path.stem for path in TEMPLATES_DIR.glob("*.y*ml")}
    assert len(identifiers) >= 2, "Provide at least two profile templates"
