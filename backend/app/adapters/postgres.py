import time
from typing import Any, Optional
import psycopg2
from psycopg2 import sql as pg_sql
from pydantic import BaseModel, Field
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


class PostgresConnectionParams(BaseModel):
    host: str
    port: int = 5432
    database: str
    username: str
    password: str = Field(..., repr=False)  # Never show in logs or repr
    ssl: str = "prefer"  # 'disable', 'allow', 'prefer', 'require'


class PostgresAdapter(DatabaseAdapter):
    """Adapter for Remote PostgreSQL databases."""

    def __init__(self, params: PostgresConnectionParams, database_id: str = "remote_pg"):
        self.params = params
        self.database_id = database_id
        self.database_name = f"PostgreSQL ({params.database})"
        self._conn = None
        self._check_localhost(params.host)

    @staticmethod
    def _check_localhost(host: str) -> None:
        cleaned = host.strip().lower()
        if cleaned in ["localhost", "127.0.0.1", "::1", "0.0.0.0"]:
            raise ValueError(
                "Local databases cannot be accessed directly by the cloud application. "
                "Use the SQLite upload option, connect a publicly reachable PostgreSQL database, "
                "or run QueryPilot locally on your machine."
            )

    def connect(self) -> None:
        try:
            self._conn = psycopg2.connect(
                host=self.params.host,
                port=self.params.port,
                dbname=self.params.database,
                user=self.params.username,
                password=self.params.password,
                sslmode=self.params.ssl if self.params.ssl in ["disable", "allow", "prefer", "require"] else "prefer",
                connect_timeout=settings.QUERY_TIMEOUT_SECONDS,
            )
            # Enforce read-only transaction on this session
            self._conn.set_session(readonly=True, autocommit=True)
            with self._conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = '{settings.QUERY_TIMEOUT_SECONDS * 1000}';")
        except Exception as e:
            # Mask password in error message
            err_msg = str(e)
            if self.params.password:
                err_msg = err_msg.replace(self.params.password, "******")
            raise ConnectionError(f"Failed to connect to PostgreSQL: {err_msg}") from None

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
            with self._conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
                return True
        except Exception:
            return False

    def get_dialect(self) -> str:
        return "postgresql"

    def introspect_schema(self) -> DatabaseSchema:
        if not self._conn:
            self.connect()

        tables: list[TableInfo] = []
        relationships: list[RelationshipInfo] = []

        with self._conn.cursor() as cur:
            # 1. Fetch user tables
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name;
            """)
            table_names = [r[0] for r in cur.fetchall()]

            for t_name in table_names:
                # Columns
                cur.execute("""
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s
                    ORDER BY ordinal_position;
                """, (t_name,))
                col_rows = cur.fetchall()

                # Primary Keys
                cur.execute("""
                    SELECT kcu.column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                      ON tc.constraint_name = kcu.constraint_name
                      AND tc.table_schema = kcu.table_schema
                    WHERE tc.constraint_type = 'PRIMARY KEY'
                      AND tc.table_schema = 'public'
                      AND tc.table_name = %s;
                """, (t_name,))
                pk_cols = [r[0] for r in cur.fetchall()]

                columns: list[ColumnInfo] = []
                for c_name, d_type, is_null, c_def in col_rows:
                    is_pk = c_name in pk_cols
                    columns.append(
                        ColumnInfo(
                            name=c_name,
                            type=d_type,
                            nullable=(is_null == "YES"),
                            primary_key=is_pk,
                            default_value=c_def,
                        )
                    )

                # Foreign Keys
                cur.execute("""
                    SELECT
                        kcu.column_name,
                        ccu.table_name AS foreign_table_name,
                        ccu.column_name AS foreign_column_name
                    FROM information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                      ON tc.constraint_name = kcu.constraint_name
                      AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.constraint_column_usage AS ccu
                      ON ccu.constraint_name = tc.constraint_name
                      AND ccu.table_schema = tc.table_schema
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                      AND tc.table_schema = 'public'
                      AND tc.table_name = %s;
                """, (t_name,))
                fk_rows = cur.fetchall()
                foreign_keys: list[ForeignKeyInfo] = []
                for f_col, ref_t, ref_c in fk_rows:
                    foreign_keys.append(
                        ForeignKeyInfo(
                            column=f_col,
                            references_table=ref_t,
                            references_column=ref_c,
                        )
                    )
                    relationships.append(
                        RelationshipInfo(
                            from_table=t_name,
                            from_column=f_col,
                            to_table=ref_t,
                            to_column=ref_c,
                            type="many_to_one",
                        )
                    )

                # Approximate row count
                row_count = 0
                try:
                    cur.execute("""
                        SELECT n_live_tup
                        FROM pg_stat_user_tables
                        WHERE relname = %s;
                    """, (t_name,))
                    stat_res = cur.fetchone()
                    if stat_res and stat_res[0] is not None:
                        row_count = int(stat_res[0])
                    else:
                        cur.execute(f'SELECT COUNT(*) FROM "{t_name}";')
                        row_count = cur.fetchone()[0]
                except Exception:
                    row_count = 0

                tables.append(
                    TableInfo(
                        name=t_name,
                        columns=columns,
                        primary_keys=pk_cols,
                        foreign_keys=foreign_keys,
                        indexes=[],
                        row_count=row_count,
                    )
                )

        return DatabaseSchema(
            database_id=self.database_id,
            database_name=self.database_name,
            dialect="postgresql",
            tables=tables,
            relationships=relationships,
            total_tables=len(tables),
            total_relationships=len(relationships),
        )

    def execute_query(self, sql: str, params: Optional[dict[str, Any]] = None) -> QueryResult:
        if not self._conn:
            self.connect()

        start_time = time.perf_counter()
        try:
            with self._conn.cursor() as cur:
                if params:
                    cur.execute(sql, params)
                else:
                    cur.execute(sql)

                max_rows = settings.MAX_RETURNED_ROWS
                raw_rows = cur.fetchmany(max_rows + 1)
                duration_ms = (time.perf_counter() - start_time) * 1000.0

                truncated = False
                if len(raw_rows) > max_rows:
                    truncated = True
                    raw_rows = raw_rows[:max_rows]

                columns = [desc[0] for desc in cur.description] if cur.description else []
                processed_rows = [list(row) for row in raw_rows]

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
            err_msg = str(e)
            if self.params.password:
                err_msg = err_msg.replace(self.params.password, "******")
            return QueryResult(
                columns=[],
                rows=[],
                row_count=0,
                execution_time_ms=round(duration_ms, 2),
                truncated=False,
                sql=sql,
                error=err_msg,
            )
