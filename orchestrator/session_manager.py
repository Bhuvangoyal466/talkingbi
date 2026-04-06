"""
Session manager: manages multi-turn conversation state 
and active pipeline instances.
"""
import uuid
from typing import Optional
from orchestrator.pipeline import TalkingBIPipeline
from core.logger import logger


class SessionManager:
    """
    Manages multiple user sessions, each with its own pipeline state.
    Provides session creation, retrieval, and cleanup.
    """

    def __init__(self, max_sessions: int = 50):
        self._sessions: dict = {}
        self.max_sessions = max_sessions

    def create(self) -> str:
        """Create a new session and return its ID."""
        if len(self._sessions) >= self.max_sessions:
            # Evict oldest session
            oldest = next(iter(self._sessions))
            self.delete(oldest)
            logger.warning(f"Session limit reached. Evicted session: {oldest[:8]}")

        session_id = str(uuid.uuid4())
        self._sessions[session_id] = TalkingBIPipeline(session_id=session_id)
        logger.info(f"Created session: {session_id[:8]}")
        return session_id

    def get(self, session_id: str) -> Optional[TalkingBIPipeline]:
        """Retrieve a pipeline by session ID."""
        if session_id not in self._sessions:
            self._sessions[session_id] = TalkingBIPipeline(session_id=session_id)
            logger.info(f"Auto-created session: {session_id[:8]}")
        return self._sessions[session_id]

    def delete(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"Deleted session: {session_id[:8]}")
            return True
        return False

    def list_sessions(self) -> list:
        """List all active session IDs."""
        return list(self._sessions.keys())

    def session_count(self) -> int:
        return len(self._sessions)


# Global session manager instance
session_manager = SessionManager()
