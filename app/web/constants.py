from pathlib import Path

from app.llm.clients import DeepSeekClient, GeminiFlashClient, OpenAIClient


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
