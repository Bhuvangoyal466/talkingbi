import json
from core.llm_client import llm

CHART_HEURISTICS = """
Chart Type Selection Heuristics:
- TIME_SERIES: x-axis is date/time, ≥4 points → LINE CHART
- COMPARISON_FEW: 2-5 categories → BAR CHART
- COMPARISON_MANY: 6+ categories → STACKED BAR or HORIZONTAL BAR
- PROPORTIONS: Part-to-whole with ≤6 slices → PIE CHART
- DISTRIBUTION: Single numeric variable → HISTOGRAM
- CORRELATION: Two numeric variables → SCATTER PLOT
- GROUPED: Subcategory comparison → GROUPED BAR CHART
- TREND + FEW POINTS: ≤3 time points → BAR (not line)
Anti-patterns:
- Never use pie with >6 segments
- Never use line for non-sequential data
- Avoid sparse line charts (<3 points)
"""

SUPPORTED_CHARTS = [
    "bar",
    "horizontal_bar",
    "grouped_bar",
    "stacked_bar",
    "line",
    "scatter",
    "pie",
    "histogram",
    "area",
]


class ChartTypeSelector:
    """
    Heuristic-guided chart type recommendation.
    Combines data structure analysis with LLM reasoning.
    """

    def select(self, intent: str, extracted_data: dict) -> dict:
        values = extracted_data.get("values", [])
        n_points = len(values)
        has_category = any("category" in v for v in values)
        categories = list(set(v.get("category", "") for v in values if "category" in v))
        n_categories = len(categories)

        x_vals = [str(v.get("x", "")) for v in values[:5]]
        is_time = any(
            any(c.isdigit() for c in x)
            and any(sep in x for sep in ["-", "/", "Q", "H", "Jan", "Feb", "Mar"])
            for x in x_vals
        )

        prompt = f"""{CHART_HEURISTICS}

Given this data and intent, recommend the best chart type.
Intent: {intent}
Data structure:
  - Number of data points: {n_points}
  - Has category grouping: {has_category}
  - Number of categories: {n_categories}
  - X-axis values (sample): {x_vals}
  - Is time-based: {is_time}
  - X label: {extracted_data.get('x_axis_label')}
  - Y label: {extracted_data.get('y_axis_label')}

Supported types: {SUPPORTED_CHARTS}

Return JSON:
{{
  "recommended_chart_type": "<type from supported list>",
  "justification": "<reason based on heuristics>",
  "confidence_score": 8
}}"""
        try:
            resp = llm.chat(prompt, json_mode=True)
            result = json.loads(resp)
            if result.get("recommended_chart_type") not in SUPPORTED_CHARTS:
                result["recommended_chart_type"] = "bar"
            return result
        except Exception:
            return {
                "recommended_chart_type": "line" if is_time else "bar",
                "justification": "Default selection",
                "confidence_score": 5,
            }
