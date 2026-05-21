import os

from app.config.env_loader import load_dotenv
from langchain_deepseek import ChatDeepSeek
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

load_dotenv()


class BaseChatClient:
    provider: str
    model: str

    def __init__(self) -> None:
        self.llm = None


class OpenAIClient(BaseChatClient):
    def __init__(
        self,
        model: str | None = None,
        temperature: float = 0.3,
    ) -> None:
        super().__init__()
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("请先设置环境变量 OPENAI_API_KEY")

        self.provider = "OpenAI"
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        self.llm = ChatOpenAI(model=self.model, temperature=temperature)


class DeepSeekClient(BaseChatClient):
    def __init__(
        self,
        model: str | None = None,
        temperature: float = 0.3,
    ) -> None:
        super().__init__()
        if not os.getenv("DEEPSEEK_API_KEY"):
            raise RuntimeError("请先设置环境变量 DEEPSEEK_API_KEY")

        self.provider = "DeepSeek"
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        self.llm = ChatDeepSeek(model=self.model, temperature=temperature)


class GeminiFlashClient(BaseChatClient):
    def __init__(
        self,
        model: str | None = None,
        temperature: float = 0.3,
    ) -> None:
        super().__init__()
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("请先设置环境变量 GEMINI_API_KEY")

        self.provider = "Gemini"
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
        self.llm = ChatGoogleGenerativeAI(
            model=self.model,
            api_key=api_key,
            temperature=temperature,
        )
