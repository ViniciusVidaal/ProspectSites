from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Request
from pwdlib import PasswordHash

from .config import get_settings

password_hash = PasswordHash.recommended()
ALGORITHM = "HS256"


def authenticate(email: str, password: str) -> bool:
    settings = get_settings()
    if email.strip().casefold() != settings.admin_email.strip().casefold():
        return False
    return password_hash.verify(password, settings.admin_password_hash)


def create_access_token(email: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": email,
            "iat": now,
            "exp": now + timedelta(hours=12),
        },
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )


def require_auth(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Autenticação necessária.")
    try:
        payload = jwt.decode(
            token,
            get_settings().jwt_secret,
            algorithms=[ALGORITHM],
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada.") from exc
    email = str(payload.get("sub", ""))
    if email.casefold() != get_settings().admin_email.casefold():
        raise HTTPException(status_code=401, detail="Sessão inválida.")
    return email
