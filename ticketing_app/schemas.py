from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import List, Optional
from ticketing_app.models import UserRole, TicketStatus


# User schemas
class UserBase(BaseModel):
    email: EmailStr
    role: UserRole = UserRole.USER


class UserCreate(UserBase):
    password: str


class UserResponse(UserBase):
    id: int
    created_at: datetime


    class Config:
        from_attributes = True


# Auth schemas
class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    email: Optional[str] = None


# Ticket schemas
class TicketBase(BaseModel):
    title: str
    description: str
    status: TicketStatus = TicketStatus.OPEN


class TicketCreate(TicketBase):
    pass


class TicketUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TicketStatus] = None


class TicketResponse(TicketBase):
    id: int
    status: TicketStatus
    created_by: int
    created_at: datetime
    updated_at: datetime
    creator: UserResponse


    class Config:
        from_attributes = True


# Reply schemas
class ReplyBase(BaseModel):
    message: str


class ReplyCreate(ReplyBase):
    pass


class ReplyResponse(ReplyBase):
    id: int
    ticket_id: int
    replied_by: int
    created_at: datetime
    author: UserResponse


    class Config:
        from_attributes = True


# Ticket with replies
class TicketWithReplies(TicketResponse):
    replies: List[ReplyResponse] = []
