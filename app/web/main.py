import asyncio
import os
import time
from pathlib import Path
from typing import Any

from app.config.env_loader import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agents.stock_agent import invoke_stock_agent
from app.chains.chat_chain import ChatResult, invoke_chat
from app.db import auth_store
from app.db.auth_store import AuthUser
from app.llm.clients import DeepSeekClient, GeminiFlashClient, OpenAIClient
from app.tools.financial_tools import build_financial_context


BASE_DIR = Path(__file__).resolve().parents[2]


DEFAULT_STYLE = "简洁清晰，像 ChatGPT 一样先直接回答，再给必要的说明。"
MAX_MODEL_RETRIES = 2

CLIENTS = {
    "gemini": GeminiFlashClient,
    "openai": OpenAIClient,
    "deepseek": DeepSeekClient,
}

MODEL_LABELS = {
    "gemini": "Gemini",
    "openai": "OpenAI",
    "deepseek": "DeepSeek",
}

PROVIDER_API_KEYS = {
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

app = FastAPI(title="Multi Model Chat")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.on_event("startup")
def startup() -> None:
    auth_store.init_auth_store()


class ChatRequest(BaseModel):
    provider: str = "gemini"
    analysis_mode: str = "standard"
    role: str = "通用"
    language: str = "中文"
    style: str | None = None
    question: str
    use_memory: bool = True


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_at: str
    username: str
    role: str


class UserResponse(BaseModel):
    username: str
    role: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "normal"


class ChatResponse(BaseModel):
    provider: str
    provider_label: str
    model: str
    analysis_mode: str
    answer: str
    confidence: float


def get_bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证信息",
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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(BASE_DIR / "templates" / "index.html")


@app.get("/login")
def login_page() -> FileResponse:
    return FileResponse(BASE_DIR / "templates" / "login.html")


@app.get("/register")
def register_page() -> FileResponse:
    return FileResponse(BASE_DIR / "templates" / "register.html")


@app.post("/api/login", response_model=LoginResponse)
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


@app.post("/api/register", response_model=UserResponse)
def register(request: LoginRequest) -> UserResponse:
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


@app.post("/api/logout")
def logout(user_token: str = Depends(get_bearer_token)) -> dict[str, bool]:
    auth_store.delete_session(user_token)
    return {"ok": True}


@app.get("/api/me", response_model=UserResponse)
def me(user: AuthUser = Depends(get_current_user)) -> UserResponse:
    return UserResponse(username=user.username, role=user.role)


@app.post("/api/users", response_model=UserResponse)
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


@app.get("/api/models")
def list_models() -> list[dict[str, str | bool]]:
    return [
        {
            "provider": provider,
            "label": MODEL_LABELS[provider],
            "configured": is_provider_configured(provider),
        }
        for provider in CLIENTS
    ]


@app.post("/api/chat", response_model=ChatResponse)
async def chat_api(
    request: ChatRequest,
    user: AuthUser = Depends(get_current_user),
) -> ChatResponse:
    try:
        return await asyncio.to_thread(chat, request, user)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


@app.post("/api/reset")
def reset_memory(user: AuthUser = Depends(get_current_user)) -> dict[str, bool]:
    auth_store.clear_memory(user)
    return {"ok": True}


def chat(request: ChatRequest, user: AuthUser) -> ChatResponse:
    provider = request.provider.lower()
    analysis_mode = normalize_analysis_mode(request.analysis_mode)
    question = request.question.strip()
    if not question:
        raise ValueError("问题不能为空")

    client = make_client(provider)
    inputs = {
        "role": request.role,
        "language": request.language,
        "style": (request.style or "").strip() or DEFAULT_STYLE,
        "question": question,
        "history": build_history(user, provider) if request.use_memory else "本轮不使用历史对话。",
        "financial_context": (
            build_financial_context(question)
            if analysis_mode == "standard"
            else "Agent 模式会按需调用金融数据工具。"
        ),
    }

    result = invoke_chat_with_retries(client, inputs, analysis_mode)

    if request.use_memory:
        auth_store.append_memory(user, provider, "user", question)
        auth_store.append_memory(user, provider, "assistant", result.answer)

    return ChatResponse(
        provider=provider,
        provider_label=MODEL_LABELS.get(provider, provider),
        model=client.model,
        analysis_mode=analysis_mode,
        answer=result.answer,
        confidence=result.confidence,
    )


def make_client(provider: str):
    if provider not in CLIENTS:
        available = ", ".join(CLIENTS)
        raise ValueError(f"未知模型供应商：{provider}。可选值：{available}")
    return CLIENTS[provider]()


def is_provider_configured(provider: str) -> bool:
    api_key = PROVIDER_API_KEYS.get(provider)
    return api_key is None or bool(os.getenv(api_key))


def normalize_analysis_mode(value: str) -> str:
    mode = (value or "standard").lower()
    if mode in {"standard", "agent"}:
        return mode
    raise ValueError("未知分析模式。可选值：standard, agent")


def build_history(user: AuthUser, provider: str) -> str:
    messages = auth_store.get_history(user, provider)
    if not messages:
        return "暂无历史对话。"

    lines = []
    for message in messages:
        role = "用户" if message["role"] == "user" else "助手"
        lines.append(f"{role}：{message['content']}")
    return "\n".join(lines)


def invoke_chat_with_retries(
    client: Any,
    inputs: dict[str, Any],
    analysis_mode: str,
) -> ChatResult:
    last_error = None
    for attempt in range(MAX_MODEL_RETRIES + 1):
        try:
            if analysis_mode == "agent":
                return invoke_stock_agent(client, inputs)
            return invoke_chat(client, inputs)
        except Exception as exc:
            last_error = exc
            if attempt < MAX_MODEL_RETRIES:
                time.sleep(1)

    raise RuntimeError(f"模型调用连续失败：{type(last_error).__name__}: {last_error}")


def main() -> None:
    import uvicorn

    host = os.getenv("CHAT_HOST", "127.0.0.1")
    port = int(os.getenv("CHAT_PORT", "8000"))
    uvicorn.run("app.web.main:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    main()
