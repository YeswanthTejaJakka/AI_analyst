"""
Tests for QueryPilot REST API endpoints.
Uses TestClient from fastapi.testclient.
"""
import os
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_connect_sample_database():
    response = client.post("/api/database/sample")
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert data["database_type"] == "sample"
    assert data["total_tables"] >= 5
    assert len(data["tables"]) >= 5


def test_upload_database(sample_db_path):
    with open(sample_db_path, "rb") as f:
        response = client.post(
            "/api/database/upload",
            files={"file": ("test_upload.db", f, "application/octet-stream")},
        )
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert data["database_type"] == "sqlite"
    assert data["total_tables"] >= 5


def test_chat_pipeline_end_to_end():
    # 1. Connect sample database
    sample_res = client.post("/api/database/sample")
    session_id = sample_res.json()["session_id"]

    # 2. Ask simple query
    chat_res = client.post(
        "/api/chat",
        json={"database_id": session_id, "query": "How many customers are there?"},
    )
    assert chat_res.status_code == 200
    msg = chat_res.json()["message"]
    assert msg["role"] == "assistant"
    assert msg["sql"] is not None

    # 3. Ask ambiguous query
    ambiguous_res = client.post(
        "/api/chat",
        json={"database_id": session_id, "query": "Who is the best customer?"},
    )
    assert ambiguous_res.status_code == 200
    amb_data = ambiguous_res.json()
    conv_id = amb_data["conversation_id"]
    assert amb_data["has_clarification"] is True

    # 4. Respond to clarification
    clarify_res = client.post(
        f"/api/chat/{conv_id}/clarify",
        json={
            "field_name": "metric",
            "selected_option": "Highest total spending",
        },
    )
    assert clarify_res.status_code == 200
    clf_msg = clarify_res.json()["message"]
    assert clf_msg["role"] == "assistant"
    assert clf_msg["sql"] is not None
