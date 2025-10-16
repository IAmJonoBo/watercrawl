from firecrawl_demo import models


def test_models_import():
    assert hasattr(models, "Organisation")
