import json
from enum import Enum
from core.llm_client import llm
from core.logger import logger


class QueryIntent(str, Enum):
    SQL_QUERY = "sql_query"        # "Show me sales for Q3"
    DATA_PREP = "data_prep"        # "Clean this dataset"
    CHART = "chart"                # "Plot revenue by region"
    INSIGHT = "insight"            # "Find insights in this data"
    HYBRID = "hybrid"              # Combination of above
    CONVERSATION = "conversation"  # General chat


class QueryRouter:
    """Routes user messages to appropriate pipeline layer."""

    def route(
        self, message: str, has_db: bool = False, has_file: bool = False
    ) -> QueryIntent:
        prompt = f"""Classify this user message intent.
Message: "{message}"
Has database connection: {has_db}
Has uploaded file: {has_file}

Return JSON:
{{
  "intent": "sql_query | data_prep | chart | insight | hybrid | conversation",
  "confidence": 0.9,
  "reasoning": "<brief reason>"
}}

Rules:
- sql_query: asking for data retrieval, "show me", "find", "how many", "what is", "list", "count"
- data_prep: wants data cleaned/transformed, "prepare", "clean", "fix", "transform", "remove duplicates"
- chart: wants visualization, "plot", "chart", "graph", "visualize", "show graph", "draw"
- insight: wants analysis, "analyze", "insights", "patterns", "what does this tell", "summarize"
- hybrid: wants multiple of the above (e.g. "plot sales trends and explain patterns")
- conversation: general question, greeting, clarification, help"""

        try:
            for attempt in range(2):
                resp = llm.chat(prompt, json_mode=True, temperature=0.0, use_cache=False)
                # Strip markdown code fences that some providers wrap around JSON
                cleaned = resp.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[-1]
                    cleaned = cleaned.rsplit("```", 1)[0].strip()
                try:
                    result = json.loads(cleaned)
                    intent_str = result.get("intent", "conversation").strip()
                    logger.debug(f"Router: '{message[:40]}' → {intent_str} (conf={result.get('confidence')})")
                    return QueryIntent(intent_str)
                except (json.JSONDecodeError, ValueError):
                    if attempt == 0:
                        logger.debug("QueryRouter: unparseable LLM response, retrying...")
                        continue
                    raise
        except Exception as e:
            logger.warning(f"QueryRouter fallback: {e}")
            return self._keyword_fallback(message, has_db=has_db, has_file=has_file)

    def _keyword_fallback(
        self, message: str, has_db: bool = False, has_file: bool = False
    ) -> QueryIntent:
        """Keyword-based intent classification used when LLM is unavailable."""
        msg_lower = message.lower()
        # Without a data source the only sensible intent is conversation.
        # Routing to CHART/INSIGHT/DATA_PREP with no data always errors.
        if not has_db and not has_file:
            return QueryIntent.CONVERSATION
        if any(w in msg_lower for w in ["plot", "chart", "graph", "visualize", "draw", "pie"]):
            return QueryIntent.CHART
        if any(w in msg_lower for w in ["insight", "analyze", "pattern", "summarize", "trend"]):
            return QueryIntent.INSIGHT
        if any(w in msg_lower for w in ["clean", "prepare", "transform", "fix", "duplicate"]):
            return QueryIntent.DATA_PREP
        if any(w in msg_lower for w in ["show", "find", "query", "select", "count", "how many", "data"]):
            return QueryIntent.SQL_QUERY
        return QueryIntent.CONVERSATION
