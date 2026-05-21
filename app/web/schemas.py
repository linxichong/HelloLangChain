from pydantic import BaseModel


class ChatRequest(BaseModel):
    provider: str = "gemini"
    analysis_mode: str = "standard"
    role: str = "通用"
    language: str = "中文"
    style: str | None = None
    question: str
    use_memory: bool = True


class ChatResponse(BaseModel):
    provider: str
    provider_label: str
    model: str
    analysis_mode: str
    answer: str
    confidence: float


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
