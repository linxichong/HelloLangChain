from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Provider = Literal["gemini", "openai", "deepseek"]
AnalysisMode = Literal["standard", "agent"]
ChatRole = Literal["通用", "Python 编程", "小说推荐", "金融专家", "翻译", "学习教练"]
Language = Literal["中文", "English", "日本語"]
UserRole = Literal["normal", "superuser"]


class StrictRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChatRequest(StrictRequestModel):
    provider: Provider = "gemini"
    analysis_mode: AnalysisMode = "standard"
    role: ChatRole = "通用"
    language: Language = "中文"
    style: str | None = Field(default=None, max_length=200)
    question: str = Field(min_length=1, max_length=4000)
    use_memory: bool = True

    @field_validator("provider", "analysis_mode", mode="before")
    @classmethod
    def normalize_lowercase_fields(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("question", mode="before")
    @classmethod
    def strip_question(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("style", mode="before")
    @classmethod
    def strip_style(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class ChatResponse(BaseModel):
    provider: str
    provider_label: str
    model: str
    analysis_mode: str
    answer: str
    confidence: float


class UsernameRequest(StrictRequestModel):
    username: str = Field(min_length=3, max_length=64)

    @field_validator("username", mode="before")
    @classmethod
    def validate_username(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        value = value.strip()
        if any(char.isspace() for char in value):
            raise ValueError("用户名不能包含空白字符")
        if any(ord(char) < 32 for char in value):
            raise ValueError("用户名不能包含控制字符")
        return value


class LoginRequest(UsernameRequest):
    password: str = Field(min_length=1, max_length=128)


class RegisterRequest(UsernameRequest):
    password: str = Field(min_length=8, max_length=128)


class LoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_at: str
    username: str
    role: str


class UserResponse(BaseModel):
    username: str
    role: str


class CreateUserRequest(RegisterRequest):
    role: UserRole = "normal"
