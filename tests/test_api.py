import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ticketing_app.models import User, Ticket, Reply
import httpx
from ticketing_app.auth import get_password_hash


@pytest.mark.asyncio
async def test_signup_success(
    client: httpx.AsyncClient,
    db_session: AsyncSession
):
    """Test successful user signup."""
    payload = {
        "email": "testuser@example.com",
        "password": "testpass",
        "role": "user"
    }

    response = await client.post("/auth/signup", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "testuser@example.com"
    assert data["role"] == "user"

    # Verify database state
    result = await db_session.execute(
        select(User).where(User.email == "testuser@example.com"))
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.email == "testuser@example.com"


@pytest.mark.asyncio
async def test_signup_existing_user_fails(client: httpx.AsyncClient):
    """Test that signing up with an already registered email fails."""

    # First signup
    await client.post("/auth/signup", json={
        "email": "duplicate@example.com",
        "password": "testpass",
        "role": "user"
    })

    # Attempt duplicate signup
    response = await client.post("/auth/signup", json={
        "email": "duplicate@example.com",
        "password": "testpass",
        "role": "user"
    })

    assert response.status_code == 400
    assert "email already registered" in response.text.lower()


@pytest.mark.asyncio
async def test_login_success(client: httpx.AsyncClient):
    """Test successful user login."""
    # First sign up
    await client.post("/auth/signup", json={
        "email": "loginuser@example.com",
        "password": "testpass",
        "role": "user"
    })

    # Then login
    response = await client.post("/auth/login", data={
        "username": "loginuser@example.com",
        "password": "testpass"
    })

    assert response.status_code == 200
    json_data = response.json()
    assert "access_token" in json_data
    assert json_data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_password(client: httpx.AsyncClient):
    """Test login failure with incorrect password."""

    # First sign up
    await client.post("/auth/signup", json={
        "email": "test@example.com",
        "password": "correctpass",
        "role": "user"
    })

    # Try logging in with wrong password
    response = await client.post("/auth/login", data={
        "username": "test@example.com",
        "password": "wrongpass"
    })

    assert response.status_code == 401
    assert "incorrect email or password" in response.text.lower()


# Helper function to get auth token
async def get_auth_token(
    client: httpx.AsyncClient,
    email: str,
    password: str
):
    response = await client.post("/auth/login", data={
        "username": email,
        "password": password
    })
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_create_ticket_success(
    client: httpx.AsyncClient,
    db_session: AsyncSession
):
    """Test successful ticket creation by regular user"""
    # First sign up a user
    await client.post("/auth/signup", json={
        "email": "test@example.com",
        "password": "testpass",
        "role": "user"
    })

    # Get auth token
    token = await get_auth_token(client, "test@example.com", "testpass")

    # Create ticket
    payload = {
        "title": "Test Ticket",
        "description": "This is a test ticket",
        "status": "open"
    }

    response = await client.post(
        "/tickets/",
        json=payload,
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Test Ticket"
    assert data["description"] == "This is a test ticket"
    assert data["status"] == "open"

    # Verify database state
    result = await db_session.execute(select(Ticket))
    ticket = result.scalars().first()
    assert ticket is not None
    assert ticket.title == "Test Ticket"


@pytest.mark.asyncio
async def test_create_ticket_rate_limited(client: httpx.AsyncClient):
    """Test ticket creation rate limiting"""
    # Sign up user
    await client.post("/auth/signup", json={
        "email": "test@example.com",
        "password": "testpass",
        "role": "user"
    })
    token = await get_auth_token(client, "test@example.com", "testpass")

    payload = {
        "title": "Test Ticket",
        "description": "This is a test ticket",
        "status": "open"
    }

    # Make 5 requests quickly (should all succeed)
    for _ in range(5):
        response = await client.post(
            "/tickets/",
            json=payload,
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    # 6th request should be rate limited
    response = await client.post(
        "/tickets/",
        json=payload,
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 429


@pytest.mark.asyncio
async def test_get_ticket_success(
    client: httpx.AsyncClient,
    db_session: AsyncSession
):
    """Test successful ticket retrieval"""
    # Create a test user and ticket directly in DB
    test_user = User(
        email="test@example.com",
        hashed_password=get_password_hash("testpass"),
        role="user"
    )
    db_session.add(test_user)
    await db_session.commit()

    test_ticket = Ticket(
        title="Existing Ticket",
        description="Existing description",
        status="open",
        created_by=test_user.id
    )
    db_session.add(test_ticket)
    await db_session.commit()

    # Get auth token
    token = await get_auth_token(client, "test@example.com", "testpass")

    # Get ticket
    response = await client.get(
        f"/tickets/{test_ticket.id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Existing Ticket"
    assert data["id"] == test_ticket.id


@pytest.mark.asyncio
async def test_get_ticket_not_found(client: httpx.AsyncClient):
    """Test getting non-existent ticket"""
    # Sign up user
    await client.post("/auth/signup", json={
        "email": "test@example.com",
        "password": "testpass",
        "role": "user"
    })
    token = await get_auth_token(client, "test@example.com", "testpass")

    # Try to get non-existent ticket
    response = await client.get(
        "/tickets/999999",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404
    assert "ticket not found" in response.text.lower()


@pytest.mark.asyncio
async def test_get_ticket_unauthorized(
    client: httpx.AsyncClient,
    db_session: AsyncSession
):
    """Test user cannot access another user's ticket"""
    # Create two users
    user1 = User(
        email="user1@example.com",
        hashed_password=get_password_hash("hashedpass"),
        role="user"
    )
    user2 = User(
        email="user2@example.com",
        hashed_password=get_password_hash("hashedpass"),
        role="user"
    )
    db_session.add_all([user1, user2])
    await db_session.commit()
    await db_session.refresh(user1)
    await db_session.refresh(user2)

    # Create ticket for user1
    ticket = Ticket(
        title="User1's Ticket",
        description="ticket 1 description",
        status="open",
        created_by=user1.id
    )
    db_session.add(ticket)
    await db_session.commit()

    # Get token for user2
    token = await get_auth_token(client, "user2@example.com", "hashedpass")

    # User2 tries to access user1's ticket
    response = await client.get(
        f"/tickets/{ticket.id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403
    assert "only view your own tickets" in response.text.lower()


@pytest.mark.asyncio
async def test_reply_to_ticket_success(
    client: httpx.AsyncClient,
    db_session: AsyncSession
):
    """Test agent can reply to ticket"""
    # Create user and agent
    user = User(
        email="ticketowner@example.com",
        hashed_password=get_password_hash("hashedpass"),
        role="user"
    )
    agent = User(
        email="agent@example.com",
        hashed_password=get_password_hash("hashedpass"),
        role="agent"
    )
    db_session.add_all([user, agent])
    await db_session.commit()
    await db_session.refresh(user)
    await db_session.refresh(agent)

    # Create ticket
    ticket = Ticket(
        title="Need Help",
        description="I need assistance",
        status="open",
        created_by=user.id
    )
    db_session.add(ticket)
    await db_session.commit()

    # Get agent token
    token = await get_auth_token(client, "agent@example.com", "hashedpass")

    # Post reply
    response = await client.post(
        f"/tickets/{ticket.id}/reply",
        json={"message": "test reply"},
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "test reply"

    # Verify reply in database
    result = await db_session.execute(select(Reply))
    reply = result.scalar_one_or_none()
    assert reply is not None
    assert reply.message == "test reply"


@pytest.mark.asyncio
async def test_reply_to_ticket_non_agent_fails(
    client: httpx.AsyncClient,
    db_session: AsyncSession
):
    """Test regular user cannot reply to tickets"""
    # Create user and ticket
    user = User(
        email="user@example.com",
        hashed_password=get_password_hash("hashedpass"),
        role="user"
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    ticket = Ticket(
        title="My Ticket",
        description="My issue",
        status="open",
        created_by=user.id
    )
    db_session.add(ticket)
    await db_session.commit()

    # Get user token
    token = await get_auth_token(client, "user@example.com", "hashedpass")

    # Attempt to reply
    response = await client.post(
        f"/tickets/{ticket.id}/reply",
        json={"message": "I'm trying to reply"},
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_ticket_status_success(
    client: httpx.AsyncClient,
    db_session: AsyncSession
):
    """Test agent can update ticket status"""

    # Create user, agent, and ticket
    user = User(
        email="user@example.com",
        hashed_password=get_password_hash("hashedpass"),
        role="user"
    )
    agent = User(
        email="agent@example.com",
        hashed_password=get_password_hash("hashedpass"),
        role="agent"
    )
    db_session.add_all([user, agent])
    await db_session.commit()
    await db_session.refresh(user)
    await db_session.refresh(agent)

    ticket = Ticket(
        title="Status Ticket",
        description="Test status change",
        status="open",
        created_by=user.id
    )
    db_session.add(ticket)
    await db_session.commit()

    # Get agent token
    token = await get_auth_token(client, "agent@example.com", "hashedpass")

    # Update status
    response = await client.patch(
        f"/tickets/{ticket.id}/status",
        json={"status": "in_progress"},
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "in_progress"

    # Verify database update
    result = await db_session.execute(
        select(Ticket).where(Ticket.id == ticket.id))
    updated_ticket = result.scalar_one()
    assert updated_ticket.status == "in_progress"


@pytest.mark.asyncio
async def test_list_tickets_user_sees_only_own(
    client: httpx.AsyncClient,
    db_session: AsyncSession
):
    """Test user only sees their own tickets"""

    # Create two users
    user1 = User(
        email="user1@example.com",
        hashed_password=get_password_hash("hashedpass"),
        role="user"
    )
    user2 = User(
        email="user2@example.com",
        hashed_password=get_password_hash("hashedpass"),
        role="user"
    )
    db_session.add_all([user1, user2])
    await db_session.commit()
    await db_session.refresh(user1)
    await db_session.refresh(user2)

    # Create tickets for both users
    ticket1 = Ticket(
        title="User1 Ticket",
        description="Desc",
        status="open",
        created_by=user1.id
    )
    ticket2 = Ticket(
        title="User2 Ticket",
        description="Desc",
        status="open",
        created_by=user2.id
    )
    db_session.add_all([ticket1, ticket2])
    await db_session.commit()

    # Get token for user1
    token = await get_auth_token(client, "user1@example.com", "hashedpass")

    # List tickets
    response = await client.get(
        "/tickets/",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "User1 Ticket"
    assert data[0]["created_by"] == user1.id


@pytest.mark.asyncio
async def test_list_tickets_agent_sees_all(
    client: httpx.AsyncClient,
    db_session: AsyncSession
):
    """Test agent sees all tickets"""

    # Create users and agent
    user1 = User(
        email="user1@example.com",
        hashed_password=get_password_hash("hashedpass"),
        role="user"
    )
    user2 = User(
        email="user2@example.com",
        hashed_password=get_password_hash("hashedpass"),
        role="user"
    )
    agent = User(
        email="agent@example.com",
        hashed_password=get_password_hash("hashedpass"),
        role="agent"
    )
    db_session.add_all([user1, user2, agent])
    await db_session.commit()
    await db_session.refresh(user1)
    await db_session.refresh(user2)
    await db_session.refresh(agent)

    # Create tickets
    ticket1 = Ticket(
        title="Ticket 1",
        description="Desc",
        status="open",
        created_by=user1.id
    )
    ticket2 = Ticket(
        title="Ticket 2",
        description="Desc",
        status="open",
        created_by=user2.id
    )
    db_session.add_all([ticket1, ticket2])
    await db_session.commit()

    # Get agent token
    token = await get_auth_token(client, "agent@example.com", "hashedpass")

    # List tickets
    response = await client.get(
        "/tickets/",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert {t["title"] for t in data} == {"Ticket 1", "Ticket 2"}
