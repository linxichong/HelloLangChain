import csv
import gzip
import json
import os
import re
import time
from io import StringIO
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.config.env_loader import load_dotenv
from langchain_core.tools import tool

load_dotenv()


SEC_USER_AGENT = os.getenv(
    "SEC_USER_AGENT",
    "HelloLangChain/0.1 contact@example.com",
)
HTTP_TIMEOUT = 12
MAX_SYMBOLS = 4
DEFAULT_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://quote.eastmoney.com/",
}
_ticker_cache: dict[str, Any] = {"loaded_at": 0, "data": {}}
_a_share_search_cache: dict[str, list[dict[str, str]]] = {}

A_SHARE_STOPWORDS = {
    "a股",
    "帮",
    "帮忙",
    "帮我",
    "分析",
    "看",
    "看看",
    "今天",
    "昨日",
    "昨天",
    "明天",
    "一下",
    "下",
    "想要",
    "请",
    "走势",
    "趋势",
    "行情",
    "股票",
    "股价",
    "个股",
    "最近",
    "现在",
    "技术面",
    "基本面",
    "为什么",
    "怎么",
    "如何",
    "的",
}


def extract_stock_symbols(text: str) -> list[str]:
    candidates = set(re.findall(r"\$?\b[A-Z]{1,5}\b", text))
    ignored = {
        "AI",
        "API",
        "CEO",
        "CFO",
        "CPI",
        "ETF",
        "EPS",
        "GDP",
        "IPO",
        "LLM",
        "PE",
        "ROE",
        "SEC",
        "USD",
    }
    symbols = [symbol.lstrip("$").upper() for symbol in candidates if symbol not in ignored]
    return sorted(symbols)[:MAX_SYMBOLS]


def build_financial_context(question: str) -> str:
    a_shares = extract_a_share_stocks(question)
    symbols = extract_stock_symbols(question)

    if not a_shares and not symbols:
        return "未识别到明确股票代码。"

    sections = []
    for stock in a_shares:
        sections.append(f"## {stock['name']}（{stock['code']}）")
        sections.append(get_a_share_quote(stock))

    for symbol in symbols:
        sections.append(f"## {symbol}")
        sections.append(get_stock_quote(symbol))
        sections.append(get_company_filings(symbol))
        sections.append(get_company_facts_summary(symbol))

    return "\n\n".join(sections)


def extract_a_share_stocks(text: str) -> list[dict[str, str]]:
    stocks: list[dict[str, str]] = []
    seen = set()

    for code in re.findall(r"(?<!\d)[036]\d{5}(?!\d)", text):
        stock = resolve_a_share_code(code)
        if stock and stock["secid"] not in seen:
            stocks.append(stock)
            seen.add(stock["secid"])

    for query in extract_chinese_stock_queries(text):
        for stock in search_a_share_stocks(query):
            if stock["secid"] in seen:
                continue
            stocks.append(stock)
            seen.add(stock["secid"])
            break
        if len(stocks) >= MAX_SYMBOLS:
            break

    return stocks[:MAX_SYMBOLS]


def extract_chinese_stock_queries(text: str) -> list[str]:
    normalized = text.lower()
    for word in sorted(A_SHARE_STOPWORDS, key=len, reverse=True):
        normalized = normalized.replace(word, " ")

    queries = []
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,12}", normalized):
        queries.extend(chinese_substrings(chunk))

    return unique_preserve_order(queries)


def chinese_substrings(text: str) -> list[str]:
    if len(text) <= 8:
        return [text]

    queries = []
    max_len = min(len(text), 8)
    for size in range(max_len, 1, -1):
        for start in range(0, len(text) - size + 1):
            queries.append(text[start : start + size])
    return queries


def search_a_share_stocks(query: str) -> list[dict[str, str]]:
    query = query.strip()
    if not query:
        return []
    if query in _a_share_search_cache:
        return _a_share_search_cache[query]

    url = (
        "https://searchapi.eastmoney.com/api/suggest/get"
        f"?input={quote(query)}&type=14&token=D43BF722C8E33BDC906FB84D85E326E8"
    )
    try:
        data = json.loads(http_get(url, headers=DEFAULT_HTTP_HEADERS))
    except Exception:
        _a_share_search_cache[query] = []
        return []

    rows = data.get("QuotationCodeTable", {}).get("Data") or []
    stocks = []
    for row in rows:
        if row.get("Classify") != "AStock":
            continue
        code = row.get("Code")
        name = row.get("Name")
        secid = row.get("QuoteID") or build_a_share_secid(code)
        if code and name and secid:
            stocks.append({"code": code, "name": name, "secid": secid})

    _a_share_search_cache[query] = stocks
    return stocks


def resolve_a_share_code(code: str) -> dict[str, str] | None:
    for stock in search_a_share_stocks(code):
        if stock["code"] == code:
            return stock

    secid = build_a_share_secid(code)
    if not secid:
        return None
    return {"code": code, "name": code, "secid": secid}


def build_a_share_secid(code: str | None) -> str | None:
    if not code:
        return None
    if code.startswith("6"):
        return f"1.{code}"
    if code.startswith(("0", "3")):
        return f"0.{code}"
    return None


def build_a_share_secucode(stock: dict[str, str]) -> str | None:
    code = stock.get("code")
    secid = stock.get("secid", "")
    if not code:
        return None
    if secid.startswith("1.") or code.startswith("6"):
        return f"{code}.SH"
    if secid.startswith("0.") or code.startswith(("0", "3")):
        return f"{code}.SZ"
    return None


def get_a_share_quote(stock: dict[str, str]) -> str:
    code = stock["code"]
    market_prefix = "sh" if stock["secid"].startswith("1.") else "sz"
    url = f"https://qt.gtimg.cn/q={market_prefix}{code}"

    try:
        text = http_get(url, headers={})
        snapshot = parse_tencent_a_share_snapshot(stock, text)
    except Exception as exc:
        return f"A 股行情数据：获取失败（{type(exc).__name__}: {exc}）。"

    sections = [
        format_a_share_snapshot(snapshot),
        get_a_share_industry_boards(stock),
        get_a_share_daily_kline_summary(stock, market_prefix, snapshot),
        get_a_share_intraday_summary(stock, market_prefix),
        get_a_share_announcements(stock),
    ]
    return "\n".join(section for section in sections if section)


def parse_tencent_a_share_snapshot(stock: dict[str, str], text: str) -> dict[str, str]:
    _, _, payload = text.partition('="')
    payload = payload.rstrip('";\n')
    fields = payload.split("~")
    if len(fields) < 39 or not fields[3]:
        return {"name": stock["name"], "code": stock["code"], "error": "未找到行情"}

    return {
        "name": fields[1] or stock["name"],
        "code": fields[2] or stock["code"],
        "latest": fields[3],
        "prev_close": fields[4],
        "open": fields[5],
        "timestamp": fields[30],
        "change": fields[31],
        "pct_change": fields[32],
        "high": fields[33],
        "low": fields[34],
        "volume_lots": fields[36],
        "amount_10k": fields[37],
        "turnover": fields[38],
        "pe_dynamic": field_at(fields, 39),
        "amplitude": field_at(fields, 43),
        "total_market_cap_yi": field_at(fields, 44),
        "float_market_cap_yi": field_at(fields, 45),
        "pb": field_at(fields, 46),
        "limit_up": field_at(fields, 47),
        "limit_down": field_at(fields, 48),
        "volume_ratio": field_at(fields, 49),
        "category": field_at(fields, 61),
        "float_shares": field_at(fields, 72),
        "source_time": field_at(fields, 30),
    }


def format_a_share_snapshot(snapshot: dict[str, str]) -> str:
    if snapshot.get("error"):
        return f"A 股行情数据：未找到 {snapshot['name']}（{snapshot['code']}）的行情。"

    source_time = format_market_timestamp(snapshot["source_time"])

    return (
        "A 股行情数据（腾讯行情，可能延迟）："
        f"名称={snapshot['name']}，代码={snapshot['code']}，数据时间={source_time}，"
        f"最新={snapshot['latest']}，涨跌额={snapshot['change']}，"
        f"涨跌幅={snapshot['pct_change']}%，今开={snapshot['open']}，"
        f"昨收={snapshot['prev_close']}，最高={snapshot['high']}，最低={snapshot['low']}，"
        f"振幅={snapshot['amplitude']}%，成交量={snapshot['volume_lots']}手，"
        f"成交额={snapshot['amount_10k']}万元，换手率={snapshot['turnover']}%，"
        f"量比={snapshot['volume_ratio']}，涨停价={snapshot['limit_up']}，"
        f"跌停价={snapshot['limit_down']}，总市值={snapshot['total_market_cap_yi']}亿元，"
        f"流通市值={snapshot['float_market_cap_yi']}亿元，动态市盈率={snapshot['pe_dynamic']}，"
        f"市净率={snapshot['pb']}，市场类别={snapshot['category']}。"
    )


def get_a_share_industry_boards(stock: dict[str, str]) -> str:
    secucode = build_a_share_secucode(stock)
    if not secucode:
        return "所属行业/板块：未识别交易所后缀。"

    url = (
        "https://datacenter.eastmoney.com/securities/api/data/v1/get"
        "?reportName=RPT_F10_CORETHEME_BOARDTYPE"
        "&columns=SECUCODE,SECURITY_CODE,SECURITY_NAME_ABBR,BOARD_NAME,BOARD_TYPE"
        f"&filter=(SECUCODE%3D%22{quote(secucode)}%22)"
        "&pageNumber=1&pageSize=30&source=HSF10&client=PC"
    )

    try:
        data = json.loads(http_get(url, headers=DEFAULT_HTTP_HEADERS))
    except Exception as exc:
        return f"所属行业/板块：获取失败（{type(exc).__name__}: {exc}）。"

    rows = data.get("result", {}).get("data") or []
    industries = unique_preserve_order(
        [row.get("BOARD_NAME", "") for row in rows if row.get("BOARD_TYPE") == "行业"]
    )
    boards = unique_preserve_order(
        [
            row.get("BOARD_NAME", "")
            for row in rows
            if row.get("BOARD_NAME") and row.get("BOARD_TYPE") != "行业"
        ]
    )

    industry_text = "、".join(industries[:5]) if industries else "未返回"
    board_text = "、".join(boards[:8]) if boards else "未返回"
    return f"所属行业/板块（东方财富 F10）：行业={industry_text}；相关概念/板块={board_text}。"


def get_a_share_daily_kline_summary(
    stock: dict[str, str],
    market_prefix: str,
    snapshot: dict[str, str],
) -> str:
    url = (
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        f"?param={market_prefix}{stock['code']},day,,,25,qfq"
    )

    try:
        data = json.loads(http_get(url, headers=DEFAULT_HTTP_HEADERS))
        rows = parse_tencent_klines(
            data.get("data", {}).get(f"{market_prefix}{stock['code']}", {}).get("qfqday", [])
        )
    except Exception as exc:
        return f"日 K 线数据：获取失败（{type(exc).__name__}: {exc}）。"

    if not rows:
        return "日 K 线数据：未返回数据。"

    latest = rows[-1]
    recent5 = rows[-5:]
    recent20 = rows[-20:] if len(rows) >= 20 else rows
    pct_5 = period_pct_change(rows, 5)
    pct_20 = period_pct_change(rows, 20)
    latest_volume = latest["volume"]
    avg5_volume = average(row["volume"] for row in recent5)
    avg20_volume = average(row["volume"] for row in recent20)
    float_shares = to_float(snapshot.get("float_shares", "0"))
    latest_turnover = turnover_from_volume(latest_volume, float_shares)
    avg5_turnover = turnover_from_volume(avg5_volume, float_shares)
    avg20_turnover = turnover_from_volume(avg20_volume, float_shares)
    volume_vs_5 = compare_to_average(latest_volume, avg5_volume)
    volume_vs_20 = compare_to_average(latest_volume, avg20_volume)

    return (
        "日 K 线摘要（腾讯行情，前复权，可能延迟）："
        f"最近交易日={latest['date']}，收盘={latest['close']}，"
        f"当日涨跌幅={format_optional_float(daily_pct_change(rows), '%')}，"
        f"当日换手率={format_optional_float(latest_turnover, '%')}，"
        f"近5个交易日涨跌幅={format_optional_float(pct_5, '%')}，"
        f"近20个交易日涨跌幅={format_optional_float(pct_20, '%')}，"
        f"最新成交量={latest_volume:.0f}手，5日均量={avg5_volume:.0f}手，"
        f"20日均量={avg20_volume:.0f}手，量能较5日均量={format_optional_float(volume_vs_5, '%')}，"
        f"量能较20日均量={format_optional_float(volume_vs_20, '%')}，"
        f"5日平均换手率={format_optional_float(avg5_turnover, '%')}，"
        f"20日平均换手率={format_optional_float(avg20_turnover, '%')}。"
    )


def parse_tencent_klines(klines: list[list[str]]) -> list[dict[str, float | str]]:
    rows = []
    for parts in klines:
        if len(parts) < 6:
            continue
        rows.append(
            {
                "date": parts[0],
                "open": to_float(parts[1]),
                "close": to_float(parts[2]),
                "high": to_float(parts[3]),
                "low": to_float(parts[4]),
                "volume": to_float(parts[5]),
            }
        )
    return rows


def get_a_share_intraday_summary(stock: dict[str, str], market_prefix: str) -> str:
    url = f"https://web.ifzq.gtimg.cn/appstock/app/minute/query?code={market_prefix}{stock['code']}"
    try:
        data = json.loads(http_get(url, headers=DEFAULT_HTTP_HEADERS))
        rows = parse_tencent_intraday_rows(
            data.get("data", {})
            .get(f"{market_prefix}{stock['code']}", {})
            .get("data", {})
            .get("data", [])
        )
        trade_date = (
            data.get("data", {})
            .get(f"{market_prefix}{stock['code']}", {})
            .get("data", {})
            .get("date")
        )
    except Exception as exc:
        return f"分时走势数据：获取失败（{type(exc).__name__}: {exc}）。"

    if not rows:
        return "分时走势数据：未返回数据，可能处于未开盘或数据源延迟。"

    first = rows[0]
    latest = rows[-1]
    high = max(rows, key=lambda item: item["price"])
    low = min(rows, key=lambda item: item["price"])
    morning = [row for row in rows if row["time"] <= "1130"]
    afternoon = [row for row in rows if row["time"] >= "1300"]
    morning_change = intraday_change(morning)
    afternoon_change = intraday_change(afternoon)

    return (
        "分时走势摘要（腾讯分时，可能延迟）："
        f"交易日={trade_date or '未知'}，首笔={first['time']} {first['price']}，"
        f"最新={latest['time']} {latest['price']}，"
        f"分时最高={high['time']} {high['price']}，分时最低={low['time']} {low['price']}，"
        f"上午段变化={format_optional_float(morning_change, '%')}，"
        f"下午段变化={format_optional_float(afternoon_change, '%')}，"
        f"累计成交量={latest['volume']:.0f}手，累计成交额={latest['amount'] / 100000000:.2f}亿元。"
    )


def parse_tencent_intraday_rows(rows: list[str]) -> list[dict[str, float | str]]:
    result = []
    for row in rows:
        parts = row.split()
        if len(parts) < 4:
            continue
        result.append(
            {
                "time": parts[0],
                "price": to_float(parts[1]),
                "volume": to_float(parts[2]),
                "amount": to_float(parts[3]),
            }
        )
    return result


def get_a_share_announcements(stock: dict[str, str]) -> str:
    url = (
        "https://np-anotice-stock.eastmoney.com/api/security/ann"
        f"?sr=-1&page_size=3&page_index=1&ann_type=A&client_source=web&stock_list={stock['code']}"
    )
    try:
        data = json.loads(http_get(url, headers={}))
    except Exception as exc:
        return f"公告数据：获取失败（{type(exc).__name__}: {exc}）。"

    items = data.get("data", {}).get("list") or []
    if not items:
        return "公告数据：暂无近期公告。"

    lines = []
    for item in items[:3]:
        date = item.get("notice_date") or item.get("display_time") or "未知日期"
        title = item.get("title_ch") or item.get("title") or "未命名公告"
        lines.append(f"{date[:10]} {title}")

    return "近期公告（东方财富）：\n" + "\n".join(lines)


def unique_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        result.append(item)
        seen.add(item)
    return result


def field_at(fields: list[str], index: int, default: str = "未返回") -> str:
    if index >= len(fields) or fields[index] in {"", " "}:
        return default
    return fields[index]


def format_market_timestamp(value: str) -> str:
    if not value or len(value) < 14:
        return value or "未知"
    return f"{value[0:4]}-{value[4:6]}-{value[6:8]} {value[8:10]}:{value[10:12]}:{value[12:14]}"


def to_float(value: str) -> float:
    try:
        return float(value)
    except TypeError, ValueError:
        return 0.0


def average(values) -> float:
    numbers = list(values)
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)


def period_pct_change(rows: list[dict[str, float | str]], days: int) -> float | None:
    if len(rows) <= days:
        return None
    base = rows[-days - 1]["close"]
    latest = rows[-1]["close"]
    if not isinstance(base, float) or not isinstance(latest, float) or base == 0:
        return None
    return (latest - base) / base * 100


def daily_pct_change(rows: list[dict[str, float | str]]) -> float | None:
    if len(rows) < 2:
        return None
    previous = rows[-2]["close"]
    latest = rows[-1]["close"]
    if not isinstance(previous, float) or not isinstance(latest, float) or previous == 0:
        return None
    return (latest - previous) / previous * 100


def turnover_from_volume(volume_lots: float, float_shares: float) -> float | None:
    if float_shares <= 0:
        return None
    return volume_lots * 100 / float_shares * 100


def compare_to_average(value: float, avg_value: float) -> float | None:
    if avg_value == 0:
        return None
    return (value - avg_value) / avg_value * 100


def intraday_change(rows: list[dict[str, float | str]]) -> float | None:
    if len(rows) < 2:
        return None
    first = rows[0]["price"]
    latest = rows[-1]["price"]
    if not isinstance(first, float) or not isinstance(latest, float) or first == 0:
        return None
    return (latest - first) / first * 100


def format_optional_float(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "样本不足"
    return f"{value:.2f}{suffix}"


@tool
def financial_context_tool(question: str) -> str:
    """Get A-share or US stock market data context for a user's stock analysis question."""
    try:
        return build_financial_context(question)
    except Exception as exc:
        return f"金融数据工具：获取失败（{type(exc).__name__}: {exc}）。请基于已知信息谨慎回答，并明确说明数据缺失。"


@tool
def stock_quote_tool(symbol: str) -> str:
    """Get a free delayed stock quote for a US ticker symbol."""
    try:
        return get_stock_quote(symbol)
    except Exception as exc:
        return f"行情工具：获取失败（{type(exc).__name__}: {exc}）。"


@tool
def sec_filings_tool(symbol: str) -> str:
    """Get recent SEC filings for a US ticker symbol."""
    try:
        return get_company_filings(symbol)
    except Exception as exc:
        return f"SEC 申报工具：获取失败（{type(exc).__name__}: {exc}）。"


@tool
def sec_company_facts_tool(symbol: str) -> str:
    """Get a compact SEC company facts summary for a US ticker symbol."""
    try:
        return get_company_facts_summary(symbol)
    except Exception as exc:
        return f"SEC 财务数据工具：获取失败（{type(exc).__name__}: {exc}）。"


def get_stock_quote(symbol: str) -> str:
    symbol = normalize_symbol(symbol)
    url = f"https://stooq.com/q/l/?s={quote(symbol.lower())}.us&f=sd2t2ohlcv&h&e=csv"

    try:
        text = http_get(url, headers={})
        rows = list(csv.DictReader(StringIO(text)))
    except Exception as exc:
        return f"行情数据：获取失败（{type(exc).__name__}: {exc}）。"

    if not rows:
        return "行情数据：未返回数据。"

    row = rows[0]
    close = row.get("Close", "N/D")
    if close == "N/D":
        return f"行情数据：未找到 {symbol} 的免费行情。"

    return (
        "行情数据（Stooq，可能延迟）："
        f"代码={symbol}，日期={row.get('Date')}，时间={row.get('Time')}，"
        f"开盘={row.get('Open')}，最高={row.get('High')}，最低={row.get('Low')}，"
        f"收盘/最新={close}，成交量={row.get('Volume')}。"
    )


def get_company_filings(symbol: str, limit: int = 5) -> str:
    symbol = normalize_symbol(symbol)
    cik = lookup_cik(symbol)
    if not cik:
        return f"SEC 申报：未找到 {symbol} 对应 CIK。"

    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        data = json.loads(http_get(url, sec_headers()))
    except Exception as exc:
        return f"SEC 申报：获取失败（{type(exc).__name__}: {exc}）。"

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])

    items = []
    for form, date, accession, doc in list(zip(forms, dates, accessions, docs, strict=False))[
        :limit
    ]:
        accession_path = accession.replace("-", "")
        filing_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_path}/{doc}"
        items.append(f"{date} {form}: {filing_url}")

    if not items:
        return "SEC 申报：暂无近期申报。"

    return "SEC 近期申报：\n" + "\n".join(items)


def get_company_facts_summary(symbol: str) -> str:
    symbol = normalize_symbol(symbol)
    cik = lookup_cik(symbol)
    if not cik:
        return f"SEC 公司事实：未找到 {symbol} 对应 CIK。"

    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    try:
        data = json.loads(http_get(url, sec_headers()))
    except Exception as exc:
        return f"SEC 公司事实：获取失败（{type(exc).__name__}: {exc}）。"

    facts = data.get("facts", {}).get("us-gaap", {})
    metrics = {
        "Revenue": "Revenues",
        "Net income": "NetIncomeLoss",
        "Assets": "Assets",
        "Liabilities": "Liabilities",
        "Operating cash flow": "NetCashProvidedByUsedInOperatingActivities",
    }

    lines = []
    for label, key in metrics.items():
        latest = latest_usd_fact(facts.get(key, {}))
        if latest:
            lines.append(f"{label}: {latest}")

    if not lines:
        return "SEC 公司事实：未提取到常用财务指标。"

    return "SEC 公司事实摘要（最新可用 XBRL 数据）：\n" + "\n".join(lines)


def latest_usd_fact(fact: dict[str, Any]) -> str | None:
    units = fact.get("units", {})
    values = units.get("USD") or units.get("shares") or []
    if not values:
        return None

    sorted_values = sorted(
        values,
        key=lambda item: (item.get("fy") or 0, item.get("filed") or ""),
        reverse=True,
    )
    value = sorted_values[0]
    amount = value.get("val")
    if amount is None:
        return None

    return (
        f"{amount:,}，期间={value.get('fp')} {value.get('fy')}，"
        f"截止={value.get('end')}，申报={value.get('filed')}"
    )


def lookup_cik(symbol: str) -> str | None:
    symbol = normalize_symbol(symbol)
    mapping = load_ticker_mapping()
    cik = mapping.get(symbol)
    if cik is None:
        return None
    return str(cik).zfill(10)


def load_ticker_mapping() -> dict[str, int]:
    now = time.time()
    if _ticker_cache["data"] and now - _ticker_cache["loaded_at"] < 86400:
        return _ticker_cache["data"]

    url = "https://www.sec.gov/files/company_tickers.json"
    data = json.loads(http_get(url, sec_headers()))
    mapping = {item["ticker"].upper(): int(item["cik_str"]) for item in data.values()}
    _ticker_cache["data"] = mapping
    _ticker_cache["loaded_at"] = now
    return mapping


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper().lstrip("$")


def sec_headers() -> dict[str, str]:
    return {
        "User-Agent": SEC_USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
    }


def http_get(url: str, headers: dict[str, str]) -> str:
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=HTTP_TIMEOUT) as response:
            body = response.read()
            if response.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            try:
                return body.decode("utf-8")
            except UnicodeDecodeError:
                return body.decode("gbk")
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc
