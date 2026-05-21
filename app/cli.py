import os

from app.config.env_loader import load_dotenv

load_dotenv()

from app.chains.chat_chain import stream_chat_print
from app.llm.clients import DeepSeekClient, GeminiFlashClient, OpenAIClient


def main() -> None:
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()

    clients = {
        "gemini": GeminiFlashClient,
        "openai": OpenAIClient,
        "deepseek": DeepSeekClient,
    }

    if provider not in clients:
        available_providers = ", ".join(clients)
        raise ValueError(f"未知供应商：{provider}。可选值：{available_providers}")

    client = clients[provider]()

    inputs = {
        "role": "小说推荐",
        "language": "中文",
        "style": "需要书名、作者、简介，按照 1、2、3 的格式列出",
        "question": "推荐一下2026年好看的小说。",
    }

    stream_chat_print(client, inputs)


if __name__ == "__main__":
    main()
