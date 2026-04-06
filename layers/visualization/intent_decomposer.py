import json
from core.llm_client import llm


class IntentDecomposer:
    """
    Decomposes natural language visualization intent into
    structured components: data points, axes, categories, title.
    """

    def decompose(self, intent: str, available_columns: list, column_types: dict = None) -> dict:
        type_info = ""
        if column_types:
            type_info = f"\nColumn types (dtype): {column_types}"
        prompt = f"""Decompose this chart intent into structured components.
Intent: {intent}
Available columns: {available_columns}{type_info}

Return JSON:
{{
  "x_axis": "<column name for x-axis>",
  "y_axis": "<column name or metric for y-axis>",
  "category": "<column for grouping/color, or null>",
  "aggregation": "sum | mean | count | none",
  "filter": "<any filter condition, or null>",
  "title": "<suggested chart title>",
  "time_based": true,
  "part_to_whole": false
}}

IMPORTANT: y_axis MUST be a numeric column (int64/float64 dtype). Date, string, or object columns must go to x_axis or category only.
Only use columns from the available list. Return valid JSON only."""
        try:
            resp = llm.chat(prompt, json_mode=True)
            result = json.loads(resp)
            # Validate columns
            if result.get("x_axis") not in available_columns and available_columns:
                result["x_axis"] = available_columns[0]
            if result.get("y_axis") not in available_columns and len(available_columns) > 1:
                result["y_axis"] = available_columns[1]
            return result
        except Exception:
            return {
                "x_axis": available_columns[0] if available_columns else "x",
                "y_axis": available_columns[1] if len(available_columns) > 1 else "y",
                "title": intent[:60],
                "aggregation": "none",
                "category": None,
                "time_based": False,
                "part_to_whole": False,
            }
