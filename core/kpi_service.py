from __future__ import annotations

import re
from typing import Any, Optional

import pandas as pd


KPI_RULES: list[tuple[str, list[str]]] = [
    ("State", ["state", "province", "region"]),
    ("Revenue", ["revenue", "sales", "turnover", "amount", "top line", "topline"]),
    ("Profit", ["profit", "net profit", "gross profit", "earnings", "income"]),
    ("Margin", ["margin", "gross margin", "operating margin"]),
    ("EBITDA", ["ebitda"]),
    ("Operating Income", ["operating income", "operating profit"]),
    ("CAC", ["cac", "customer acquisition cost"]),
    ("LTV", ["ltv", "lifetime value", "customer lifetime value"]),
    ("Churn Rate", ["churn", "churn rate", "attrition"]),
    ("MRR", ["mrr", "monthly recurring revenue"]),
    ("ARR", ["arr", "annual recurring revenue"]),
    ("DAU", ["dau", "daily active users"]),
    ("MAU", ["mau", "monthly active users"]),
    ("NPS", ["nps", "net promoter score"]),
    ("ROI", ["roi", "return on investment"]),
    ("Conversion Rate", ["conversion rate", "conversion"]),
    ("Retention", ["retention", "retention rate"]),
    ("Growth", ["growth", "growth rate"]),
    ("Forecast", ["forecast", "projection", "predictive"]),
    ("Variance", ["variance", "delta", "difference"]),
    ("Orders", ["orders", "order count", "transactions"]),
    ("Sessions", ["sessions", "visits", "pageviews"]),
]

NON_KPI_TOKENS = {
    "id",
    "uuid",
    "date",
    "time",
    "year",
    "month",
    "day",
    "index",
    "code",
    "rank",
}


def _normalize(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", str(text).lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(normalized)
    return ordered


def _match_kpi_label(text: str) -> Optional[str]:
    normalized = _normalize(text)
    for label, synonyms in KPI_RULES:
        for synonym in synonyms:
            if _normalize(synonym) in normalized:
                return label
    return None


def _pretty_label(name: str) -> str:
    pretty = re.sub(r"[_\-]+", " ", str(name)).strip()
    pretty = re.sub(r"\s+", " ", pretty)
    if not pretty:
        return "KPI"
    return pretty[:1].upper() + pretty[1:]


def infer_kpis_from_message(message: str) -> list[str]:
    if not message:
        return []

    normalized = _normalize(message)
    matches: list[str] = []
    for label, synonyms in KPI_RULES:
        if any(_normalize(synonym) in normalized for synonym in synonyms):
            matches.append(label)
    return _unique(matches)


def infer_kpis_from_dataframe(df: Optional[pd.DataFrame]) -> list[str]:
    if df is None or df.empty:
        return []

    inferred: list[str] = []
    for column in df.columns:
        column_name = str(column)
        normalized = _normalize(column_name)
        if not normalized:
            continue
        if (
            normalized in NON_KPI_TOKENS
            or normalized.endswith(" id")
            or normalized.endswith("_id")
        ):
            continue

        label = _match_kpi_label(column_name)
        if label is None and pd.api.types.is_numeric_dtype(df[column]):
            label = _pretty_label(column_name)
        elif label is None and any(
            token in normalized
            for token in ("rate", "score", "ratio", "share", "margin")
        ):
            label = _pretty_label(column_name)

        if label:
            inferred.append(label)

    return _unique(inferred)


def infer_kpis_from_chart_data(chart_data: Optional[dict[str, Any]]) -> list[str]:
    if not chart_data:
        return []

    labels: list[str] = []
    x_axis = chart_data.get("x_axis_label")
    y_axis = chart_data.get("y_axis_label")
    title = chart_data.get("title")
    if x_axis:
        label = _match_kpi_label(str(x_axis)) or _pretty_label(str(x_axis))
        labels.append(label)
    if y_axis:
        label = _match_kpi_label(str(y_axis)) or _pretty_label(str(y_axis))
        labels.append(label)
    if title:
        title_label = _match_kpi_label(str(title))
        if title_label:
            labels.append(title_label)

    return _unique(labels)


def build_kpi_coverage(
    message: str,
    df: Optional[pd.DataFrame] = None,
    chart_data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    normalized_message = _normalize(message)
    requested = infer_kpis_from_message(message)
    available = infer_kpis_from_dataframe(df)
    chart_kpis = infer_kpis_from_chart_data(chart_data)

    # If the user explicitly references a chart axis term (for example: "by month"),
    # include that axis label in requested KPIs alongside metric terms.
    if requested and chart_kpis:
        axis_requested = [
            kpi
            for kpi in chart_kpis
            if _normalize(kpi) and _normalize(kpi) in normalized_message
        ]
        if axis_requested:
            requested = _unique(requested + axis_requested)

    merged_available = _unique(available + chart_kpis)
    basis = "requested" if requested else "context"

    if not requested:
        if chart_kpis:
            requested = chart_kpis[:]
            basis = "chart"
        else:
            requested = merged_available[:]

    if not merged_available and requested:
        merged_available = requested[:]

    covered = [
        kpi
        for kpi in requested
        if any(
            _normalize(kpi) == _normalize(candidate) for candidate in merged_available
        )
    ]
    if not covered and requested and merged_available:
        for kpi in requested:
            match = _match_kpi_label(kpi)
            if match and any(
                match.lower() == candidate.lower() for candidate in merged_available
            ):
                covered.append(match)

    covered = _unique(covered)
    missing = [
        kpi
        for kpi in requested
        if kpi.lower() not in {item.lower() for item in covered}
    ]
    total = len(requested)
    matched = len(covered)
    percent = round((matched / total) * 100, 1) if total else 0.0
    status = (
        "complete"
        if total and matched == total
        else "partial" if matched else "not_available"
    )

    summary = ""
    if total:
        summary = f"KPI coverage: {matched}/{total} ({percent:.1f}%)."
    elif merged_available:
        summary = f"KPIs in context: {', '.join(merged_available)}."

    return {
        "requested_kpis": requested,
        "available_kpis": merged_available,
        "covered_kpis": covered,
        "missing_kpis": missing,
        "coverage_count": matched,
        "coverage_total": total,
        "coverage_percent": percent,
        "coverage_basis": basis,
        "status": status,
        "summary": summary,
    }
