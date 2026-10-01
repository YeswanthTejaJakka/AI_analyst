from abc import ABC, abstractmethod
from typing import Any, Optional
from app.models.schema import DatabaseSchema, QueryResult


class DatabaseAdapter(ABC):
    """Abstract base class for database adapters."""

    @abstractmethod
    def connect(self) -> None:
        """Establish database connection."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close database connection."""
        pass

    @abstractmethod
    def introspect_schema(self) -> DatabaseSchema:
        """Introspect tables, columns, data types, keys, and relationships."""
        pass

    @abstractmethod
    def execute_query(self, sql: str, params: Optional[dict[str, Any]] = None) -> QueryResult:
        """Safely execute a read-only query and return the result."""
        pass

    @abstractmethod
    def get_dialect(self) -> str:
        """Return database dialect name: 'sqlite' or 'postgresql'."""
        pass

    @abstractmethod
    def ping(self) -> bool:
        """Check if database connection is alive."""
        pass
