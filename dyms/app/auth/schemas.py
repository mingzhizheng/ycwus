from pydantic import BaseModel
from typing import Optional, List


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class RefreshRequest(BaseModel):
    refresh_token: str


class UserCreate(BaseModel):
    username: str
    password: str
    display_name: str
    role: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None
    dmv_number: Optional[str] = None
    facility_ids: List[int] = [1]


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None
    is_active: bool
