from fastapi import WebSocket
from typing import Dict, List, Optional
import json
from datetime import datetime
from ticketing_app.models import User


class ConnectionManager:
    def __init__(self):
        # Store active connections per ticket with user info
        self.active_connections: Dict[int, List[Dict]] = {}

    async def connect(self, websocket: WebSocket, ticket_id: int, user: User):
        """Accept WebSocket connection and add to ticket channel"""
        if ticket_id not in self.active_connections:
            self.active_connections[ticket_id] = []

        connection_info = {
            "websocket": websocket,
            "user_id": user.id,
            "user_email": user.email,
            "user_role": user.role
        }

        self.active_connections[ticket_id].append(connection_info)

    def disconnect(self, websocket: WebSocket, ticket_id: int):
        """Remove WebSocket connection from ticket channel"""
        if ticket_id in self.active_connections:
            self.active_connections[ticket_id] = [
                conn for conn in self.active_connections[ticket_id]
                if conn["websocket"] != websocket
            ]

            # Clean up empty channels
            if not self.active_connections[ticket_id]:
                del self.active_connections[ticket_id]

    async def send_to_ticket(
        self,
        ticket_id: int,
        message: dict,
        exclude_user_id: Optional[int] = None
    ):
        """Send message to all connections in a ticket channel"""
        if ticket_id in self.active_connections:
            message_text = json.dumps(message)

            # Send to all connections, remove dead ones
            dead_connections = []
            for connection_info in self.active_connections[ticket_id]:
                # Skip if excluding specific user
                if exclude_user_id and connection_info["user_id"] == exclude_user_id:
                    continue

                try:
                    await connection_info["websocket"].send_text(message_text)
                except Exception as e:
                    print(f"Failed to send WebSocket message: {e}")
                    dead_connections.append(connection_info)

            # Remove dead connections
            for dead_conn in dead_connections:
                if dead_conn in self.active_connections[ticket_id]:
                    self.active_connections[ticket_id].remove(dead_conn)

    async def send_status_update(self, ticket_id: int, new_status: str, updated_by_user_id: int):
        """Send ticket status update to all connected clients"""
        message = {
            "type": "status_update",
            "ticket_id": ticket_id,
            "new_status": new_status,
            "updated_by": updated_by_user_id,
            "timestamp": json.loads(json.dumps(datetime.utcnow(), default=str))
        }
        await self.send_to_ticket(ticket_id, message)

    def get_connected_users(self, ticket_id: int) -> List[Dict]:
        """Get list of connected users for a ticket"""
        if ticket_id in self.active_connections:
            return [
                {
                    "user_id": conn["user_id"],
                    "email": conn["user_email"],
                    "role": conn["user_role"]
                }
                for conn in self.active_connections[ticket_id]
            ]
        return []


# Global connection manager instance
manager = ConnectionManager()
