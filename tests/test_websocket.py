import pytest
from fastapi.testclient import TestClient
from fastapi import WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ticketing_app.models import User, Ticket
from ticketing_app.auth import create_access_token, get_password_hash
from ticketing_app.main import app
import json

@pytest.fixture
def client():
    return TestClient(app)

def test_websocket_authentication_required(client: TestClient):
    """Test WebSocket requires authentication"""
    with client.websocket_connect("/ws/tickets/1") as websocket:
        # Should receive auth error if no token provided
        websocket.send_json({"message": "hello"})
        data = websocket.receive_json()
        assert "error" in data
        assert "Authentication token required" in data["error"]

def test_websocket_invalid_token_rejected(client: TestClient):
    """Test WebSocket rejects invalid tokens"""
    with client.websocket_connect("/ws/tickets/1") as websocket:
        websocket.send_json({"token": "invalid_token"})
        data = websocket.receive_json()
        assert "error" in data
        assert "Authentication failed" in data["error"]

