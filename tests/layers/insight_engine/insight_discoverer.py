import json
import pandas as pd
import numpy as np
from core.llm_client import llm
from core.config import settings
from core.logger import logger


class InsightDiscoverer:
    """
    3-stage pipeline: Code Generation → Execution → Insight Synthesis.
    Implements Step 3 of InsightEval's data construction pipeline.
    """

    def discover(self, question: dict, df: pd.DataFrame, goal: dict) -> dict:
        q_text = question.get("question", "")
        q_type = question.get("type", "Descriptive")

        # Stage 1: Generate analysis code
        code = self._generate_code(q_text, q_type, df, goal)

        # Stage 2: Execute code safely
        stats = self._execute_code(code, df)

        # Stage 3: Generate insight from stats
        answer = self._generate_answer(q_text, stats, df, goal)
        insight = self._generate_insight(q_text, answer, stats, df, goal, q_type)

        return {
            "question": q_text,
            "type": q_type,
            "code": code,
            "stats": stats,
            "answer": answer,
            "insight": insight,
        }

    def _generate_code(self, question: str, q_type: str, df: pd.DataFrame, goal: dict) -> str:
        prompt = f"""Write Python code to answer this {q_type} question about a DataFrame.
Goal: {goal.get('refined_goal', '')}
Question: {question}
DataFrame columns: {list(df.columns)}
DataFrame dtypes: {dict(df.dtypes.astype(str))}

Instructions:
- Use 'df' as the variable name
- Import pandas as pd, numpy as np (already imported)
- Store results in a dict called 'stats' with keys: 'name', 'description', 'value'
- Keep 'value' concise (max 500 chars if dict/list)
- Code only, no markdown blocks

Example:
stats = {{'name': 'mean_revenue', 'description': 'Average revenue', 'value': float(df['revenue'].mean())}}"""

        code = llm.chat(prompt, model=settings.CODE_MODEL, temperature=0.1)
        code = code.replace("```python", "").replace("```", "").strip()
        return code

    def _execute_code(self, code: str, df: pd.DataFrame) -> dict:
        """Execute generated code in sandboxed namespace."""
        local_ns = {
            "df": df.copy(),
            "pd": pd,
            "np": np,
            "stats": {},
        }
        try:
            exec(code, local_ns)  # noqa: S102
            stats = local_ns.get("stats", {})
            if isinstance(stats.get("value"), (list, dict)):
                val = stats["value"]
                stats["value"] = str(val)[:500]
            return stats
        except Exception as e:
            logger.warning(f"Code execution failed: {e}")
            return {"name": "error", "description": str(e), "value": "N/A"}

    def _generate_answer(
        self, question: str, stats: dict, df: pd.DataFrame, goal: dict
    ) -> str:
        prompt = f"""Answer this question based on the computed statistics.
Question: {question}
Data statistics: {json.dumps(stats, indent=2, default=str)}
Goal: {goal.get('refined_goal', '')}

Provide a single, factual sentence answer including key numbers.
Return only the answer text."""
        try:
            return llm.chat(prompt, temperature=0.1).strip()
        except Exception:
            return str(stats.get("value", "Unable to compute."))

    def _generate_insight(
        self,
        question: str,
        answer: str,
        stats: dict,
        df: pd.DataFrame,
        goal: dict,
        q_type: str,
    ) -> str:
        type_guidance = {
            "Descriptive": "Summarize what the numbers tell us about the current state.",
            "Diagnostic": "Explain root causes or contributing factors.",
            "Predictive": "Project future trends based on observed patterns.",
            "Prescriptive": "Recommend specific, actionable steps.",
            "Evaluative": "Assess data quality, completeness, and reliability.",
            "Exploratory": "Highlight unexpected patterns, clusters, or anomalies.",
        }
        guidance = type_guidance.get(q_type, "Provide a meaningful insight.")

        prompt = f"""Generate a concise, quantitative business insight.
Goal: {goal.get('refined_goal', '')}
Question: {question}
Answer: {answer}
Data stats: {json.dumps(stats, indent=2, default=str)}
Insight type: {q_type} — {guidance}

Rules:
- Include specific numbers/percentages where available
- Be actionable and non-trivial
- Maximum 2 sentences
- Return only the insight text"""
        try:
            return llm.chat(prompt, temperature=0.2).strip()
        except Exception:
            return answer
