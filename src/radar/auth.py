"""Acceso opcional por clave de acceso para cuando Radar se expone fuera de localhost (túnel/VPS).

Sin `RADAR_ACCESS_TOKEN` no hay autenticación (uso local en 127.0.0.1). Con ella, todo `/api/*`
salvo salud y login exige la cookie de sesión o `Authorization: Bearer <clave>`.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

COOKIE = "radar_session"
PUBLIC_PATHS = {"/api/health", "/api/auth/login", "/api/auth/status"}
MAX_ATTEMPTS = 5
WINDOW_SECONDS = 60
_attempts: dict[str, list[float]] = defaultdict(list)

router = APIRouter(prefix="/api/auth")


def access_token() -> str | None:
    return os.getenv("RADAR_ACCESS_TOKEN") or None


def _session_value(token: str) -> str:
    return hmac.new(token.encode(), b"radar-session-v1", hashlib.sha256).hexdigest()


def is_authenticated(request: Request) -> bool:
    token = access_token()
    if token is None:
        return True
    cookie = request.cookies.get(COOKIE, "")
    if cookie and hmac.compare_digest(cookie, _session_value(token)):
        return True
    header = request.headers.get("authorization", "")
    return header.startswith("Bearer ") and hmac.compare_digest(header[7:], token)


class AccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/") and path not in PUBLIC_PATHS and not is_authenticated(request):
            return JSONResponse({"detail": "Autenticación requerida"}, status_code=401)
        return await call_next(request)


class Login(BaseModel):
    token: str = Field(min_length=1, max_length=200)


@router.get("/status")
def status(request: Request) -> dict[str, bool]:
    return {"required": access_token() is not None, "authenticated": is_authenticated(request)}


@router.post("/login")
def login(payload: Login, request: Request, response: Response) -> dict[str, bool]:
    token = access_token()
    if token is None:
        return {"authenticated": True}
    client = request.client.host if request.client else "?"
    now = time.monotonic()
    recent = [t for t in _attempts[client] if now - t < WINDOW_SECONDS]
    if len(recent) >= MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Demasiados intentos; espera un minuto")
    if not hmac.compare_digest(payload.token, token):
        recent.append(now)
        _attempts[client] = recent
        raise HTTPException(status_code=401, detail="Clave incorrecta")
    _attempts.pop(client, None)
    response.set_cookie(
        COOKIE, _session_value(token), httponly=True, samesite="strict",
        secure=request.url.scheme == "https", max_age=60 * 60 * 24 * 30, path="/",
    )
    return {"authenticated": True}


@router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(COOKIE, path="/")
    return {"authenticated": False}
