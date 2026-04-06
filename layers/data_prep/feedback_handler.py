"""
Feedback handler for DeepPrep: analyzes failed operator results
and suggests corrective actions to the LLM.
"""
import json
from core.llm_client import llm
from core.logger import logger


class FeedbackHandler:
    """
    Analyzes execution feedback and generates corrective suggestions
    for the LLM planner to use on the next iteration.
    """

    def analyze(self, failed_ops: list, log: list, target_schema: dict) -> dict:
        """
        Analyze failures and produce structured feedback.

        Returns dict with corrective action suggestions.
        """
        if not failed_ops:
            return {"has_issues": False, "suggestions": []}

        log_str = "\n".join(log[-10:])  # Last 10 log entries

        prompt = f"""Analyze these data preparation failures and suggest fixes.
Failed operators: {failed_ops}
Execution log:
{log_str}
Target schema: {json.dumps(target_schema, indent=2)}

For each failed operator, suggest:
1. The likely cause of failure
2. A corrective action or alternative operator

Return JSON:
{{
  "has_issues": true,
  "suggestions": [
    {{
      "failed_op": "OperatorName",
      "cause": "likely cause",
      "fix": "corrective action"
    }}
  ]
}}"""

        try:
            resp = llm.chat(prompt, json_mode=True)
            return json.loads(resp)
        except Exception as e:
            logger.warning(f"Feedback analysis failed: {e}")
            return {
                "has_issues": True,
                "suggestions": [
                    {"failed_op": op, "cause": "unknown", "fix": "try alternative operator"}
                    for op in failed_ops
                ],
            }
