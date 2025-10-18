from firecrawl_demo.application import pipeline


def test_pipeline_import():
    assert hasattr(pipeline, "Pipeline")
