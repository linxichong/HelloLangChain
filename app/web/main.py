import os

from app.config.env_loader import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.db import auth_store
from app.db.connection import close_pool
from app.web.constants import BASE_DIR
from app.web.routers import auth, chat, models, pages, users


app = FastAPI(title="Multi Model Chat")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

app.include_router(pages.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(models.router)
app.include_router(chat.router)


@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=()",
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "img-src 'self' data:; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'",
    )
    return response


@app.on_event("startup")
def startup() -> None:
    auth_store.init_auth_store()


@app.on_event("shutdown")
def shutdown() -> None:
    close_pool()


def main() -> None:
    import uvicorn

    host = os.getenv("CHAT_HOST", "127.0.0.1")
    port = int(os.getenv("CHAT_PORT", "8000"))
    uvicorn.run("app.web.main:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    main()
