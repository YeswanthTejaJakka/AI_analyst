"""
Session Manager for QueryPilot.
Manages database adapter instances, schema caches, and session lifecycle.
"""
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from app.adapters.base import DatabaseAdapter
from app.adapters.sqlite import SQLiteAdapter
from app.adapters.postgres import PostgresAdapter, PostgresConnectionParams
from app.core.config import settings
from app.models.schema import DatabaseSchema


@dataclass
class DatabaseSession:
    session_id: str
    adapter: DatabaseAdapter
    schema: Optional[DatabaseSchema] = None
    database_type: str = "sqlite"  # "sqlite" | "postgresql" | "sample"
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        return (time.time() - self.last_accessed) > (settings.SESSION_EXPIRE_MINUTES * 60)

    def touch(self) -> None:
        self.last_accessed = time.time()


class SessionManager:
    """Thread-safe manager for database sessions with auto-expiration."""

    def __init__(self):
        self._sessions: dict[str, DatabaseSession] = {}
        self._lock = threading.Lock()

    def create_sample_session(self) -> DatabaseSession:
        """Create a session for the built-in sample e-commerce database."""
        session_id = f"sample_{uuid.uuid4().hex[:8]}"
        adapter = SQLiteAdapter(
            db_path=settings.SAMPLE_DB_PATH,
            database_id=session_id,
            database_name="Sample E-Commerce Database",
        )
        adapter.connect()
        schema = adapter.introspect_schema()

        session = DatabaseSession(
            session_id=session_id,
            adapter=adapter,
            schema=schema,
            database_type="sample",
        )

        with self._lock:
            self._cleanup_expired()
            self._sessions[session_id] = session

        return session

    def create_upload_session(self, file_path: str, original_filename: str = "uploaded.db") -> DatabaseSession:
        """Create a session for a user-uploaded SQLite database."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Uploaded file not found: {file_path}")

        file_size = os.path.getsize(file_path)
        if file_size > settings.MAX_UPLOAD_SIZE_BYTES:
            os.remove(file_path)
            raise ValueError(
                f"File size ({file_size / (1024*1024):.1f} MB) exceeds "
                f"maximum allowed size ({settings.MAX_UPLOAD_SIZE_BYTES / (1024*1024):.0f} MB)."
            )

        session_id = f"upload_{uuid.uuid4().hex[:8]}"
        adapter = SQLiteAdapter(
            db_path=file_path,
            database_id=session_id,
            database_name=f"Uploaded: {original_filename}",
        )
        adapter.connect()
        schema = adapter.introspect_schema()

        session = DatabaseSession(
            session_id=session_id,
            adapter=adapter,
            schema=schema,
            database_type="sqlite",
        )

        with self._lock:
            self._cleanup_expired()
            self._sessions[session_id] = session

        return session

    def create_postgres_session(self, params: PostgresConnectionParams) -> DatabaseSession:
        """Create a session for a remote PostgreSQL database."""
        session_id = f"pg_{uuid.uuid4().hex[:8]}"
        adapter = PostgresAdapter(params=params, database_id=session_id)
        adapter.connect()
        schema = adapter.introspect_schema()

        session = DatabaseSession(
            session_id=session_id,
            adapter=adapter,
            schema=schema,
            database_type="postgresql",
        )

        with self._lock:
            self._cleanup_expired()
            self._sessions[session_id] = session

        return session

    def get_session(self, session_id: str) -> Optional[DatabaseSession]:
        """Retrieve a session by ID, returning None if expired or not found."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if session.is_expired():
                self._remove_session(session_id)
                return None
            session.touch()
            return session

    def delete_session(self, session_id: str) -> bool:
        """Disconnect and remove a session."""
        with self._lock:
            return self._remove_session(session_id)

    def _remove_session(self, session_id: str) -> bool:
        """Internal: remove session and clean up resources."""
        session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        try:
            session.adapter.disconnect()
        except Exception:
            pass
        # Clean up uploaded files
        if session.database_type == "sqlite" and hasattr(session.adapter, 'db_path'):
            db_path = session.adapter.db_path
            if db_path and settings.UPLOAD_DIR in db_path:
                try:
                    os.remove(db_path)
                except Exception:
                    pass
        return True

    def _cleanup_expired(self) -> None:
        """Remove all expired sessions. Must be called under lock."""
        expired = [sid for sid, s in self._sessions.items() if s.is_expired()]
        for sid in expired:
            self._remove_session(sid)

    def list_sessions(self) -> list[dict]:
        """List active sessions (for debugging/admin)."""
        with self._lock:
            self._cleanup_expired()
            return [
                {
                    "session_id": s.session_id,
                    "database_type": s.database_type,
                    "database_name": s.adapter.database_name if hasattr(s.adapter, 'database_name') else "Unknown",
                    "tables": s.schema.total_tables if s.schema else 0,
                    "relationships": s.schema.total_relationships if s.schema else 0,
                }
                for s in self._sessions.values()
            ]


# Global singleton instance
session_manager = SessionManager()
