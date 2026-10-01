import os
import sqlite3
import time
from typing import Any, Optional
from app.adapters.base import DatabaseAdapter
from app.core.config import settings
from app.models.schema import (
    ColumnInfo,
    DatabaseSchema,
    ForeignKeyInfo,
    IndexInfo,
    QueryResult,
    RelationshipInfo,
    TableInfo,
)


class SQLiteAdapter(DatabaseAdapter):
    """Adapter for SQLite databases, including sample database and uploaded SQLite files."""

    def __init__(self, db_path: str, database_id: str = "sqlite_db", database_name: str = "SQLite Database"):
        self.db_path = db_path
        self.database_id = database_id
        self.database_name = database_name
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database file not found: {self.db_path}")

        # Connect with read-only URI when possible or enable PRAGMA query_only
        # sqlite3 URI syntax for read-only: file:path?mode=ro
        abs_path = os.path.abspath(self.db_path)
        uri = f"file:{abs_path}?mode=ro"
        try:
            self._conn = sqlite3.connect(uri, uri=True, check_same_thread=False, timeout=settings.QUERY_TIMEOUT_SECONDS)
        except sqlite3.OperationalError:
            # Fallback to standard connect and set pragma
            self._conn = sqlite3.connect(abs_path, check_same_thread=False, timeout=settings.QUERY_TIMEOUT_SECONDS)
            self._conn.execute("PRAGMA query_only = ON;")

    def disconnect(self) -> None:
        if self._conn:
            try:
                self._conn.close()
            finally:
                self._conn = None

    def ping(self) -> bool:
        if not self._conn:
            return False
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT 1;")
            cur.fetchone()
            return True
        except Exception:
            return False

    def get_dialect(self) -> str:
        return "sqlite"

    def introspect_schema(self) -> DatabaseSchema:
        if not self._conn:
            self.connect()

        cursor = self._conn.cursor()
        
        # 1. Fetch tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
        tables_records = cursor.fetchall()
        
        tables: list[TableInfo] = []
        relationships: list[RelationshipInfo] = []

        for (table_name,) in tables_records:
            # Columns
            cursor.execute(f"PRAGMA table_info('{table_name}');")
            # cid, name, type, notnull, dflt_value, pk
            col_rows = cursor.fetchall()
            columns: list[ColumnInfo] = []
            primary_keys: list[str] = []

            for col in col_rows:
                cid, name, col_type, notnull, dflt_val, pk = col
                is_pk = bool(pk)
                if is_pk:
                    primary_keys.append(name)
                columns.append(
                    ColumnInfo(
                        name=name,
                        type=col_type or "TEXT",
                        nullable=not bool(notnull),
                        primary_key=is_pk,
                        default_value=str(dflt_val) if dflt_val is not None else None,
                    )
                )

            # Foreign Keys
            cursor.execute(f"PRAGMA foreign_key_list('{table_name}');")
            # id, seq, table, from, to, on_update, on_delete, match
            fk_rows = cursor.fetchall()
            foreign_keys: list[ForeignKeyInfo] = []

            for fk in fk_rows:
                ref_table = fk[2]
                from_col = fk[3]
                to_col = fk[4]
                if ref_table and from_col and to_col:
                    foreign_keys.append(
                        ForeignKeyInfo(
                            column=from_col,
                            references_table=ref_table,
                            references_column=to_col,
                        )
                    )
                    relationships.append(
                        RelationshipInfo(
                            from_table=table_name,
                            from_column=from_col,
                            to_table=ref_table,
                            to_column=to_col,
                            type="many_to_one",
                        )
                    )

            # Indexes
            cursor.execute(f"PRAGMA index_list('{table_name}');")
            # seq, name, unique, origin, partial
            idx_rows = cursor.fetchall()
            indexes: list[IndexInfo] = []
            for idx in idx_rows:
                idx_name = idx[1]
                is_unique = bool(idx[2])
                cursor.execute(f"PRAGMA index_info('{idx_name}');")
                # seqno, cid, name
                idx_cols = [c[2] for c in cursor.fetchall() if c[2]]
                indexes.append(
                    IndexInfo(
                        name=idx_name,
                        columns=idx_cols,
                        unique=is_unique,
                    )
                )

            # Approximate row count
            row_count = 0
            try:
                cursor.execute(f"SELECT COUNT(*) FROM '{table_name}';")
                row_count = cursor.fetchone()[0]
            except Exception:
                row_count = 0

            tables.append(
                TableInfo(
                    name=table_name,
                    columns=columns,
                    primary_keys=primary_keys,
                    foreign_keys=foreign_keys,
                    indexes=indexes,
                    row_count=row_count,
                )
            )

        return DatabaseSchema(
            database_id=self.database_id,
            database_name=self.database_name,
            dialect="sqlite",
            tables=tables,
            relationships=relationships,
            total_tables=len(tables),
            total_relationships=len(relationships),
        )

    def execute_query(self, sql: str, params: Optional[dict[str, Any]] = None) -> QueryResult:
        if not self._conn:
            self.connect()

        # Enforce read-only constraint at SQLite level
        try:
            self._conn.execute("PRAGMA query_only = ON;")
        except Exception:
            pass

        start_time = time.perf_counter()
        cursor = self._conn.cursor()

        try:
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)

            # Fetch up to MAX_RETURNED_ROWS + 1 to detect truncation
            max_rows = settings.MAX_RETURNED_ROWS
            raw_rows = cursor.fetchmany(max_rows + 1)
            duration_ms = (time.perf_counter() - start_time) * 1000.0

            truncated = False
            if len(raw_rows) > max_rows:
                truncated = True
                raw_rows = raw_rows[:max_rows]

            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            # Convert row tuples to lists with serialized types
            processed_rows: list[list[Any]] = []
            for row in raw_rows:
                row_list = []
                for val in row:
                    if isinstance(val, (bytes, bytearray)):
                        row_list.append("<binary data>")
                    else:
                        row_list.append(val)
                processed_rows.append(row_list)

            return QueryResult(
                columns=columns,
                rows=processed_rows,
                row_count=len(processed_rows),
                execution_time_ms=round(duration_ms, 2),
                truncated=truncated,
                sql=sql,
                error=None,
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return QueryResult(
                columns=[],
                rows=[],
                row_count=0,
                execution_time_ms=round(duration_ms, 2),
                truncated=False,
                sql=sql,
                error=str(e),
            )
