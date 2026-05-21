import time
from typing import Any

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.llm.clients import BaseChatClient


class ChatResult(BaseModel):
    answer: str = Field(description="最终回答内容")
    confidence: float = Field(description="回答可信度，范围是 0 到 1")


output_parser = JsonOutputParser(pydantic_object=ChatResult)

prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是一个{role}助手。必须用{language}回答，并保持{style}的风格。\n"
            "如果涉及金融分析，必须优先使用提供的金融数据上下文；"
            "股票分析要覆盖趋势、量能、换手、关键价格区间、风险点和数据时间；"
            "明确区分事实、推断和不确定性；不得承诺收益；不得把回答写成投资建议。\n"
            "{format_instructions}",
        ),
        (
            "human",
            "历史对话：\n{history}\n\n"
            "金融数据上下文：\n{financial_context}\n\n"
            "当前问题：{question}",
        ),
    ]
).partial(format_instructions=output_parser.get_format_instructions())


def build_chat_chain(client: BaseChatClient):
    return prompt | client.llm | output_parser


def normalize_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(inputs)
    normalized.setdefault("history", "暂无历史对话。")
    normalized.setdefault("financial_context", "未提供金融数据上下文。")
    return normalized


def invoke_chat(client: BaseChatClient, inputs: dict[str, Any]) -> ChatResult:
    result = build_chat_chain(client).invoke(normalize_inputs(inputs))
    return ChatResult.model_validate(result)


def stream_chat_print(
    client: BaseChatClient,
    inputs: dict[str, Any],
    max_retries: int = 2,
) -> None:
    inputs = normalize_inputs(inputs)
    _print_header(client, inputs)

    for attempt in range(max_retries + 1):
        if attempt > 0:
            print(f"\n第 {attempt + 1} 次尝试：")

        try:
            result = _stream_once(client, inputs)
        except Exception as exc:
            if attempt < max_retries:
                print(f"\n流式调用失败，准备重试：{type(exc).__name__}: {exc}")
                time.sleep(1)
                continue

            print(f"\n流式调用连续失败，降级为普通调用：{type(exc).__name__}: {exc}")
            result = invoke_chat(client, inputs)
            print(result.answer)
            print(f"\n可信度：{result.confidence:.2f}")
            return

        if result.confidence is not None:
            print(f"\n可信度：{result.confidence:.2f}")
        return


def _print_header(client: BaseChatClient, inputs: dict[str, Any]) -> None:
    print(f"供应商：{client.provider}")
    print(f"模型：{client.model}")
    print("链式：prompt | llm | output_parser")
    print(f"问题：{inputs['question']}")
    print()


def _stream_once(client: BaseChatClient, inputs: dict[str, Any]) -> ChatResult:
    chain = build_chat_chain(client)
    printed_answer = ""
    latest_confidence = None

    print("回答：")

    for chunk in chain.stream(inputs):
        answer = chunk.get("answer")
        if answer and len(answer) > len(printed_answer):
            print(answer[len(printed_answer) :], end="", flush=True)
            printed_answer = answer

        if "confidence" in chunk:
            latest_confidence = chunk["confidence"]

    print()
    return ChatResult(answer=printed_answer, confidence=latest_confidence or 0)
