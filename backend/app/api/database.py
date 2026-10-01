"""
Database API routes for QueryPilot.
Handles database connection modes: sample, upload, and remote PostgreSQL.
"""
import os
import uuid
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.adapters.postgres import PostgresConnectionParams
from app.core.config import settings
from app.services.database.session_manager import session_manager

router = APIRouter(prefix="/api/database", tags=["Database"])


# --- Response Models ---

class SchemaTableSummary(BaseModel):
    name: str
    columns: int
    row_count: int


class DatabaseConnectionResponse(BaseModel):
    session_id: str
    database_name: str
    database_type: str
    total_tables: int
    total_relationships: int
    tables: list[SchemaTableSummary]
    message: str


class SchemaResponse(BaseModel):
    session_id: str
    database_name: str
    dialect: str
    total_tables: int
    total_relationships: int
    schema_data: dict  # Full serialized DatabaseSchema


# --- Request Models ---

class PostgresConnectRequest(BaseModel):
    host: str
    port: int = 5432
    database: str
    username: str
    password: str = Field(..., repr=False)
    ssl: str = "prefer"


# --- Endpoints ---

@router.post("/sample", response_model=DatabaseConnectionResponse)
async def connect_sample_database():
    """Connect to the built-in sample e-commerce database."""
    try:
        session = session_manager.create_sample_session()
        schema = session.schema

        tables_summary = [
            SchemaTableSummary(
                name=t.name,
                columns=len(t.columns),
                row_count=t.row_count,
            )
            for t in schema.tables
        ]

        return DatabaseConnectionResponse(
            session_id=session.session_id,
            database_name=schema.database_name,
            database_type="sample",
            total_tables=schema.total_tables,
            total_relationships=schema.total_relationships,
            tables=tables_summary,
            message=f"Connected to sample e-commerce database. {schema.total_tables} tables discovered with {schema.total_relationships} relationships. Ready to query.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to sample database: {str(e)}")


@router.post("/upload", response_model=DatabaseConnectionResponse)
async def upload_database(file: UploadFile = File(...)):
    """Upload a SQLite .db file for querying."""
    # Validate file extension
    if not file.filename or not file.filename.lower().endswith(".db"):
        raise HTTPException(status_code=400, detail="Only .db (SQLite) files are supported.")

    # Save to temp directory
    upload_id = uuid.uuid4().hex[:12]
    safe_filename = f"{upload_id}_{os.path.basename(file.filename)}"
    file_path = os.path.join(settings.UPLOAD_DIR, safe_filename)

    try:
        content = await file.read()
        if len(content) > settings.MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"File size ({len(content) / (1024*1024):.1f} MB) exceeds maximum allowed size ({settings.MAX_UPLOAD_SIZE_BYTES / (1024*1024):.0f} MB).",
            )

        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(content)

        session = session_manager.create_upload_session(file_path, file.filename)
        schema = session.schema

        tables_summary = [
            SchemaTableSummary(
                name=t.name,
                columns=len(t.columns),
                row_count=t.row_count,
            )
            for t in schema.tables
        ]

        return DatabaseConnectionResponse(
            session_id=session.session_id,
            database_name=schema.database_name,
            database_type="sqlite",
            total_tables=schema.total_tables,
            total_relationships=schema.total_relationships,
            tables=tables_summary,
            message=f"Database uploaded successfully. {schema.total_tables} tables discovered with {schema.total_relationships} relationships. Ready to query.",
        )
    except HTTPException:
        raise
    except Exception as e:
        # Clean up file on failure
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Failed to process uploaded database: {str(e)}")


@router.post("/connect", response_model=DatabaseConnectionResponse)
async def connect_postgres(request: PostgresConnectRequest):
    """Connect to a remote PostgreSQL database."""
    try:
        params = PostgresConnectionParams(
            host=request.host,
            port=request.port,
            database=request.database,
            username=request.username,
            password=request.password,
            ssl=request.ssl,
        )
        session = session_manager.create_postgres_session(params)
        schema = session.schema

        tables_summary = [
            SchemaTableSummary(
                name=t.name,
                columns=len(t.columns),
                row_count=t.row_count,
            )
            for t in schema.tables
        ]

        return DatabaseConnectionResponse(
            session_id=session.session_id,
            database_name=schema.database_name,
            database_type="postgresql",
            total_tables=schema.total_tables,
            total_relationships=schema.total_relationships,
            tables=tables_summary,
            message=f"Connected to PostgreSQL database '{request.database}'. {schema.total_tables} tables discovered with {schema.total_relationships} relationships. Ready to query.",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ConnectionError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect: {str(e)}")


@router.get("/{session_id}/schema", response_model=SchemaResponse)
async def get_schema(session_id: str):
    """Return full schema for a connected database session."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired.")
    if not session.schema:
        raise HTTPException(status_code=500, detail="Schema not available.")

    return SchemaResponse(
        session_id=session.session_id,
        database_name=session.schema.database_name,
        dialect=session.schema.dialect,
        total_tables=session.schema.total_tables,
        total_relationships=session.schema.total_relationships,
        schema_data=session.schema.model_dump(),
    )


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Disconnect and delete a database session."""
    deleted = session_manager.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {"message": "Session deleted successfully.", "session_id": session_id}
