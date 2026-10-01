"""
Tests for SQLite and PostgreSQL Database Adapters.
"""
import pytest
from app.adapters.sqlite import SQLiteAdapter


def test_sqlite_adapter_connect_introspect(sample_db_path):
    adapter = SQLiteAdapter(
        db_path=sample_db_path,
        database_id="test_db",
        database_name="Test DB",
    )
    adapter.connect()
    assert adapter.ping() is True
    assert adapter.get_dialect() == "sqlite"

    schema = adapter.introspect_schema()
    assert schema.total_tables >= 5
    assert "customers" in schema.get_table_names()
    assert "orders" in schema.get_table_names()
    assert "products" in schema.get_table_names()

    res = adapter.execute_query("SELECT COUNT(*) FROM customers")
    assert res.error is None
    assert res.row_count == 1
    assert res.rows[0][0] > 0

    adapter.disconnect()


def test_sqlite_adapter_read_only_protection(sample_db_path):
    adapter = SQLiteAdapter(
        db_path=sample_db_path,
        database_id="test_db",
        database_name="Test DB",
    )
    adapter.connect()
    res = adapter.execute_query("DELETE FROM customers")
    assert res.error is not None
    assert "readonly" in res.error.lower() or "read-only" in res.error.lower() or "forbidden" in res.error.lower()
    adapter.disconnect()
