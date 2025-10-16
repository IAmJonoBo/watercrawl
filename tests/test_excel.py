import pytest

from firecrawl_demo import excel


def test_excel_import():
    assert hasattr(excel, "ExcelExporter")
