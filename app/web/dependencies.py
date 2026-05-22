import os

from fastapi import Cookie, Depends, Header, HTTPException, status

from app.db import auth_store
from app.db.auth_store import AuthUser


AUTH_COOKIE_NAME = "hellolangchain_session"
AUTH_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
AUTH_COOKIE_SAMESITE = "lax"


def get_auth_token(
    authorization: str | None = Header(default=None),
    session_token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
) -> str:
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的认证信息",
            )
        return token

    if session_token:
        return session_token

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="请先登录",
    )


def get_bearer_token(token: str = Depends(get_auth_token)) -> str:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
        )
    return token


def get_current_user(token: str = Depends(get_bearer_token)) -> AuthUser:
    user = auth_store.get_user_by_token(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录已过期，请重新登录",
        )
    return user
