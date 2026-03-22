"""Pydantic schemas for admin authentication."""

from __future__ import annotations

from pydantic import BaseModel


# ── Request ──────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


# ── Response ─────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
