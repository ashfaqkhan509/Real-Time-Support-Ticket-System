from datetime import datetime
import enum

from sqlalchemy import String, Text, DateTime, ForeignKey, Enum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ticketing_app.database import Base


class UserRole(str, enum.Enum):
    USER = "user"
    AGENT = "agent"


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True
    )
    email: Mapped[str] = mapped_column(
        String,
        unique=True,
        index=True,
        nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(
        String,
        nullable=False
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole),
        default=UserRole.USER,
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    created_tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="creator", 
        foreign_keys="[Ticket.created_by]"
    )
    replies: Mapped[list["Reply"]] = relationship(
        back_populates="author"
    )


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True
    )
    title: Mapped[str] = mapped_column(
        String,
        nullable=False
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus),
        default=TicketStatus.OPEN,
        nullable=False
    )
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    creator: Mapped["User"] = relationship(
        back_populates="created_tickets",
        foreign_keys=[created_by]
    )
    replies: Mapped[list["Reply"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan"
    )


class Reply(Base):
    __tablename__ = "replies"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True
    )
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id"),
        nullable=False
    )
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    replied_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    ticket: Mapped["Ticket"] = relationship(
        back_populates="replies"
    )
    author: Mapped["User"] = relationship(
        back_populates="replies"
    )
