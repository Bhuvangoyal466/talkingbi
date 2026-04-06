import json
import random
from dataclasses import dataclass, field
from typing import Optional
from core.llm_client import llm
from core.logger import logger
from layers.data_access.schema_rep import DatabaseSchema


@dataclass
class Triplet:
    """Core knowledge unit: (Schema fragment, SQL Query, NL Description)"""
    schema_fragment: dict
    sql_query: str
    nl_description: str
    tables_used: list
    success: bool = True


@dataclass
class ExplorationNode:
    node_id: str
    current_query_state: str
    tables_in_scope: list
    actions_taken: list
    triplets: list = field(default_factory=list)
    visit_count: int = 0
    success_count: int = 0

    @property
    def score(self) -> float:
        if self.visit_count == 0:
            return 0.0
        return self.success_count / self.visit_count


ACTIONS = [
    "SELECT_COLUMN",
    "ADD_WHERE_CONSTRAINT",
    "INTRODUCE_JOIN",
    "APPLY_AGGREGATION",
    "ADD_GROUP_BY",
    "ADD_ORDER_BY",
    "ADD_HAVING",
]


class DatabaseExplorer:
    """
    Implements MCTS-inspired autonomous database exploration.
    Generates (Schema, SQL, NL) triplets that form the knowledge base.
    Replaces traditional UCT scalar rewards with LLM semantic evaluation.
    """

    def __init__(self, schema: DatabaseSchema, conn, target_triplets: int = 50):
        self.schema = schema
        self.conn = conn
        self.target = target_triplets
        self.triplets: list = []
        self.nodes: dict = {}

    def explore(self) -> list:
        """Main exploration loop."""
        logger.info(f"Starting DB exploration. Target: {self.target} triplets")
        iterations = 0
        max_iterations = self.target * 5

        while len(self.triplets) < self.target and iterations < max_iterations:
            iterations += 1
            node = self._select_node()
            expanded_node = self._expand(node)
            success, triplet = self._simulate(expanded_node)
            self._backpropagate(expanded_node, success)
            if success and triplet:
                self.triplets.append(triplet)
                logger.info(f"Collected triplet {len(self.triplets)}/{self.target}")

        logger.info(f"Exploration complete. Collected {len(self.triplets)} triplets.")
        return self.triplets

    def _select_node(self) -> ExplorationNode:
        """LLM-guided selection: pick node with best exploration potential."""
        if not self.nodes:
            root = ExplorationNode(
                node_id="root",
                current_query_state="",
                tables_in_scope=list(self.schema.tables.keys())[:3],
                actions_taken=[],
            )
            self.nodes["root"] = root
            return root
        candidates = sorted(
            self.nodes.values(),
            key=lambda n: n.score - (0.1 * n.visit_count),
        )
        return random.choice(candidates[:3]) if len(candidates) >= 3 else candidates[0]

    def _expand(self, node: ExplorationNode) -> ExplorationNode:
        """LLM selects next action to expand node."""
        schema_ctx = {
            t: [f.name for f in self.schema.tables[t].fields]
            for t in node.tables_in_scope
            if t in self.schema.tables
        }
        prompt = f"""You are building a SQL query step by step.
Current query state: {node.current_query_state or 'empty (starting fresh)'}
Available tables and columns: {json.dumps(schema_ctx, indent=2)}
Previous actions: {node.actions_taken}
Available actions: {ACTIONS}

Choose ONE action and provide details as JSON:
{{
  "action": "<ACTION_NAME>",
  "details": "<specific column/table/condition>",
  "new_query_fragment": "<SQL fragment to add>"
}}
Return only valid JSON, no explanation."""

        try:
            response = llm.chat(prompt, json_mode=True)
            decision = json.loads(response)
        except Exception:
            decision = {
                "action": "SELECT_COLUMN",
                "details": "id",
                "new_query_fragment": "SELECT id",
            }

        new_state = node.current_query_state + " " + decision.get("new_query_fragment", "")
        node_id = f"node_{len(self.nodes)}"
        new_node = ExplorationNode(
            node_id=node_id,
            current_query_state=new_state.strip(),
            tables_in_scope=node.tables_in_scope,
            actions_taken=node.actions_taken + [decision.get("action", "")],
        )
        self.nodes[node_id] = new_node
        return new_node

    def _simulate(self, node: ExplorationNode) -> tuple:
        """Generate complete SQL and validate via execution."""
        schema_ctx = {
            t: [f.name for f in self.schema.tables[t].fields]
            for t in node.tables_in_scope
            if t in self.schema.tables
        }
        prompt = f"""Complete this partial SQL query into a full, executable SQL statement.
Partial query: {node.current_query_state}
Available schema: {json.dumps(schema_ctx, indent=2)}

Return only valid JSON:
{{
  "sql": "<complete SQL query>",
  "description": "<natural language description of what this query does>"
}}"""

        try:
            response = llm.chat(prompt, json_mode=True)
            result = json.loads(response)
            sql = result.get("sql", "").strip()
            desc = result.get("description", "")
        except Exception:
            return False, None

        success, data = self._execute_sql(sql)
        if not success or data is None or len(data) == 0:
            return False, None

        triplet = Triplet(
            schema_fragment=schema_ctx,
            sql_query=sql,
            nl_description=desc,
            tables_used=node.tables_in_scope,
        )
        return True, triplet

    def _execute_sql(self, sql: str) -> tuple:
        """Execute SQL and return results or failure."""
        try:
            import sqlite3
            cursor = self.conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchmany(10)
            if not rows:
                return False, None
            return True, rows
        except Exception as e:
            logger.debug(f"SQL execution failed: {e}")
            return False, None

    def _backpropagate(self, node: ExplorationNode, success: bool):
        """Update node statistics for future selection."""
        node.visit_count += 1
        if success:
            node.success_count += 1
