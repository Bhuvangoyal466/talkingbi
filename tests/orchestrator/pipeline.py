import json
import pandas as pd
import sqlite3
from pathlib import Path
from core.llm_client import llm
from core.logger import logger
from core.config import settings
from core.exceptions import DatabaseConnectionError, FileLoadError
from orchestrator.router import QueryRouter, QueryIntent
from layers.data_access.schema_rep import SchemaRepresentation
from layers.data_access.explorer import DatabaseExplorer
from layers.data_access.knowledge_base import TripletKnowledgeBase
from layers.data_access.dual_agent import DualAgentSQLEngine
from layers.data_prep.tree_reasoner import DeepPrepReasoner
from layers.insight_engine.goal_refiner import GoalRefiner
from layers.insight_engine.question_gen import QuestionGenerator
from layers.insight_engine.insight_discoverer import InsightDiscoverer
from layers.insight_engine.evaluator import InsightEvaluator
from layers.insight_engine.summary_synth import SummarySynthesizer
from layers.visualization.data_extractor import DataExtractor
from layers.visualization.chart_type_selector import ChartTypeSelector
from layers.visualization.chart_generator import ChartGenerator


class TalkingBIPipeline:
    """
    Master pipeline orchestrator that integrates all 4 research layers
    into a unified conversational BI system.
    """

    def __init__(self):
        self.router = QueryRouter()
        self.goal_refiner = GoalRefiner()
        self.question_gen = QuestionGenerator()
        self.insight_disc = InsightDiscoverer()
        self.evaluator = InsightEvaluator()
        self.summary_synth = SummarySynthesizer()
        self.data_extractor = DataExtractor()
        self.chart_selector = ChartTypeSelector()
        self.chart_gen = ChartGenerator()

        # Session state
        self.db_conn = None
        self.db_schema = None
        self.sql_engine = None
        self.current_df: pd.DataFrame = None
        self.session_history: list = []

    # ── DATABASE ──────────────────────────────────────────────────────────────
    def connect_database(self, db_path: str) -> dict:
        """Initialize database connection and exploration."""
        logger.info(f"Connecting to database: {db_path}")
        try:
            schema_rep = SchemaRepresentation(db_path)
            self.db_schema = schema_rep.extract_schema()
            self.db_conn = schema_rep.conn
        except Exception as e:
            raise DatabaseConnectionError(f"Failed to connect: {e}") from e

        kb = TripletKnowledgeBase(self.db_schema.db_name)

        if kb.collection.count() == 0:
            logger.info("Building knowledge base via exploration...")
            explorer = DatabaseExplorer(self.db_schema, self.db_conn, target_triplets=30)
            triplets = explorer.explore()
            kb.add_triplets(triplets)
            logger.info(f"Knowledge base built: {len(triplets)} triplets")
        else:
            logger.info(f"Loaded existing knowledge base: {kb.collection.count()} triplets")

        self.sql_engine = DualAgentSQLEngine(self.db_schema, kb, self.db_conn)

        return {
            "status": "connected",
            "db_name": self.db_schema.db_name,
            "tables": list(self.db_schema.tables.keys()),
            "total_columns": sum(len(t.fields) for t in self.db_schema.tables.values()),
        }

    # ── FILE LOADING ──────────────────────────────────────────────────────────
    def load_file(self, file_path: str) -> dict:
        """Load CSV/Excel/Parquet file as current working DataFrame."""
        path = Path(file_path)
        try:
            if path.suffix.lower() == ".csv":
                self.current_df = pd.read_csv(file_path)
            elif path.suffix.lower() in [".xlsx", ".xls"]:
                self.current_df = pd.read_excel(file_path)
            elif path.suffix.lower() == ".parquet":
                self.current_df = pd.read_parquet(file_path)
            else:
                raise FileLoadError(f"Unsupported file type: {path.suffix}")
        except FileLoadError:
            raise
        except Exception as e:
            raise FileLoadError(str(e)) from e

        # Sanitize dtypes dict and preview for JSON serialization
        import math
        def _safe(v):
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                return None
            try:
                import pandas as _pd
                if isinstance(v, _pd.Timestamp):
                    return str(v)
            except Exception:
                pass
            return v

        raw_preview = self.current_df.head(5).to_dict(orient="records")
        preview = [{k: _safe(val) for k, val in row.items()} for row in raw_preview]

        return {
            "status": "loaded",
            "rows": len(self.current_df),
            "columns": list(self.current_df.columns),
            "dtypes": dict(self.current_df.dtypes.astype(str)),
            "preview": preview,
        }

    # ── MAIN PROCESS ─────────────────────────────────────────────────────────
    def process(self, message: str) -> dict:
        """Main message processing entry point."""
        self.session_history.append({"role": "user", "content": message})

        has_db = self.db_schema is not None
        has_file = self.current_df is not None
        intent = self.router.route(message, has_db, has_file)
        logger.info(f"Routing message → {intent}")

        if intent == QueryIntent.SQL_QUERY:
            result = self._handle_sql(message)
        elif intent == QueryIntent.DATA_PREP:
            result = self._handle_data_prep(message)
        elif intent == QueryIntent.CHART:
            result = self._handle_chart(message)
        elif intent == QueryIntent.INSIGHT:
            result = self._handle_insight(message)
        elif intent == QueryIntent.HYBRID:
            result = self._handle_hybrid(message)
        else:
            result = self._handle_conversation(message)

        self.session_history.append({"role": "assistant", "content": str(result)[:500]})
        return result

    # ── HANDLERS ──────────────────────────────────────────────────────────────
    def _handle_sql(self, message: str) -> dict:
        if not self.sql_engine:
            return {"error": "No database connected. Please connect a database first.", "type": "error"}
        result = self.sql_engine.query(message)
        if result["success"]:
            rows = result["result"]["rows"]
            cols = result["result"]["columns"]
            if rows:
                self.current_df = pd.DataFrame(rows, columns=cols)
            return {
                "type": "sql_result",
                "sql": result["sql"],
                "data": result["result"],
                "rows_returned": len(rows) if rows else 0,
                "iterations": result.get("iterations", 1),
            }
        return {"type": "error", "error": f"SQL generation failed: {result.get('error')}"}

    def _handle_data_prep(self, message: str) -> dict:
        if self.current_df is None:
            return {"type": "error", "error": "No data loaded. Please upload a file first."}

        schema_prompt = f"""Extract target schema requirements from this message.
Message: {message}
Current columns: {list(self.current_df.columns)}
Return JSON: {{"columns": {{"col_name": "description"}}, "goal": "transformation goal"}}"""

        try:
            resp = llm.chat(schema_prompt, json_mode=True)
            target_schema = json.loads(resp)
        except Exception:
            target_schema = {"columns": {}, "goal": message}

        tables = {"main": self.current_df.copy()}
        reasoner = DeepPrepReasoner(tables, target_schema)
        try:
            result = reasoner.run()
        except Exception as e:
            logger.error(f"_handle_data_prep error: {e}", exc_info=True)
            return {"type": "data_prep", "success": False, "error": f"Data preparation error: {e}"}

        if result["success"]:
            result_tables = result["result_tables"]
            main_df = result_tables.get("main", list(result_tables.values())[0])
            self.current_df = main_df
            return {
                "type": "data_prep",
                "success": True,
                "pipeline": result["pipeline"],
                "shape": list(main_df.shape),
                "columns": list(main_df.columns),
                "preview": main_df.head(5).to_dict(orient="records"),
                "turns": result.get("turns", 0),
            }
        return {"type": "data_prep", "success": False, "error": "Data preparation failed"}

    def _handle_chart(self, message: str) -> dict:
        try:
            df = self.current_df
            if df is None and self.sql_engine:
                self._handle_sql(message)
                df = self.current_df

            if df is None:
                return {
                    "type": "error",
                    "error": (
                        "No data loaded. Please upload a CSV/Excel/Parquet file using "
                        "the 📁 Data Sources panel in the sidebar, then ask again."
                    ),
                }

            extracted = self.data_extractor.extract(message, df)

            if not extracted.get("values"):
                return {"type": "error", "error": "Could not extract relevant data for chart."}

            chart_type = self.chart_selector.select(message, extracted)
            chart = self.chart_gen.generate(extracted, chart_type)

            if chart.get("success"):
                return {
                    "type": "chart",
                    "image_base64": chart["image_base64"],
                    "chart_type": chart["chart_type"],
                    "title": extracted.get("title"),
                    "data_points": len(extracted.get("values", [])),
                    "code": chart["code"],
                    "justification": chart_type.get("justification", ""),
                }
            return {"type": "error", "error": f"Chart generation failed: {chart.get('error')}"}
        except Exception as e:
            logger.error(f"_handle_chart error: {e}", exc_info=True)
            return {"type": "error", "error": f"Chart generation error: {e}"}

    def _handle_insight(self, message: str) -> dict:
        if self.current_df is None:
            return {
                "type": "error",
                "error": (
                    "No data loaded. Upload a file via the 📁 sidebar or run a SQL query first."
                ),
            }
        try:
            df = self.current_df
            goal = self.goal_refiner.refine(message, df)
            questions = self.question_gen.generate(goal, df, n_questions=6)

            insights = []
            for q in questions:
                result = self.insight_disc.discover(q, df, goal)
                insights.append(result)

            summary = self.summary_synth.synthesize(insights, goal)

            return {
                "type": "insights",
                "goal": goal.get("refined_goal"),
                "insights": insights,
                "summary": summary,
                "total_insights": len(insights),
            }
        except Exception as e:
            logger.error(f"_handle_insight error: {e}", exc_info=True)
            return {"type": "error", "error": f"Insight generation error: {e}"}

    def _handle_hybrid(self, message: str) -> dict:
        """Handle requests that need both data retrieval and visualization."""
        responses = {"type": "hybrid"}

        if self.sql_engine:
            sql_result = self._handle_sql(message)
            responses["data"] = sql_result

        if self.current_df is not None:
            chart_result = self._handle_chart(message)
            responses["chart"] = chart_result

            goal = self.goal_refiner.refine(message, self.current_df)
            questions = self.question_gen.generate(goal, self.current_df, n_questions=3)
            top_insights = [
                self.insight_disc.discover(q, self.current_df, goal) for q in questions[:3]
            ]
            responses["insights"] = [i["insight"] for i in top_insights]

        return responses

    def _handle_conversation(self, message: str) -> dict:
        """Handle general conversation with context awareness."""
        # Short-circuit: if no data source is loaded and the request implies
        # a data operation, return a clear onboarding message without an LLM call.
        if self.current_df is None and self.db_schema is None:
            data_keywords = [
                "chart", "plot", "graph", "pie", "bar", "line",
                "insight", "analyze", "analysis", "trend", "pattern",
                "query", "sql", "data", "upload", "sales", "revenue",
                "clean", "prepare", "summarize",
            ]
            if any(w in message.lower() for w in data_keywords):
                return {
                    "type": "conversation",
                    "response": (
                        "It looks like you want to analyse some data — great! "
                        "To get started, please:\n\n"
                        "1. **Upload a file** — use the 📁 *Data Sources* panel in the left sidebar "
                        "(CSV, Excel, or Parquet).\n"
                        "2. **Or connect a database** — paste a SQLite/DuckDB path in the 🗄️ *Database* "
                        "section of the sidebar.\n\n"
                        "Once data is loaded I can create charts, run SQL queries, find insights, "
                        "and much more."
                    ),
                }

        db_info = self.db_schema.db_name if self.db_schema else "None"
        data_info = str(self.current_df.shape) if self.current_df is not None else "None"
        context = f"Database: {db_info}, Current data shape: {data_info}"

        history_str = "\n".join(
            f"{m['role'].upper()}: {m['content'][:100]}"
            for m in self.session_history[-6:]
        )

        prompt = f"""You are TalkingBI, a conversational business intelligence assistant.
Context: {context}
Recent conversation:
{history_str}

User: {message}
Provide a helpful, concise response. If you detect they want data analysis,
guide them to upload data or connect a database."""

        try:
            response = llm.chat(prompt, temperature=0.4)
        except Exception as e:
            response = f"I'm here to help with your data analysis. (LLM error: {e})"

        return {"type": "conversation", "response": response}
