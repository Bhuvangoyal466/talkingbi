import json
import copy
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd
from core.llm_client import llm
from core.config import settings
from core.logger import logger
from layers.data_prep.operators import DataOperators, OperatorResult


@dataclass
class TreeNode:
    node_id: str
    tables: dict
    parent_id: Optional[str]
    operator_applied: str = ""
    execution_feedback: str = ""
    error: str = ""
    is_failure: bool = False
    depth: int = 0

    def table_preview(self) -> dict:
        """Serialize table states for LLM consumption."""
        preview = {}
        for name, df in self.tables.items():
            preview[name] = {
                "columns": list(df.columns),
                "shape": list(df.shape),
                "sample": df.head(3).to_dict(orient="records"),
            }
        return preview


@dataclass
class AgenticReasoningTree:
    root: TreeNode
    nodes: dict = field(default_factory=dict)
    edges: list = field(default_factory=list)

    def add_node(self, node: TreeNode):
        self.nodes[node.node_id] = node
        if node.parent_id:
            self.edges.append((node.parent_id, node.node_id, node.operator_applied))

    def get_path_to_root(self, node_id: str) -> list:
        """Return list of operator names from root to this node."""
        path = []
        current = self.nodes.get(node_id)
        while current and current.parent_id:
            path.append(current.operator_applied)
            current = self.nodes.get(current.parent_id)
        return list(reversed(path))

    def get_leaf_nodes(self) -> list:
        parent_ids = {e[0] for e in self.edges if isinstance(e, tuple)}
        return [
            n
            for nid, n in self.nodes.items()
            if nid not in parent_ids and not n.is_failure
        ]

    def to_summary(self) -> str:
        """Summarize tree state for LLM planning."""
        lines = ["Current Reasoning Tree:"]
        for node_id, node in self.nodes.items():
            status = "FAILED" if node.is_failure else "OK"
            lines.append(
                f"  Node {node_id} [depth={node.depth}, {status}]: "
                f"{node.operator_applied or 'ROOT'} "
                f"| feedback: {node.execution_feedback[:80]}"
            )
        return "\n".join(lines)


class DeepPrepReasoner:
    """
    Implements DeepPrep's tree-based agentic reasoning.
    Uses <plan>, <expand>, <execute>, <answer> action tags.
    """

    SYSTEM = """You are an autonomous data preparation agent.
Your job is to transform source tables into a target table matching a given schema.
You operate by planning transformations, executing them, and revising based on feedback.
Always output valid JSON in your responses."""

    def __init__(self, source_tables: dict, target_schema: dict):
        self.source = source_tables
        self.target_schema = target_schema
        self.max_turns = settings.MAX_ITER * 3
        self.op_map = self._build_op_map()

    def _build_op_map(self) -> dict:
        return {
            "DropNA": DataOperators.DropNA,
            "MissingValueImputation": DataOperators.MissingValueImputation,
            "Deduplicate": DataOperators.Deduplicate,
            "ValueTransform": DataOperators.ValueTransform,
            "CastType": DataOperators.CastType,
            "StandardizeDatetime": DataOperators.StandardizeDatetime,
            "NormalizeMinMax": DataOperators.NormalizeMinMax,
            "ZScoreNormalize": DataOperators.ZScoreNormalize,
            "RenameColumn": DataOperators.RenameColumn,
            "SelectColumn": DataOperators.SelectColumn,
            "AddNewColumn": DataOperators.AddNewColumn,
            "DropColumn": DataOperators.DropColumn,
            "Filter": DataOperators.Filter,
            "Sort": DataOperators.Sort,
            "Head": DataOperators.Head,
            "GroupBy": DataOperators.GroupBy,
            "Join": DataOperators.Join,
            "Union": DataOperators.Union,
            "Pivot": DataOperators.Pivot,
            "Melt": DataOperators.Melt,
            "Explode": DataOperators.Explode,
            "ExtractDatePart": DataOperators.ExtractDatePart,
            "BinColumn": DataOperators.BinColumn,
            "OneHotEncode": DataOperators.OneHotEncode,
            "FillConstant": DataOperators.FillConstant,
            "ExeCode": DataOperators.ExeCode,
        }

    def run(self) -> dict:
        """Main tree-based agentic inference loop."""
        root = TreeNode(
            node_id="n0",
            tables=copy.deepcopy(self.source),
            parent_id=None,
        )
        tree = AgenticReasoningTree(root=root)
        tree.add_node(root)

        for turn in range(self.max_turns):
            logger.info(f"DeepPrep turn {turn + 1}/{self.max_turns}")

            # ── PLAN ──────────────────────────────────────────────────────────
            last_node = list(tree.nodes.values())[-1]
            plan_prompt = f"""
Target Schema: {json.dumps(self.target_schema, indent=2)}
{tree.to_summary()}
Current tables: {json.dumps(
    {{k: {{"columns": list(v.columns), "shape": list(v.shape)}}
      for k, v in last_node.tables.items()}},
    indent=2,
)}

Based on the tree state and execution feedback, provide a plan:
{{
  "action_type": "expand" | "backtrack" | "terminate",
  "target_node_id": "<node to expand from>",
  "reasoning": "<why this plan>",
  "proposed_operators": ["OperatorName1", "OperatorName2"]
}}"""

            try:
                plan_resp = llm.chat(plan_prompt, system=self.SYSTEM, json_mode=True, temperature=0.1)
                plan = json.loads(plan_resp)
            except Exception:
                continue

            if plan.get("action_type") == "terminate":
                leaves = tree.get_leaf_nodes()
                if leaves:
                    best = leaves[-1]
                    return {
                        "success": True,
                        "result_tables": best.tables,
                        "pipeline": tree.get_path_to_root(best.node_id),
                        "turns": turn + 1,
                    }
                break

            parent_id = plan.get("target_node_id", "n0")
            if parent_id not in tree.nodes:
                parent_id = "n0"
            parent_node = tree.nodes[parent_id]

            # ── EXPAND ────────────────────────────────────────────────────────
            expand_prompt = f"""
Implement this plan: {plan.get('reasoning')}
Proposed operators: {plan.get('proposed_operators')}
Current tables: {json.dumps(
    {{k: {{"columns": list(v.columns), "shape": list(v.shape)}}
      for k, v in parent_node.tables.items()}},
    indent=2,
)}
Target schema: {json.dumps(self.target_schema, indent=2)}
Available operators: {list(self.op_map.keys())}

Return a sequence of operator calls as JSON:
{{
  "operators": [
    {{
      "name": "OperatorName",
      "params": {{"param1": "value1"}}
    }}
  ]
}}"""

            try:
                expand_resp = llm.chat(expand_prompt, system=self.SYSTEM, json_mode=True, temperature=0.1)
                expansion = json.loads(expand_resp)
                ops_to_run = expansion.get("operators", [])
            except Exception:
                continue

            # ── EXECUTE ───────────────────────────────────────────────────────
            current_tables = copy.deepcopy(parent_node.tables)
            node_counter = len(tree.nodes)

            for op_spec in ops_to_run:
                op_name = op_spec.get("name")
                op_params = op_spec.get("params", {})

                if op_name not in self.op_map:
                    continue

                op_func = self.op_map[op_name]
                try:
                    result: OperatorResult = op_func(current_tables, **op_params)
                except Exception as exc:
                    result = OperatorResult(current_tables, False, error=str(exc))

                node_id = f"n{node_counter}"
                node_counter += 1

                if result.success:
                    current_tables = result.tables
                    new_node = TreeNode(
                        node_id=node_id,
                        tables=copy.deepcopy(current_tables),
                        parent_id=parent_id,
                        operator_applied=f"{op_name}({op_params})",
                        execution_feedback=result.feedback,
                        depth=parent_node.depth + 1,
                    )
                    tree.add_node(new_node)
                    parent_id = node_id
                    logger.info(f"  ✓ {op_name}: {result.feedback}")
                else:
                    failed_node = TreeNode(
                        node_id=node_id,
                        tables=current_tables,
                        parent_id=parent_id,
                        operator_applied=f"{op_name}({op_params})",
                        execution_feedback=result.feedback,
                        error=result.error,
                        is_failure=True,
                        depth=parent_node.depth + 1,
                    )
                    tree.add_node(failed_node)
                    logger.warning(f"  ✗ {op_name}: {result.error}")
                    break

            if self._check_target(current_tables):
                return {
                    "success": True,
                    "result_tables": current_tables,
                    "pipeline": tree.get_path_to_root(parent_id),
                    "turns": turn + 1,
                }

        return {
            "success": False,
            "result_tables": {},
            "pipeline": [],
            "turns": self.max_turns,
        }

    def _check_target(self, tables: dict) -> bool:
        """Verify if current tables satisfy target schema."""
        required_cols = set(self.target_schema.get("columns", {}).keys())
        if not required_cols:
            return False
        for df in tables.values():
            if required_cols.issubset(set(df.columns)):
                return True
        return False
