import pandas as pd

from core.kpi_service import build_kpi_coverage


def test_build_kpi_coverage_detects_requested_and_available_kpis():
    df = pd.DataFrame(
        {
            "month": ["Jan", "Feb"],
            "revenue": [100.0, 140.0],
            "profit": [20.0, 35.0],
            "region": ["North", "South"],
        }
    )

    coverage = build_kpi_coverage(
        "show revenue and profit by month", df, {"y_axis_label": "Revenue"}
    )

    assert coverage["requested_kpis"] == ["Revenue", "Profit"]
    assert "Revenue" in coverage["available_kpis"]
    assert "Profit" in coverage["available_kpis"]
    assert coverage["coverage_count"] == 2
    assert coverage["coverage_total"] == 2
    assert coverage["coverage_percent"] == 100.0
    assert coverage["status"] == "complete"


def test_build_kpi_coverage_detects_state_with_revenue_request():
    df = pd.DataFrame(
        {
            "state": ["CA", "TX"],
            "revenue": [125.0, 210.0],
        }
    )

    coverage = build_kpi_coverage("show revenue by state", df)

    assert coverage["requested_kpis"] == ["State", "Revenue"]
    assert "State" in coverage["available_kpis"]
    assert "Revenue" in coverage["available_kpis"]
    assert coverage["coverage_count"] == 2
    assert coverage["coverage_total"] == 2
    assert coverage["status"] == "complete"


def test_build_kpi_coverage_uses_chart_axes_when_message_has_no_kpis():
    df = pd.DataFrame(
        {
            "customer_age": [23, 41, 35],
            "state": ["CA", "TX", "WA"],
            "revenue": [100.0, 140.0, 220.0],
            "profit": [20.0, 30.0, 60.0],
        }
    )

    coverage = build_kpi_coverage(
        "show distribution",
        df,
        {
            "x_axis_label": "customer_age",
            "y_axis_label": "customer_age",
            "title": "Distribution of Customer Age",
        },
    )

    assert coverage["coverage_basis"] == "chart"
    assert coverage["requested_kpis"] == ["Customer age"]
    assert coverage["covered_kpis"] == ["Customer age"]
    assert coverage["coverage_count"] == 1
    assert coverage["coverage_total"] == 1
    assert coverage["status"] == "complete"


def test_build_kpi_coverage_includes_month_axis_when_mentioned_in_message():
    df = pd.DataFrame(
        {
            "month": ["Jan", "Feb", "Mar"],
            "revenue": [100.0, 140.0, 120.0],
            "profit": [20.0, 30.0, 25.0],
        }
    )

    coverage = build_kpi_coverage(
        "show revenue by month",
        df,
        {
            "x_axis_label": "month",
            "y_axis_label": "revenue",
            "title": "Revenue by Month",
        },
    )

    assert coverage["coverage_basis"] == "requested"
    assert coverage["requested_kpis"] == ["Revenue", "Month"]
    assert coverage["covered_kpis"] == ["Revenue", "Month"]
    assert coverage["coverage_count"] == 2
    assert coverage["coverage_total"] == 2
    assert coverage["status"] == "complete"
