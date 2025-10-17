from firecrawl_demo.core import external_sources


def test_external_sources_import():
    assert hasattr(external_sources, "ExternalSourceFetcher")
