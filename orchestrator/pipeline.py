import hashlib
import json
import math
import os
import tempfile
import threading
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import sqlite3

from core.llm_client import llm
from core.logger import logger
from core.config import settings
from core.exceptions import DatabaseConnectionError, FileLoadError
from core.kpi_service import build_kpi_coverage
from core.session_store import SessionStore
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

    Performance improvements applied
    ---------------------------------
    Fix 1 — KB built in a background thread; upload returns immediately.
    Fix 2 — Insight questions answered in parallel (ThreadPoolExecutor).
    Fix 3 — File-hash-keyed ChromaDB collection; repeat uploads are instant.
    Fix 5 — Temp SQLite opened in WAL mode with tuned cache pragmas.
    """

    def __init__(self, session_id: str = None):
        import uuid

        self.session_id = session_id or str(uuid.uuid4())
        self.store = SessionStore(self.session_id)

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

        # Fix 1 — background KB build tracking
        self._kb_ready: bool = False
        self._kb_lock: threading.Lock = threading.Lock()
        self._tmp_db_path: str = None

        # Fix 7 — restore state after server restart
        self._try_restore_from_store()

    # ── SESSION RESTORE ───────────────────────────────────────────────────────

    def _try_restore_from_store(self):
        """
        Fix 7 — Restore session state after a server restart.

        On first access of an existing session (whose SQLite store is on disk
        but whose in-memory pipeline was wiped by a restart), re-read the last
        uploaded file and rebuild the SQL engine in the background so charts,
        insights, and SQL queries keep working without requiring the user to
        re-upload their data.

        Fails silently — if the original file is gone or unreadable, the user
        gets the normal "please upload a file" prompt.
        """
        try:
            uploads = self.store.get_uploads()
            if not uploads:
                return
            last = uploads[0]  # get_uploads() returns most-recent first
            file_path = last.get("db_path")
            if not file_path or not Path(file_path).exists():
                return

            logger.info(
                f"[restore] Restoring session {self.session_id[:8]} "
                f"from stored upload: {file_path}"
            )
            path = Path(file_path)
            if path.suffix.lower() == ".csv":
                df = pd.read_csv(file_path)
            elif path.suffix.lower() in [".xlsx", ".xls"]:
                df = pd.read_excel(file_path)
            elif path.suffix.lower() == ".parquet":
                df = pd.read_parquet(file_path)
            else:
                logger.warning(
                    f"[restore] Unsupported extension {path.suffix} — skipping"
                )
                return

            self.current_df = df

            # Write a fresh temp SQLite so the SQL engine has a DB to connect to
            table_name = path.stem.replace(" ", "_").replace("-", "_")[:60]
            tmp_fd, tmp_path = tempfile.mkstemp(
                suffix=".db", prefix=f"tbi_{table_name}_"
            )
            os.close(tmp_fd)
            tmp_conn = sqlite3.connect(tmp_path)
            tmp_conn.execute("PRAGMA journal_mode=WAL")
            tmp_conn.execute("PRAGMA synchronous=NORMAL")
            tmp_conn.execute("PRAGMA cache_size=10000")
            df.to_sql(
                table_name, tmp_conn, if_exists="replace", index=False, chunksize=5000
            )
            tmp_conn.close()
            self._tmp_db_path = tmp_path

            # Rebuild KB + SQL engine in the background (same path as normal upload)
            t = threading.Thread(
                target=self._build_sql_engine_bg,
                args=(file_path,),
                daemon=True,
            )
            t.start()
            logger.info(
                f"[restore] DataFrame restored ({len(df)} rows), SQL engine rebuilding"
            )
        except Exception as e:
            logger.warning(f"[restore] Could not restore session state: {e}")

    def connect_database(self, db_path: str) -> dict:
        """
        Initialize database connection and exploration.

        Called directly only for explicit DB connect (/data/connect-db).
        For uploaded files this is invoked from _build_sql_engine_bg on a
        background thread — never on the hot path of the upload response.
        """
        logger.info(f"Connecting to database: {db_path}")
        try:
            schema_rep = SchemaRepresentation(db_path)
            self.db_schema = schema_rep.extract_schema()
            self.db_conn = schema_rep.conn
        except Exception as e:
            raise DatabaseConnectionError(f"Failed to connect: {e}") from e

        # Fix 3 — hash-keyed collection; same file content = instant KB load
        file_hash = self._file_hash(db_path)
        kb = TripletKnowledgeBase(f"file_{file_hash}")

        if kb.collection.count() == 0:
            logger.info("Building knowledge base via exploration...")
            explorer = DatabaseExplorer(
                self.db_schema,
                self.db_conn,
                target_triplets=settings.MAX_EXPLORATION_STEPS,  # Fix 6
            )
            triplets = explorer.explore()
            kb.add_triplets(triplets)
            logger.info(f"Knowledge base built: {len(triplets)} triplets")
        else:
            logger.info(
                f"Reusing cached KB for hash {file_hash[:8]} "
                f"({kb.collection.count()} triplets)"
            )

        with self._kb_lock:
            self.sql_engine = DualAgentSQLEngine(self.db_schema, kb, self.db_conn)
            self._kb_ready = True

        return {
            "status": "connected",
            "db_name": self.db_schema.db_name,
            "tables": list(self.db_schema.tables.keys()),
            "total_columns": sum(len(t.fields) for t in self.db_schema.tables.values()),
        }

    # ── FILE LOADING ──────────────────────────────────────────────────────────

    def load_file(self, file_path: str) -> dict:
        """
        Load CSV/Excel/Parquet into the working DataFrame.

        Fast path (runs synchronously, determines upload response time):
          - pandas read
          - Write temp SQLite with WAL mode  (Fix 5)
          - Return preview immediately

        Slow path (Fix 1 — caller triggers on a background thread):
          - SchemaRepresentation.extract_schema()
          - DatabaseExplorer MCTS triplet build  <- biggest bottleneck ~15-40s
          - ChromaDB embed + persist             <- ~3-5s
          - DualAgentSQLEngine construction
        """
        path = Path(file_path)
        try:
            if path.suffix.lower() == ".csv":
                df = pd.read_csv(file_path)
            elif path.suffix.lower() in [".xlsx", ".xls"]:
                df = pd.read_excel(file_path)
            elif path.suffix.lower() == ".parquet":
                df = pd.read_parquet(file_path)
            else:
                raise FileLoadError(f"Unsupported file type: {path.suffix}")
        except FileLoadError:
            raise
        except Exception as e:
            raise FileLoadError(str(e)) from e

        self.current_df = df

        # ── Fast path: write temp SQLite (Fix 5 — WAL + cache pragmas) ──────
        try:
            table_name = path.stem.replace(" ", "_").replace("-", "_")[:60]
            tmp_fd, tmp_path = tempfile.mkstemp(
                suffix=".db", prefix=f"tbi_{table_name}_"
            )
            os.close(tmp_fd)

            tmp_conn = sqlite3.connect(tmp_path)
            tmp_conn.execute(
                "PRAGMA journal_mode=WAL"
            )  # concurrent reads during writes
            tmp_conn.execute("PRAGMA synchronous=NORMAL")  # ~50% fewer fsyncs vs FULL
            tmp_conn.execute("PRAGMA cache_size=10000")  # ~40 MB page cache
            df.to_sql(
                table_name,
                tmp_conn,
                if_exists="replace",
                index=False,
                chunksize=5000,
            )
            tmp_conn.close()

            self._tmp_db_path = tmp_path
            self._kb_ready = False
            logger.info(f"Temp SQLite written (WAL): {tmp_path}")

        except Exception as e:
            logger.warning(f"Could not write temp SQLite: {e}")

        # ── Safe preview serialization ────────────────────────────────────────
        def _safe(v):
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                return None
            if isinstance(v, pd.Timestamp):
                return str(v)
            return v

        raw_preview = df.head(5).to_dict(orient="records")
        preview = [{k: _safe(val) for k, val in row.items()} for row in raw_preview]

        result = {
            "status": "loaded",
            "rows": len(df),
            "columns": list(df.columns),
            "dtypes": dict(df.dtypes.astype(str)),
            "preview": preview,
            "kb_status": "building_in_background",  # Fix 1 — informs the caller
        }

        self.store.add_upload(
            original_name=path.name,
            db_path=file_path,
            rows=len(df),
            columns=list(df.columns),
        )
        return result

    def _build_sql_engine_bg(self, file_path: str) -> None:
        """
        Fix 1 — Background thread target.

        Runs the slow KB-build path without blocking the upload HTTP response.
        Called from api/routes/data.py via run_in_executor.

        Thread-safety notes:
          - self.db_schema, self.db_conn, self.sql_engine, self._kb_ready are
            all written inside self._kb_lock inside connect_database().
          - self.current_df and self.session_history are only written on the
            request thread, so no locking is needed for those.
        """
        if not self._tmp_db_path:
            logger.error("_build_sql_engine_bg: _tmp_db_path not set — skipping")
            return
        try:
            logger.info(
                f"[bg] Starting KB build for session {self.session_id} "
                f"from {self._tmp_db_path}"
            )
            self.connect_database(self._tmp_db_path)
            logger.info(f"[bg] KB ready for session {self.session_id}")
        except Exception as e:
            logger.error(f"[bg] KB build failed for session {self.session_id}: {e}")

    @staticmethod
    def _file_hash(file_path: str) -> str:
        """
        Fix 3 — MD5 of the first 1 MB of a file.

        Keys the ChromaDB collection so identical file content never triggers
        a second MCTS exploration, even across sessions or server restarts.
        Hashing only 1 MB avoids latency on large Parquet files.
        """
        h = hashlib.md5()
        with open(file_path, "rb") as f:
            h.update(f.read(1024 * 1024))
        return h.hexdigest()

    # ── MAIN PROCESS ─────────────────────────────────────────────────────────

    def process(self, message: str) -> dict:
        """Main message processing entry point."""
        self.session_history.append({"role": "user", "content": message})
        self.store.add_message("user", message)

        has_db = self.db_schema is not None
        has_file = self.current_df is not None
        intent = self.router.route(message, has_db, has_file)
        logger.info(f"Routing message -> {intent}")

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

        result = self._attach_kpi_coverage(message, result)

        # ── Persist result to session store ──────────────────────────────────
        rtype = result.get("type", "")
        # Build a human-readable summary instead of dumping the raw dict
        if rtype == "chart":
            _summary = f"Chart generated: {result.get('title') or result.get('chart_type', 'chart')}"
        elif rtype == "insights":
            _summary = (
                result.get("summary")
                or f"Discovered {len(result.get('insights', []))} insights"
            )
        elif rtype in ("sql", "sql_result"):
            _summary = f"Query returned {result.get('rows_returned', 0)} rows"
        elif rtype == "hybrid":
            _summary = "Generated SQL + chart analysis"
        elif rtype == "data_prep":
            _shape = result.get("shape", [0, 0])
            _summary = f"Data prepared: {_shape[0]} rows × {_shape[1]} columns"
        else:
            _summary = (
                result.get("answer")
                or result.get("error")
                or result.get("response")
                or str(result)[:500]
            )
        self.store.add_message(
            "assistant",
            _summary,
            intent=rtype,
            sql=result.get("sql"),
            rows_ret=result.get("rows_returned"),
            kpi_coverage=result.get("kpi_coverage"),
        )
        if rtype == "insights" and result.get("insights"):
            self.store.add_insight_run(
                goal=result.get("goal", ""),
                insights=result["insights"],
                summary=result.get("summary", ""),
            )
        if rtype == "chart" and result.get("chart_data"):
            self.store.add_chart(message, result)

        self.session_history.append({"role": "assistant", "content": str(result)[:500]})
        return result

    def _attach_kpi_coverage(self, message: str, result: dict) -> dict:
        if not isinstance(result, dict) or result.get("type") == "error":
            return result

        chart_data = result.get("chart_data")
        if not chart_data and result.get("type") == "hybrid":
            chart_data = (result.get("chart") or {}).get("chart_data")

        coverage = build_kpi_coverage(message, self.current_df, chart_data)
        if coverage.get("available_kpis") or coverage.get("requested_kpis"):
            result["kpi_coverage"] = coverage
        return result

    # ── LAYER HANDLERS ────────────────────────────────────────────────────────

    def _handle_sql(self, message: str) -> dict:
        # Fix 1 — friendly message while KB is still building in background
        if self.sql_engine is None:
            if not self._kb_ready and self._tmp_db_path:
                return {
                    "type": "error",
                    "error": (
                        "The knowledge base is still being built in the background "
                        "(usually 15-40 s on first upload). Please try again in a moment."
                    ),
                }
            return {
                "type": "error",
                "error": "No database connected. Please upload a file or connect a database first.",
            }

        with self._kb_lock:
            engine = self.sql_engine

        # Fast-path common aggregate prompts to avoid long LLM retry loops
        # under provider rate limits.
        fast_fallback = self._fallback_simple_aggregate_query(
            message,
            reason="pre_llm_fast_path",
        )
        if fast_fallback:
            return fast_fallback

        result = engine.query(message)
        if result.get("success"):
            rows = result["result"].get("rows", [])
            sql_result = {
                "type": "sql_result",
                "sql": result["sql"],
                "answer": result.get("answer", ""),
                "data": result["result"],
                "rows_returned": len(rows) if rows else 0,
                "iterations": result.get("iterations", 1),
            }
            return self._attach_kpi_coverage(message, sql_result)

        fallback = self._fallback_simple_aggregate_query(
            message, reason="post_llm_failure"
        )
        if fallback:
            return fallback

        last_error = result.get("last_error")
        if last_error:
            return {
                "type": "error",
                "error": f"SQL generation failed: {result.get('error')} (last error: {last_error})",
            }

        return {
            "type": "error",
            "error": f"SQL generation failed: {result.get('error')}",
        }

    def _fallback_simple_aggregate_query(
        self,
        message: str,
        reason: str = "post_llm_failure",
    ) -> dict | None:
        """Handle common aggregate intents when LLM SQL generation fails."""
        if self.current_df is None or self.current_df.empty:
            return None

        df = self.current_df
        lower = message.lower()
        columns_lower = {c.lower(): c for c in df.columns}

        dimension_aliases = {
            "state": ["state", "statewise", "state-wise", "region"],
            "country": ["country", "nation"],
            "month": ["month"],
            "year": ["year"],
            "product_category": ["category", "product category", "product_category"],
            "sub_category": ["sub category", "sub_category", "subcategory"],
            "product": ["product", "item", "sku"],
        }
        group_col = None
        for canonical, aliases in dimension_aliases.items():
            if any(alias in lower for alias in aliases):
                candidate = columns_lower.get(canonical)
                if candidate:
                    group_col = candidate
                    break

        metric_specs = [
            (
                ["sales", "revenue"],
                ["revenue", "net_revenue", "sales", "gross_sales", "amount"],
            ),
            (["profit", "margin"], ["profit", "gross_margin", "margin"]),
            (
                ["cost", "expense", "cogs"],
                ["cost", "cogs", "expense", "shipping_cost", "marketing_spend"],
            ),
            (
                ["quantity", "qty", "units", "orders"],
                ["order_quantity", "quantity", "qty"],
            ),
        ]

        metric_cols = []
        for trigger_words, candidates in metric_specs:
            if not any(w in lower for w in trigger_words):
                continue
            for candidate in candidates:
                col = columns_lower.get(candidate)
                if (
                    col
                    and pd.api.types.is_numeric_dtype(df[col])
                    and col not in metric_cols
                ):
                    metric_cols.append(col)
                    break

        if not metric_cols:
            return None

        if re.search(r"\b(avg|average|mean)\b", lower):
            agg_fn = "mean"
            sql_agg = "AVG"
        elif re.search(r"\b(count|how many|number of)\b", lower):
            agg_fn = "count"
            sql_agg = "COUNT"
        else:
            agg_fn = "sum"
            sql_agg = "SUM"

        select_labels = []
        for metric_col in metric_cols:
            prefix = {"sum": "total", "mean": "avg", "count": "count"}.get(
                agg_fn, agg_fn
            )
            select_labels.append((metric_col, f"{prefix}_{metric_col}"))

        if group_col:
            agg_map = {metric: agg_fn for metric, _ in select_labels}
            grouped = df.groupby(group_col, dropna=False).agg(agg_map).reset_index()
            grouped = grouped.rename(
                columns={metric: label for metric, label in select_labels}
            )
            if select_labels:
                grouped = grouped.sort_values(by=select_labels[0][1], ascending=False)
            result_df = grouped
        else:
            values = {}
            for metric, label in select_labels:
                values[label] = getattr(df[metric], agg_fn)()
            result_df = pd.DataFrame([values])

        # Convert NaN/inf to None so JSON serialization is safe.
        safe_rows = []
        for row in result_df.itertuples(index=False):
            serialized = []
            for val in row:
                if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                    serialized.append(None)
                elif pd.isna(val):
                    serialized.append(None)
                else:
                    serialized.append(val)
            safe_rows.append(serialized)

        if reason == "pre_llm_fast_path":
            logger.info(
                "Using deterministic aggregate fast-path for query: {}",
                message,
            )
        else:
            logger.warning(
                "SQL generation failed; using deterministic aggregate fallback for query: {}",
                message,
            )

        if group_col:
            select_sql = ", ".join(
                [
                    f'{sql_agg}("{metric}") AS "{label}"'
                    for metric, label in select_labels
                ]
            )
            synthetic_sql = (
                f'SELECT "{group_col}", {select_sql} FROM uploaded_data '
                f'GROUP BY "{group_col}" ORDER BY "{select_labels[0][1]}" DESC'
            )
            answer = f"Computed {sql_agg.lower()} for {', '.join(metric_cols)} grouped by {group_col}."
            columns = [group_col] + [label for _, label in select_labels]
        else:
            select_sql = ", ".join(
                [
                    f'{sql_agg}("{metric}") AS "{label}"'
                    for metric, label in select_labels
                ]
            )
            synthetic_sql = f"SELECT {select_sql} FROM uploaded_data"
            answer = f"Computed {sql_agg.lower()} for {', '.join(metric_cols)}."
            columns = [label for _, label in select_labels]

        return {
            "type": "sql_result",
            "sql": synthetic_sql,
            "answer": answer,
            "data": {
                "columns": columns,
                "rows": safe_rows[:50],
            },
            "rows_returned": min(len(safe_rows), 50),
            "iterations": settings.MAX_ITER,
            "fallback": "deterministic_aggregate",
            "fallback_reason": reason,
        }

    def _handle_data_prep(self, message: str) -> dict:
        if self.current_df is None:
            return {
                "type": "error",
                "error": "No data loaded. Please upload a file first.",
            }

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
            return {
                "type": "data_prep",
                "success": False,
                "error": f"Data preparation error: {e}",
            }

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
        return {
            "type": "data_prep",
            "success": False,
            "error": "Data preparation failed",
        }

    def _handle_chart(self, message: str, chart_type_override: str = None) -> dict:
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
                        "the Data Sources panel in the sidebar, then ask again."
                    ),
                }

            extracted = self.data_extractor.extract(message, df)

            if not extracted.get("values"):
                return {
                    "type": "error",
                    "error": "Could not extract relevant data for chart.",
                }

            chart_type = self.chart_selector.select(message, extracted)
            # Allow the caller (e.g. the /charts/generate endpoint) to override
            if chart_type_override:
                chart_type = {**chart_type, "chart_type": chart_type_override}
            chart = self.chart_gen.generate(extracted, chart_type)

            if chart.get("success"):
                result = {
                    "type": "chart",
                    "image_base64": chart["image_base64"],
                    "chart_type": chart["chart_type"],
                    "title": extracted.get("title"),
                    "data_points": len(extracted.get("values", [])),
                    "code": chart["code"],
                    "justification": chart_type.get("justification", ""),
                    "chart_data": {
                        "values": extracted.get("values", []),
                        "x_axis_label": extracted.get("x_axis_label", "X"),
                        "y_axis_label": extracted.get("y_axis_label", "Y"),
                        "title": extracted.get("title", ""),
                    },
                }
                return self._attach_kpi_coverage(message, result)
            return {
                "type": "error",
                "error": f"Chart generation failed: {chart.get('error')}",
            }
        except Exception as e:
            logger.error(f"_handle_chart error: {e}", exc_info=True)
            return {"type": "error", "error": f"Chart generation error: {e}"}

    def _handle_insight(self, message: str) -> dict:
        """
        Fix 2 — Insight questions answered in parallel (ThreadPoolExecutor).

        Original code ran N discover() calls sequentially (~6 LLM round-trips
        in series, ~60 s worst case).  With max_workers=4 those round-trips
        now overlap: wall-clock time drops ~60% on a 4-core machine.

        as_completed() is used instead of pool.map() so a single failing
        question does not cancel the others.

        Fix 6 — n_questions pulled from settings.N_INSIGHT_QUESTIONS (default 4).
        """
        if self.current_df is None:
            return {
                "type": "error",
                "error": "No data loaded. Upload a file via the sidebar or run a SQL query first.",
            }
        try:
            df = self.current_df
            goal = self.goal_refiner.refine(message, df)
            questions = self.question_gen.generate(
                goal, df, n_questions=settings.N_INSIGHT_QUESTIONS
            )

            insights = []
            max_workers = min(4, len(questions))
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {
                    pool.submit(self.insight_disc.discover, q, df, goal): q
                    for q in questions
                }
                for future in as_completed(futures):
                    q = futures[future]
                    try:
                        insights.append(future.result())
                    except Exception as exc:
                        logger.warning(f"Insight question failed ({q!r}): {exc}")

            evaluated = self.evaluator.evaluate(insights)
            summary = self.summary_synth.synthesize(evaluated, goal)

            result = {
                "type": "insights",
                "goal": goal.get("refined_goal"),
                "insights": evaluated,
                "summary": summary,
                "total_insights": len(evaluated),
            }
            return self._attach_kpi_coverage(message, result)
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

            # Fix 2 (partial) — parallelise the 3 hybrid insight questions too
            top_insights = []
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = {
                    pool.submit(self.insight_disc.discover, q, self.current_df, goal): q
                    for q in questions[:3]
                }
                for future in as_completed(futures):
                    try:
                        top_insights.append(future.result())
                    except Exception as exc:
                        logger.warning(f"Hybrid insight failed: {exc}")

            responses["insights"] = [i["insight"] for i in top_insights]

        return self._attach_kpi_coverage(message, responses)

    def _handle_conversation(self, message: str) -> dict:
        """Handle general conversation with context awareness."""
        if self.current_df is None and self.db_schema is None:
            data_keywords = [
                "chart",
                "plot",
                "graph",
                "pie",
                "bar",
                "line",
                "insight",
                "analyze",
                "analysis",
                "trend",
                "pattern",
                "query",
                "sql",
                "data",
                "upload",
                "sales",
                "revenue",
                "clean",
                "prepare",
                "summarize",
            ]
            if any(w in message.lower() for w in data_keywords):
                return {
                    "type": "conversation",
                    "response": (
                        "It looks like you want to analyse some data — great! "
                        "To get started, please:\n\n"
                        "1. **Upload a file** — use the Data Sources panel in the left sidebar "
                        "(CSV, Excel, or Parquet).\n"
                        "2. **Or connect a database** — paste a SQLite/DuckDB path in the "
                        "Database section of the sidebar.\n\n"
                        "Once data is loaded I can create charts, run SQL queries, find insights, "
                        "and much more."
                    ),
                }

        db_info = self.db_schema.db_name if self.db_schema else "None"
        data_info = (
            str(self.current_df.shape) if self.current_df is not None else "None"
        )
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

        result = {"type": "conversation", "response": response}
        return self._attach_kpi_coverage(message, result)
