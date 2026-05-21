from typing import Any

from langchain.agents import create_agent

from app.chains.chat_chain import ChatResult
from app.llm.clients import BaseChatClient
from app.tools.financial_tools import financial_context_tool


STOCK_AGENT_PROMPT = (
    "你是专业但谨慎的股票分析助手。必须用用户要求的语言回答。\n"
    "当用户提出股票、行情、走势、技术面、公告或估值相关问题时，"
    "必须先调用 financial_context_tool 获取金融数据上下文，再基于数据回答。\n"
    "回答必须覆盖：数据时间、趋势、日 K、分时、量能、换手、关键价格、估值、行业/板块、公告和风险点。"
    "如果工具没有返回某项数据，要明确说明数据源未返回，不得编造。\n"
    "不得承诺收益，不得给出确定性涨跌判断，不得把回答写成投资建议。"
)


def invoke_stock_agent(client: BaseChatClient, inputs: dict[str, Any]) -> ChatResult:
    agent = create_agent(
        model=client.llm,
        tools=[financial_context_tool],
        system_prompt=STOCK_AGENT_PROMPT,
        response_format=ChatResult,
    )

    content = (
        f"角色：{inputs['role']}\n"
        f"语言：{inputs['language']}\n"
        f"风格：{inputs['style']}\n"
        f"历史对话：\n{inputs['history']}\n\n"
        f"当前问题：{inputs['question']}"
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": content}]},
        config={"recursion_limit": 6},
    )

    structured = result.get("structured_response")
    if structured is not None:
        return ChatResult.model_validate(structured)

    messages = result.get("messages") or []
    if messages:
        answer = getattr(messages[-1], "content", str(messages[-1]))
        return ChatResult(answer=str(answer), confidence=0.75)

    return ChatResult(answer="Agent 未返回有效回答。", confidence=0)
