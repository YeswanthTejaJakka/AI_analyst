import re
from typing import Optional
import sqlparse
from sqlparse.sql import Statement
from app.core.config import settings
from app.models.schema import DatabaseSchema


class SQLValidationError(Exception):
    pass


class SQLValidator:
    """Rigorous SQL validation and safety enforcement.

    Only allows read-only SELECT and WITH statements.
    Strictly forbids destructive commands, stacked queries, and non-existent tables.
    """

    FORBIDDEN_KEYWORDS = {
        "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "CREATE",
        "GRANT", "REVOKE", "EXEC", "EXECUTE", "REPLACE", "MERGE", "CALL",
        "ATTACH", "DETACH", "PRAGMA", "VACUUM", "REINDEX", "COPY", "SHUTDOWN",
        "LOAD_EXTENSION", "INTO OUTFILE", "DUMPFILE", "INFORMATION_SCHEMA.PROCESSLIST",
    }

    ALLOWED_ROOT_KEYWORDS = {"SELECT", "WITH", "EXPLAIN"}

    @classmethod
    def validate_sql(cls, sql: str, schema: Optional[DatabaseSchema] = None) -> tuple[bool, Optional[str]]:
        cleaned_sql = sql.strip().rstrip(";")
        if not cleaned_sql:
            return False, "Query cannot be empty."

        # 1. Parse SQL into statements
        parsed_statements = sqlparse.parse(cleaned_sql)
        if not parsed_statements:
            return False, "Unable to parse SQL query."

        # Prevent multi-statement query chaining (e.g. SELECT 1; DROP TABLE customers;)
        if len(parsed_statements) > 1:
            return False, "Multiple SQL statements are not permitted for security reasons."

        stmt: Statement = parsed_statements[0]

        # 2. Check root statement type (must be SELECT, WITH, or EXPLAIN)
        first_token = None
        for token in stmt.tokens:
            if not token.is_whitespace and token.value:
                first_token = token.value.upper()
                break

        if not first_token or first_token not in cls.ALLOWED_ROOT_KEYWORDS:
            return False, f"Forbidden statement type '{first_token}'. Only read-only SELECT queries are allowed."

        # 3. Token-level scan for forbidden keywords
        sql_upper = cleaned_sql.upper()
        for forbidden in cls.FORBIDDEN_KEYWORDS:
            # Word-boundary regex check
            pattern = rf"\b{forbidden}\b"
            if re.search(pattern, sql_upper):
                return False, f"Dangerous or unauthorized keyword '{forbidden}' detected. Only read-only operations are permitted."

        # 4. Schema verification (table existence check)
        if schema and schema.tables:
            known_table_names = {t.name.lower() for t in schema.tables}
            # Extract potential table tokens after FROM and JOIN
            from_join_pattern = re.findall(r"\b(?:FROM|JOIN)\s+([a-zA-Z0-9_\"`]+)", cleaned_sql, re.IGNORECASE)
            for raw_tbl in from_join_pattern:
                cleaned_tbl = raw_tbl.strip('"\'`').lower()
                # Ignore subquery aliases or common keywords
                if cleaned_tbl in ["(", "select", "lateral"]:
                    continue
                if cleaned_tbl not in known_table_names:
                    return False, f"Table '{cleaned_tbl}' does not exist in the active database schema."

        return True, None

    @classmethod
    def enforce_row_limit(cls, sql: str, max_rows: Optional[int] = None) -> str:
        """Injects or adjusts LIMIT to ensure queries cannot exhaust memory."""
        limit_val = max_rows or settings.MAX_RETURNED_ROWS
        cleaned_sql = sql.strip().rstrip(";")

        # Check if LIMIT already exists
        limit_match = re.search(r"\bLIMIT\s+(\d+)\b", cleaned_sql, re.IGNORECASE)
        if limit_match:
            existing_limit = int(limit_match.group(1))
            if existing_limit > limit_val:
                # Cap to max limit
                cleaned_sql = re.sub(
                    r"\bLIMIT\s+\d+\b",
                    f"LIMIT {limit_val}",
                    cleaned_sql,
                    flags=re.IGNORECASE,
                )
        else:
            cleaned_sql = f"{cleaned_sql} LIMIT {limit_val}"

        return cleaned_sql
