from fastapi import APIRouter, Depends, HTTPException, status

from app.db import auth_store
from app.web.dependencies import get_bearer_token, get_current_user
from app.web.schemas import LoginRequest, LoginResponse, RegisterRequest, UserResponse


router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest) -> LoginResponse:
    user = auth_store.authenticate_user(request.username, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    token, expires_at = auth_store.create_session(user)
    return LoginResponse(
        token=token,
        expires_at=expires_at.isoformat(),
        username=user.username,
        role=user.role,
    )


@router.post("/register", response_model=UserResponse)
def register(request: RegisterRequest) -> UserResponse:
    if not auth_store.ENABLE_PUBLIC_REGISTRATION:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前未开放用户注册",
        )

    try:
        user = auth_store.create_user(request.username, request.password, "normal")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return UserResponse(username=user.username, role=user.role)


@router.post("/logout")
def logout(user_token: str = Depends(get_bearer_token)) -> dict[str, bool]:
    auth_store.delete_session(user_token)
    return {"ok": True}


@router.get("/me", response_model=UserResponse)
def me(user=Depends(get_current_user)) -> UserResponse:
    return UserResponse(username=user.username, role=user.role)
