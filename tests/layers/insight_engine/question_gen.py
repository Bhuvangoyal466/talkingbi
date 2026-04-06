import json
import pandas as pd
from core.llm_client import llm
from layers.insight_engine.goal_refiner import get_table_schema_desc

INSIGHT_TYPES = [
    "Descriptive",    # What happened?
    "Diagnostic",     # Why did it happen?
    "Predictive",     # What might happen?
    "Prescriptive",   # What should we do?
    "Evaluative",     # How good/reliable is the data?
    "Exploratory",    # What hidden patterns exist?
]


class QuestionGenerator:
    """
    Generates insight questions per dataset across all 6 types.
    Validates questions against actual table schema.
    """

    def generate(self, goal: dict, df: pd.DataFrame, n_questions: int = 10) -> list:
        schema = get_table_schema_desc(df)
        refined_goal = goal.get("refined_goal", goal.get("original_goal", ""))

        prompt = f"""Generate {n_questions} analytical questions for this dataset.
Goal: {refined_goal}
Table Schema: {json.dumps(schema, indent=2)}

Requirements:
- Cover ALL 6 types: {INSIGHT_TYPES}
- At least 1 question per type
- Each question must reference only EXISTING columns
- Questions should be specific, answerable, non-redundant
- Each has exactly ONE '?' at end

Return JSON array:
[
  {{
    "question": "<specific question>",
    "type": "<one of {INSIGHT_TYPES}>",
    "target_columns": ["col1", "col2"],
    "difficulty": "easy|medium|hard"
  }}
]"""
        try:
            resp = llm.chat(prompt, json_mode=True)
            questions = json.loads(resp)
            # Validate columns exist
            valid_q = []
            for q in questions:
                cols = q.get("target_columns", [])
                valid_cols = [c for c in cols if c in df.columns]
                q["target_columns"] = valid_cols
                if valid_cols or not cols:
                    valid_q.append(q)
            return valid_q[:n_questions]
        except Exception:
            return [
                {
                    "question": "What are the key statistics in this dataset?",
                    "type": "Descriptive",
                    "target_columns": list(df.columns)[:3],
                    "difficulty": "easy",
                }
            ]
