from fastapi import APIRouter, Depends, HTTPException, status

from app.db import auth_store
from app.db.auth_store import AuthUser
from app.web.dependencies import get_current_user
from app.web.schemas import CreateUserRequest, UserResponse


router = APIRouter(prefix="/api/users", tags=["users"])


@router.post("", response_model=UserResponse)
def create_user(
    request: CreateUserRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> UserResponse:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有超级用户可以创建用户",
        )

    user = auth_store.create_user(request.username, request.password, request.role)
    return UserResponse(username=user.username, role=user.role)
