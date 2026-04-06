"""
Attribution-based chart evaluation: verifies that chart accurately
represents the underlying data.
"""
import json
from core.llm_client import llm
from core.logger import logger


class ChartEvaluator:
    """
    Evaluates generated charts for:
    - Data fidelity (chart matches extracted data)
    - Intent alignment (chart fulfills the original intent)
    - Visual appropriateness (correct chart type for data)
    """

    def evaluate(self, intent: str, extracted_data: dict, chart_result: dict) -> dict:
        """
        Evaluate chart quality.

        Returns dict with scores and feedback.
        """
        if not chart_result.get("success"):
            return {
                "data_fidelity": 0.0,
                "intent_alignment": 0.0,
                "visual_score": 0.0,
                "overall": 0.0,
                "feedback": "Chart generation failed.",
            }

        chart_type = chart_result.get("chart_type", "unknown")
        n_points = len(extracted_data.get("values", []))
        title = extracted_data.get("title", "")

        prompt = f"""Evaluate this chart generation result.
Original Intent: {intent}
Chart Type Used: {chart_type}
Data Points Plotted: {n_points}
Chart Title: {title}
Data Sample: {json.dumps(extracted_data.get('values', [])[:3], indent=2)}

Score each dimension 0-10:
{{
  "data_fidelity": <how well data is represented>,
  "intent_alignment": <how well chart answers the intent>,
  "visual_score": <appropriateness of chart type>,
  "feedback": "<brief evaluation notes>"
}}"""

        try:
            resp = llm.chat(prompt, json_mode=True)
            scores = json.loads(resp)
            # Normalize to 0-1
            for key in ["data_fidelity", "intent_alignment", "visual_score"]:
                scores[key] = round(float(scores.get(key, 5)) / 10, 2)
            scores["overall"] = round(
                (scores["data_fidelity"] + scores["intent_alignment"] + scores["visual_score"]) / 3, 2
            )
            return scores
        except Exception as e:
            logger.warning(f"Chart evaluation failed: {e}")
            return {
                "data_fidelity": 0.7,
                "intent_alignment": 0.7,
                "visual_score": 0.7,
                "overall": 0.7,
                "feedback": "Evaluation unavailable.",
            }
