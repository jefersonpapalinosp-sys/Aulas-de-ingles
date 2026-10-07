"""Schemas de autenticação."""

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegistroIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128, description="No mínimo 8 caracteres.")
    display_name: str = Field(min_length=1, max_length=80)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class TokenOut(BaseModel):
    """O access token volta no corpo; o refresh vai em cookie httpOnly."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Validade do access token, em segundos.")


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
