"""
Unit tests for the router / query intent classifier.
"""
import pytest
from orchestrator.router import QueryRouter, QueryIntent


class TestQueryRouter:
    def test_sql_keyword_routing(self):
        router = QueryRouter()
        intent = router._keyword_fallback("show me all sales data")
        assert intent == QueryIntent.SQL_QUERY

    def test_chart_keyword_routing(self):
        router = QueryRouter()
        intent = router._keyword_fallback("plot a bar chart of revenue")
        assert intent == QueryIntent.CHART

    def test_insight_keyword_routing(self):
        router = QueryRouter()
        intent = router._keyword_fallback("give me insights about the data")
        assert intent == QueryIntent.INSIGHT

    def test_data_prep_keyword_routing(self):
        router = QueryRouter()
        intent = router._keyword_fallback("clean the data and remove duplicates")
        assert intent == QueryIntent.DATA_PREP

    def test_conversation_fallback(self):
        router = QueryRouter()
        intent = router._keyword_fallback("hello how are you")
        assert intent == QueryIntent.CONVERSATION

    def test_intent_enum_values(self):
        values = {i.value for i in QueryIntent}
        assert "sql_query" in values
        assert "chart" in values
        assert "insight" in values
        assert "data_prep" in values
        assert "conversation" in values
