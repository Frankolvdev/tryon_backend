from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import SupportTicketPriority, SupportTicketStatus


class SupportTicketCreate(BaseModel):
    subject: str = Field(min_length=3, max_length=255)
    message: str = Field(min_length=5)


class SupportTicketAdminUpdate(BaseModel):
    status: SupportTicketStatus | None = None
    priority: SupportTicketPriority | None = None
    admin_notes: str | None = None
    assigned_admin_user_id: int | None = None


class SupportTicketResponse(BaseModel):
    id: int
    user_id: int | None
    subject: str
    message: str
    status: SupportTicketStatus
    priority: SupportTicketPriority
    admin_notes: str | None
    assigned_admin_user_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)