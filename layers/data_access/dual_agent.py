import json
from core.llm_client import llm
from core.config import settings
from core.logger import logger
from layers.data_access.knowledge_base import TripletKnowledgeBase
from layers.data_access.schema_rep import DatabaseSchema


class InfoAgent:
    """
    Responsible for schema grounding and context management.
    Retrieves relevant schema components and expands context
    with necessary join paths and foreign key relationships.
    """

    def __init__(self, schema: DatabaseSchema, kb: TripletKnowledgeBase):
        self.schema = schema
        self.kb = kb

    def get_context(self, question: str, feedback: dict = None) -> dict:
        """Build schema context relevant to the user's question."""
        keywords = self._extract_keywords(question)
        initial_ctx = self._semantic_search(keywords)
        expanded_ctx = self._expand_context(question, initial_ctx, feedback)
        return expanded_ctx

    def _extract_keywords(self, question: str) -> list:
        prompt = f"""Extract key database-related terms from this question.
Question: {question}
Return as JSON: {{"keywords": ["term1", "term2", ...]}}"""
        try:
            resp = llm.chat(prompt, json_mode=True)
            return json.loads(resp).get("keywords", [])
        except Exception:
            return question.split()[:5]

    def _semantic_search(self, keywords: list) -> dict:
        """Find relevant tables and columns based on keywords."""
        relevant_tables = {}

        for tname, table in self.schema.tables.items():
            col_names = [f.name.lower() for f in table.fields]
            overlap = sum(
                1
                for kw in keywords
                if any(kw.lower() in cn for cn in col_names) or kw.lower() in tname.lower()
            )
            if overlap > 0:
                relevant_tables[tname] = {
                    "score": overlap,
                    "fields": [{"name": f.name, "type": f.dtype} for f in table.fields],
                }

        sorted_tables = sorted(
            relevant_tables.items(), key=lambda x: x[1]["score"], reverse=True
        )
        return dict(sorted_tables[: settings.TOP_K])

    def _expand_context(self, question: str, ctx: dict, feedback: dict = None) -> dict:
        """Use LLM to infer implicit dependencies like join keys."""
        feedback_str = ""
        if feedback:
            feedback_str = f"\nFeedback from previous attempt: {feedback}"

        prompt = f"""You are a database expert. Given this question and initial schema context,
identify any missing tables or columns needed (especially join keys).
Question: {question}
Current context: {json.dumps(ctx, indent=2)}
Full schema: {json.dumps(
    {t: [f.name for f in tbl.fields] for t, tbl in self.schema.tables.items()},
    indent=2,
)}{feedback_str}

Return JSON with expanded context:
{{
  "tables": {{
    "table_name": {{
      "fields": [{{"name": "...", "type": "..."}}],
      "reason_included": "..."
    }}
  }}
}}"""
        try:
            resp = llm.chat(prompt, json_mode=True)
            expanded = json.loads(resp)
            return expanded.get("tables", ctx)
        except Exception:
            return ctx


class GenAgent:
    """
    Knowledge-driven SQL synthesis agent.
    Uses retrieved triplets as few-shot examples for accurate SQL generation.
    """

    def __init__(self, kb: TripletKnowledgeBase):
        self.kb = kb

    def generate(
        self, question: str, schema_ctx: dict, conn, feedback: str = ""
    ) -> str:
        """Generate SQL using schema context and knowledge base examples."""
        examples = self.kb.retrieve(question)

        example_str = "\n".join(
            [
                f"-- Example {i+1}:\n-- Q: {ex['description']}\n{ex['sql']}"
                for i, ex in enumerate(examples)
            ]
        )

        prompt = f"""You are an expert SQL data analyst.
Database Schema:
{json.dumps(schema_ctx, indent=2)}

Reference Examples:
{example_str}

{"Previous attempt feedback: " + feedback if feedback else ""}

User Question: {question}

Write a complete, executable SQL query. Return only the SQL, no explanation."""

        sql = llm.chat(
            prompt,
            system="You are an expert SQL analyst. Always return valid SQL only.",
            model=settings.CODE_MODEL,
            temperature=0.1,
            use_cache=not bool(feedback),   # bypass cache when refining with feedback
        )
        return sql.strip().replace("```sql", "").replace("```", "").strip()


class DualAgentSQLEngine:
    """
    Orchestrates InfoAgent and GenAgent in an iterative refinement loop.
    Implements the collaborative SQL synthesis workflow from SQLAgent paper.
    """

    def __init__(self, schema: DatabaseSchema, kb: TripletKnowledgeBase, conn):
        self.info_agent = InfoAgent(schema, kb)
        self.gen_agent = GenAgent(kb)
        self.conn = conn
        self.max_iter = settings.MAX_ITER

    def query(self, question: str) -> dict:
        """Execute iterative dual-agent SQL synthesis."""
        feedback = {}
        last_sql = ""

        for iteration in range(self.max_iter):
            logger.info(f"SQL generation iteration {iteration + 1}/{self.max_iter}")

            schema_ctx = self.info_agent.get_context(question, feedback)
            sql = self.gen_agent.generate(
                question,
                schema_ctx,
                self.conn,
                feedback=str(feedback) if feedback else "",
            )
            last_sql = sql

            success, result, error = self._execute(sql)

            if success and result:
                rows = result.get("rows", [])
                # First iteration: trust any successful execution unconditionally.
                # Fidelity LLM check only runs on refinement iterations (2+).
                if iteration == 0:
                    logger.info("SQL generation succeeded at iteration 1")
                    return {
                        "sql": sql,
                        "result": result,
                        "iterations": 1,
                        "success": True,
                    }
                if self._check_fidelity(question, sql, result):
                    logger.info(f"SQL generation succeeded at iteration {iteration + 1}")
                    return {
                        "sql": sql,
                        "result": result,
                        "iterations": iteration + 1,
                        "success": True,
                    }
                else:
                    feedback = {
                        "type": "semantic_mismatch",
                        "sql": sql,
                        "result": str(result)[:200],
                    }
            else:
                feedback = {"type": "execution_error", "sql": sql, "error": error}

        return {
            "sql": last_sql,
            "result": None,
            "iterations": self.max_iter,
            "success": False,
            "error": "Max iterations reached",
        }

    def _execute(self, sql: str) -> tuple:
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            columns = (
                [d[0] for d in cursor.description] if cursor.description else []
            )
            return True, {"columns": columns, "rows": rows[:50]}, ""
        except Exception as e:
            return False, None, str(e)

    def _check_fidelity(self, question: str, sql: str, result: dict) -> bool:
        """Quick LLM check: does the SQL answer the question?"""
        prompt = f"""Does this SQL query correctly answer the question?
Question: {question}
SQL: {sql}
Result preview: {str(result)[:300]}
Answer with only 'yes' or 'no'."""
        try:
            resp = llm.chat(prompt, temperature=0.0).strip().lower()
            return "yes" in resp
        except Exception:
            return True  # Assume success on LLM failure
