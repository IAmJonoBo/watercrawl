import pytest

from firecrawl_demo import external_sources


def test_external_sources_import():
    assert hasattr(external_sources, "ExternalSourceFetcher")
