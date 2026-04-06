"""
Conversation memory for multi-turn dialogue management.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional


@dataclass
class Turn:
    role: str          # "user" | "assistant"
    content: str
    metadata: Dict = field(default_factory=dict)


class ConversationMemory:
    """
    Sliding-window conversation memory with optional summarization.

    Attributes
    ----------
    max_turns : int
        Maximum number of turns to keep in memory before oldest are dropped.
    """

    def __init__(self, max_turns: int = 20):
        self.max_turns = max_turns
        self._turns: Deque[Turn] = deque(maxlen=max_turns)

    def add(self, role: str, content: str, metadata: Optional[Dict] = None):
        """Add a turn to memory."""
        self._turns.append(Turn(role=role, content=content, metadata=metadata or {}))

    def get_history(self) -> List[Dict]:
        """Return history as a list of {role, content} dicts."""
        return [{"role": t.role, "content": t.content} for t in self._turns]

    def get_context_window(self, n: int = 10) -> List[Dict]:
        """Return the last n turns."""
        turns = list(self._turns)[-n:]
        return [{"role": t.role, "content": t.content} for t in turns]

    def format_as_string(self, n: int = 10) -> str:
        """Format last n turns as a plain-text string for LLM prompts."""
        parts = []
        for t in list(self._turns)[-n:]:
            label = "User" if t.role == "user" else "Assistant"
            parts.append(f"{label}: {t.content}")
        return "\n".join(parts)

    def clear(self):
        """Clear all conversation history."""
        self._turns.clear()

    def __len__(self) -> int:
        return len(self._turns)
