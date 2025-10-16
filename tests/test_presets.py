import pytest

from firecrawl_demo import presets


def test_presets_import():
    assert hasattr(presets, "PRESET_MAP")
