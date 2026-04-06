"""
State tree for tracking multi-step pipeline execution state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class StateNode:
    """A single node in the execution state tree."""
    node_id: str
    phase: str                        # e.g. "sql", "data_prep", "insight", "chart"
    status: str = "pending"           # pending | running | success | failed
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    children: List["StateNode"] = field(default_factory=list)

    def add_child(self, child: "StateNode"):
        self.children.append(child)

    def flatten(self) -> List["StateNode"]:
        """Return self + all descendants in pre-order."""
        result = [self]
        for c in self.children:
            result.extend(c.flatten())
        return result


class StateTree:
    """
    Tracks the full execution state of a TalkingBI pipeline run.

    Useful for debugging, replaying, and showing progress in the UI.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.root: Optional[StateNode] = None
        self._node_index: Dict[str, StateNode] = {}

    def create_root(self, phase: str, input_data: Dict[str, Any] = None) -> StateNode:
        node = StateNode(node_id="root", phase=phase, input_data=input_data or {})
        self.root = node
        self._node_index["root"] = node
        return node

    def add_node(
        self,
        node_id: str,
        phase: str,
        parent_id: Optional[str] = None,
        input_data: Dict[str, Any] = None,
    ) -> StateNode:
        node = StateNode(node_id=node_id, phase=phase, input_data=input_data or {})
        self._node_index[node_id] = node
        if parent_id and parent_id in self._node_index:
            self._node_index[parent_id].add_child(node)
        return node

    def get_node(self, node_id: str) -> Optional[StateNode]:
        return self._node_index.get(node_id)

    def update_node(
        self,
        node_id: str,
        status: str,
        output_data: Dict[str, Any] = None,
        error: Optional[str] = None,
    ):
        node = self._node_index.get(node_id)
        if node:
            node.status = status
            if output_data:
                node.output_data.update(output_data)
            if error:
                node.error = error

    def summary(self) -> Dict[str, Any]:
        """Return a flat summary suitable for API serialization."""
        if not self.root:
            return {}
        all_nodes = self.root.flatten()
        return {
            "session_id": self.session_id,
            "total_nodes": len(all_nodes),
            "phases": [n.phase for n in all_nodes],
            "statuses": {n.node_id: n.status for n in all_nodes},
        }
