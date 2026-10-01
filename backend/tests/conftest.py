"""
Pytest fixtures for QueryPilot backend tests.
"""
import os
import sys
import pytest

# Ensure backend/app is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.adapters.sqlite import SQLiteAdapter
from app.models.schema import DatabaseSchema
from app.services.pipeline import QueryPipeline
from app.models.chat import ConversationContext


@pytest.fixture
def sample_db_path():
    """Path to the sample ecommerce.db."""
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(base, "sample_database", "ecommerce.db")
    assert os.path.exists(path), f"Sample database not found at {path}"
    return path


@pytest.fixture
def sample_adapter(sample_db_path):
    """SQLiteAdapter connected to the sample database."""
    adapter = SQLiteAdapter(
        db_path=sample_db_path,
        database_id="test_sample",
        database_name="Test Sample Database",
    )
    adapter.connect()
    yield adapter
    adapter.disconnect()


@pytest.fixture
def sample_schema(sample_adapter):
    """Introspected schema from the sample database."""
    return sample_adapter.introspect_schema()


@pytest.fixture
def pipeline():
    """QueryPipeline instance using heuristic provider."""
    return QueryPipeline()


@pytest.fixture
def conversation():
    """Fresh conversation context."""
    return ConversationContext(
        conversation_id="test_conv_001",
        database_id="test_sample",
    )
