from firecrawl_demo.core import pipeline


def test_pipeline_import():
    assert hasattr(pipeline, "Pipeline")
