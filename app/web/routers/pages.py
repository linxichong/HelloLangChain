from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.web.constants import BASE_DIR


router = APIRouter()


@router.get("/")
def index() -> FileResponse:
    return FileResponse(BASE_DIR / "templates" / "index.html")


@router.get("/login")
def login_page() -> FileResponse:
    return FileResponse(BASE_DIR / "templates" / "login.html")


@router.get("/register")
def register_page() -> FileResponse:
    return FileResponse(BASE_DIR / "templates" / "register.html")
