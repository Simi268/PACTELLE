from uuid import UUID
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, ConfigDict, Field


class OrganizationMemberResponse(BaseModel):
    user_id: UUID
    full_name: str
    email: EmailStr
    role: str
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrganizationMemberInviteRequest(BaseModel):
    email: EmailStr
    role: str = Field(default="member")


class OrganizationMemberRoleUpdateRequest(BaseModel):
    role: Literal["admin", "member"]