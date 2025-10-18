from firecrawl_demo.domain import models


def test_models_import():
    assert hasattr(models, "Organisation")


def test_quality_issue_structure():
    issue = models.QualityIssue(
        row_id=3,
        organisation="Example Org",
        code="insufficient_evidence",
        severity="block",
        message="Needs more evidence",
        remediation="Collect additional sources",
    )

    assert issue.as_dict() == {
        "row_id": 3,
        "organisation": "Example Org",
        "code": "insufficient_evidence",
        "severity": "block",
        "message": "Needs more evidence",
        "remediation": "Collect additional sources",
    }


def test_rollback_plan_serialisation():
    action = models.RollbackAction(
        row_id=2,
        organisation="Flight School",
        columns=["Website URL", "Contact Person"],
        previous_values={
            "Website URL": "https://legacy.example/",
            "Contact Person": "Alex Analyst",
        },
        reason="Quality gate rejected enrichment",
    )
    plan = models.RollbackPlan(actions=[action])

    assert plan.as_dict() == {
        "actions": [
            {
                "row_id": 2,
                "organisation": "Flight School",
                "columns": ["Website URL", "Contact Person"],
                "previous_values": {
                    "Website URL": "https://legacy.example/",
                    "Contact Person": "Alex Analyst",
                },
                "reason": "Quality gate rejected enrichment",
            }
        ]
    }


def test_pipeline_report_includes_quality_metadata():
    report = models.PipelineReport(
        refined_dataframe=models.pd.DataFrame(),
        validation_report=models.ValidationReport(issues=[], rows=0),
        evidence_log=[],
        metrics={},
        sanity_findings=[],
        quality_issues=[
            models.QualityIssue(
                row_id=1,
                organisation="Test",
                code="test",
                severity="warn",
                message="Example",
                remediation="",
            )
        ],
        rollback_plan=models.RollbackPlan(actions=[]),
    )

    assert report.quality_issues
    assert report.rollback_plan is not None
