"""
Insight summary synthesizer: generates executive summaries
from a list of discovered insights.
"""
from core.llm_client import llm
from core.logger import logger


class SummarySynthesizer:
    """
    Combines multiple insights into a coherent executive summary
    with actionable recommendations.
    """

    def synthesize(self, insights: list, goal: dict) -> str:
        """
        Generate a 3-5 sentence executive summary from insights.

        Args:
            insights: list of insight dicts from InsightDiscoverer
            goal: refined goal dict from GoalRefiner
        """
        insight_texts = [i.get("insight", "") for i in insights if i.get("insight")]
        if not insight_texts:
            return "No insights were discovered for the given goal."

        goal_text = goal.get("refined_goal", goal.get("original_goal", "Analyze data"))

        summary_prompt = f"""Summarize these discovered insights for the following goal.
Goal: {goal_text}

Insights:
{chr(10).join(f"- {i}" for i in insight_texts)}

Write a concise 3-5 sentence executive summary that:
1. Captures the most important findings with specific numbers
2. Identifies clear patterns or trends
3. Ends with 1-2 actionable recommendations

Return only the summary text."""

        try:
            return llm.chat(summary_prompt, temperature=0.2).strip()
        except Exception as e:
            logger.error(f"Summary synthesis failed: {e}")
            return ". ".join(insight_texts[:3])
