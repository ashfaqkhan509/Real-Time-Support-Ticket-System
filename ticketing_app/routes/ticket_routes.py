from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List
from slowapi import Limiter
from slowapi.util import get_remote_address
from ticketing_app.database import get_db
from ticketing_app.models import User, Ticket, Reply, UserRole
from ticketing_app.schemas import (
    TicketCreate,
    TicketResponse,
    TicketWithReplies,
    ReplyCreate,
    ReplyResponse
)
from ticketing_app.dependencies import (
    get_current_user,
    get_current_agent,
    get_current_regular_user
)
from ticketing_app.websocket.manager import manager
from ticketing_app.tasks.celery_tasks import send_reply_notification, log_reply_event

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post("/", response_model=TicketResponse)
@limiter.limit("5/minute")
async def create_ticket(
    request: Request,
    ticket_data: TicketCreate,
    current_user: User = Depends(get_current_regular_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new support ticket (users only)"""
    db_ticket = Ticket(
        title=ticket_data.title,
        description=ticket_data.description,
        status=ticket_data.status,
        created_by=current_user.id
    )

    db.add(db_ticket)
    await db.commit()
    await db.refresh(db_ticket)

    # Load creator relationship
    result = await db.execute(
        select(Ticket)
        .options(selectinload(Ticket.creator))
        .where(Ticket.id == db_ticket.id)
    )
    ticket_with_creator = result.scalar_one()

    return ticket_with_creator


@router.get("/{ticket_id}", response_model=TicketWithReplies)
async def get_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get ticket details with replies"""
    result = await db.execute(
        select(Ticket)
        .options(
            selectinload(Ticket.creator),
            selectinload(Ticket.replies).selectinload(Reply.author)
        )
        .where(Ticket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found"
        )

    # Users can only see their own tickets, agents can see all
    if current_user.role == UserRole.USER and ticket.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own tickets"
        )

    return ticket


@router.post("/{ticket_id}/reply", response_model=ReplyResponse)
async def reply_to_ticket(
    ticket_id: int,
    reply_data: ReplyCreate,
    current_user: User = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db)
):
    """Add a reply to a ticket (agents only)"""
    # Check if ticket exists
    result = await db.execute(
        select(Ticket)
        .options(selectinload(Ticket.creator))
        .where(Ticket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found"
        )

    # Create reply
    db_reply = Reply(
        ticket_id=ticket_id,
        message=reply_data.message,
        replied_by=current_user.id
    )

    db.add(db_reply)
    await db.commit()
    await db.refresh(db_reply)

    # Load author relationship
    result = await db.execute(
        select(Reply)
        .options(selectinload(Reply.author))
        .where(Reply.id == db_reply.id)
    )
    reply_with_author = result.scalar_one()

    # Send real-time update via WebSocket to all connected clients except the sender
    await manager.send_to_ticket(ticket_id, {
        "type": "new_reply",
        "reply": {
            "id": reply_with_author.id,
            "message": reply_with_author.message,
            "author": {
                "id": reply_with_author.author.id,
                "email": reply_with_author.author.email,
                "role": reply_with_author.author.role
            },
            "created_at": reply_with_author.created_at.isoformat()
        },
        "ticket_id": ticket_id
    }, exclude_user_id=current_user.id)

    # Send background tasks
    send_reply_notification.delay(ticket.creator.email, ticket.title, reply_data.message)
    log_reply_event.delay(ticket_id, current_user.id, reply_data.message)

    return reply_with_author


@router.patch("/{ticket_id}/status", response_model=TicketResponse)
async def update_ticket_status(
    ticket_id: int,
    status_update: dict,
    current_user: User = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db)
):
    """Update ticket status (agents only)"""
    # Check if ticket exists
    result = await db.execute(
        select(Ticket)
        .options(selectinload(Ticket.creator))
        .where(Ticket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found"
        )

    # Update status
    new_status = status_update.get("status")
    if new_status:
        old_status = ticket.status
        ticket.status = new_status
        await db.commit()
        await db.refresh(ticket)

        # Send real-time status update via WebSocket
        await manager.send_status_update(ticket_id, new_status, current_user.id)

        # Log status change
        log_reply_event.delay(
            ticket_id,
            current_user.id,
            f"Status changed from {old_status} to {new_status}"
        )

    return ticket


@router.get("/", response_model=List[TicketResponse])
async def list_tickets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List tickets (users see their own, agents see all)"""
    if current_user.role == UserRole.AGENT:
        # Agents can see all tickets
        result = await db.execute(
            select(Ticket)
            .options(selectinload(Ticket.creator))
            .order_by(Ticket.created_at.desc())
        )
    else:
        # Users can only see their own tickets
        result = await db.execute(
            select(Ticket)
            .options(selectinload(Ticket.creator))
            .where(Ticket.created_by == current_user.id)
            .order_by(Ticket.created_at.desc())
        )

    tickets = result.scalars().all()
    return tickets
