import pandas as pd

from orchestrator.pipeline import TalkingBIPipeline


def _make_pipeline(monkeypatch):
    monkeypatch.setattr(TalkingBIPipeline, "_try_restore_from_store", lambda self: None)
    return TalkingBIPipeline()


def test_handle_chart_attaches_kpi_coverage(monkeypatch):
    pipeline = _make_pipeline(monkeypatch)
    pipeline.current_df = pd.DataFrame(
        {
            "month": ["Jan", "Feb"],
            "revenue": [100.0, 150.0],
        }
    )

    monkeypatch.setattr(
        pipeline.data_extractor,
        "extract",
        lambda message, df, context="": {
            "values": [{"x": "Jan", "y": 100.0}, {"x": "Feb", "y": 150.0}],
            "x_axis_label": "month",
            "y_axis_label": "revenue",
            "title": "Revenue by Month",
        },
    )
    monkeypatch.setattr(
        pipeline.chart_selector,
        "select",
        lambda message, extracted: {
            "recommended_chart_type": "bar",
            "justification": "test",
        },
    )
    monkeypatch.setattr(
        pipeline.chart_gen,
        "generate",
        lambda extracted, chart_type: {
            "success": True,
            "image_base64": "ZmFrZQ==",
            "code": "# chart",
            "chart_type": chart_type["recommended_chart_type"],
        },
    )

    result = pipeline._handle_chart("show revenue by month")

    assert result["type"] == "chart"
    assert result["kpi_coverage"]["status"] == "complete"
    assert result["kpi_coverage"]["coverage_percent"] == 100.0


def test_handle_conversation_attaches_kpi_coverage(monkeypatch):
    pipeline = _make_pipeline(monkeypatch)
    pipeline.current_df = pd.DataFrame(
        {
            "month": ["Jan", "Feb"],
            "revenue": [100.0, 150.0],
            "profit": [20.0, 30.0],
        }
    )

    monkeypatch.setattr(
        "orchestrator.pipeline.llm.chat",
        lambda *args, **kwargs: "Sure, here is the answer.",
    )

    result = pipeline._handle_conversation("what is my revenue trend")

    assert result["type"] == "conversation"
    assert result["kpi_coverage"]["coverage_count"] >= 1
    assert result["kpi_coverage"]["summary"]
