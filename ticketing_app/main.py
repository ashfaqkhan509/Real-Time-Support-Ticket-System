from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy import select

from ticketing_app.database import create_tables, AsyncSessionLocal
from ticketing_app.routes import auth_routes, ticket_routes
from ticketing_app.websocket.manager import ConnectionManager
from ticketing_app.models import User, Ticket, UserRole
from ticketing_app.auth import verify_token


# Initialize rate limiter with Redis
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Support Ticket System", version="1.0.0")

# Add rate limiting middleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket connection manager
manager = ConnectionManager()

# Include routers
app.include_router(auth_routes.router, prefix="/auth", tags=["Authentication"])
app.include_router(ticket_routes.router, prefix="/tickets", tags=["Tickets"])


@app.on_event("startup")
async def startup_event():
    await create_tables()


@app.websocket("/ws/tickets/{ticket_id}")
async def websocket_endpoint(websocket: WebSocket, ticket_id: int):
    """WebSocket endpoint for real-time ticket updates"""
    await websocket.accept()

    try:
        # Wait for authentication token
        auth_message = await websocket.receive_json()
        token = auth_message.get("token")

        if not token:
            await websocket.send_json({"error": "Authentication token required"})
            await websocket.close()
            return

        # Verify token and get user
        try:
            email = verify_token(token)
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(User).where(User.email == email))
                user = result.scalar_one_or_none()

                if not user:
                    await websocket.send_json({"error": "Invalid user"})
                    await websocket.close()
                    return

                # Check if user has access to this ticket
                ticket_result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
                ticket = ticket_result.scalar_one_or_none()

                if not ticket:
                    await websocket.send_json({"error": "Ticket not found"})
                    await websocket.close()
                    return

                # Users can only access their own tickets, agents can access all
                if user.role == UserRole.USER and ticket.created_by != user.id:
                    await websocket.send_json({"error": "Access denied"})
                    await websocket.close()
                    return

        except Exception:
            await websocket.send_json({"error": "Authentication failed"})
            await websocket.close()
            return

        # Add to connection manager with user info
        await manager.connect(websocket, ticket_id, user)
        await websocket.send_json({
            "type": "connected",
            "message": f"Connected to ticket {ticket_id}",
            "user": user.email,
            "role": user.role
        })

        # Hold connection until closed
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(websocket, ticket_id)
    except Exception as e:
        print(f"WebSocket error: {e}")
        await websocket.close()


@app.get("/")
async def root():
    return {"message": "Support Ticket System API"}
