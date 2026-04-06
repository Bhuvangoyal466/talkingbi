import json
import pandas as pd
from core.llm_client import llm


def get_table_schema_desc(df: pd.DataFrame) -> dict:
    """Extract schema statistics for LLM input."""
    schema = {}
    for col in df.columns:
        col_info = {
            "dtype": str(df[col].dtype),
            "missing": int(df[col].isna().sum()),
            "unique": int(df[col].nunique()),
        }
        try:
            if pd.api.types.is_numeric_dtype(df[col]):
                if not df[col].isna().all():
                    col_info["min"] = float(df[col].min())
                    col_info["max"] = float(df[col].max())
                    col_info["mean"] = float(df[col].mean())
                else:
                    col_info["min"] = col_info["max"] = col_info["mean"] = None
            else:
                col_info["top5"] = df[col].dropna().astype(str).value_counts().head(5).index.tolist()
        except Exception:
            col_info["top5"] = []
        schema[col] = col_info
    return schema


class GoalRefiner:
    """
    Refines user-provided analytical goals to be specific,
    measurable, and aligned with available data.
    Implements Step 1 of InsightEval's data curation pipeline.
    """

    def refine(self, goal: str, df: pd.DataFrame, table_desc: str = "") -> dict:
        schema = get_table_schema_desc(df)
        prompt = f"""Analyze this analytical goal against the table schema.
Table Description: {table_desc}
Table Schema: {json.dumps(schema, indent=2)}
Original Goal: {goal}

Refine the goal to be:
1. RELEVANT: Only uses columns that actually exist
2. FEASIBLE: Computationally achievable
3. CLEAR: Specific metrics and dimensions stated

Return JSON:
{{
  "refined_goal": "<refined goal>",
  "relevant_columns": ["col1", "col2"],
  "analysis_type": "trend | comparison | distribution | correlation | anomaly",
  "refinement_reason": "<explanation>"
}}"""
        try:
            resp = llm.chat(prompt, json_mode=True)
            result = json.loads(resp)
            result["original_goal"] = goal
            return result
        except Exception:
            return {
                "refined_goal": goal,
                "relevant_columns": list(df.columns)[:5],
                "original_goal": goal,
                "analysis_type": "descriptive",
            }
