"""
Slancio Crypto Algo Treding Engine — Auth Schemas
====================================
"""

from pydantic import BaseModel, EmailStr

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: str | None = None

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    is_active: bool
    bot_enabled: bool

    class Config:
        from_attributes = True
