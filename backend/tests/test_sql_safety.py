"""
Tests for SQL Validator and Safety Layer.
Ensures destructive SQL operations are rejected, safe SELECT queries pass, and row limits are enforced.
"""
import pytest
from app.services.sql.validator import SQLValidator
from app.models.schema import DatabaseSchema, TableInfo, ColumnInfo


@pytest.fixture
def mock_schema():
    return DatabaseSchema(
        database_id="test_db_id",
        database_name="test_db",
        dialect="sqlite",
        tables=[
            TableInfo(
                name="customers",
                columns=[
                    ColumnInfo(name="id", type="INTEGER", primary_key=True),
                    ColumnInfo(name="name", type="VARCHAR"),
                    ColumnInfo(name="email", type="VARCHAR"),
                ],
                row_count=100,
            ),
            TableInfo(
                name="orders",
                columns=[
                    ColumnInfo(name="id", type="INTEGER", primary_key=True),
                    ColumnInfo(name="customer_id", type="INTEGER"),
                    ColumnInfo(name="total_amount", type="NUMERIC"),
                ],
                row_count=500,
            ),
        ],
    )


def test_valid_select_query(mock_schema):
    sql = "SELECT id, name FROM customers WHERE id = 1;"
    is_valid, error = SQLValidator.validate_sql(sql, mock_schema)
    assert is_valid is True
    assert error is None


def test_reject_delete_statement(mock_schema):
    sql = "DELETE FROM customers;"
    is_valid, error = SQLValidator.validate_sql(sql, mock_schema)
    assert is_valid is False
    assert "DELETE" in error or "Forbidden" in error or "Dangerous" in error


def test_reject_drop_table(mock_schema):
    sql = "DROP TABLE customers;"
    is_valid, error = SQLValidator.validate_sql(sql, mock_schema)
    assert is_valid is False
    assert "Forbidden" in error or "DROP" in error or "Dangerous" in error


def test_reject_update_statement(mock_schema):
    sql = "UPDATE customers SET name = 'Hacked';"
    is_valid, error = SQLValidator.validate_sql(sql, mock_schema)
    assert is_valid is False
    assert "Forbidden" in error or "Dangerous" in error


def test_reject_insert_statement(mock_schema):
    sql = "INSERT INTO customers (id, name) VALUES (999, 'Attacker');"
    is_valid, error = SQLValidator.validate_sql(sql, mock_schema)
    assert is_valid is False
    assert "Forbidden" in error or "Dangerous" in error


def test_reject_nonexistent_table(mock_schema):
    sql = "SELECT * FROM secret_passwords;"
    is_valid, error = SQLValidator.validate_sql(sql, mock_schema)
    assert is_valid is False
    assert "secret_passwords" in error


def test_row_limit_enforcement():
    sql = "SELECT * FROM customers"
    limited_sql = SQLValidator.enforce_row_limit(sql, max_rows=100)
    assert "LIMIT 100" in limited_sql

    existing_limit = "SELECT * FROM customers LIMIT 10"
    limited_sql_2 = SQLValidator.enforce_row_limit(existing_limit, max_rows=100)
    assert "LIMIT 10" in limited_sql_2
