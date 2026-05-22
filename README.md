# HelloLangChain

一个 FastAPI + LangChain 的多模型聊天示例，默认使用 Gemini。

## 启动 Web 版

```bash
uv run uvicorn app.web.main:app --host 0.0.0.0 --port 8000
```

兼容旧命令：

```bash
uv run python chat_web_app.py
```

打开：

```text
http://127.0.0.1:8000
```

如果端口被占用，可以换端口：

```bash
uv run uvicorn app.web.main:app --host 0.0.0.0 --port 8010
```

## 代码结构

```text
app/
  web/       FastAPI 页面和 API 路由
  db/        PostgreSQL 用户、登录会话、记忆存储
  llm/       Gemini、OpenAI、DeepSeek 客户端
  chains/    普通 LangChain 链
  agents/    LangChain Agent 模式
  tools/     A 股/美股金融数据工具
  config/    .env 加载
```

## Docker Compose 部署

先准备 `.env`：

```bash
cp .env.example .env
```

至少修改这些值：

```dotenv
GEMINI_API_KEY=你的 Gemini key
ADMIN_USERNAME=admin
ADMIN_PASSWORD=换成强密码
```

然后启动 Web 和 PostgreSQL：

```bash
docker compose up --build
```

打开：

```text
http://127.0.0.1:8000
```

Compose 会启动两个服务：

- `db`：PostgreSQL，数据保存在 Docker volume `postgres_data`
- `web`：FastAPI 应用，容器内会根据 `POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB` 自动拼接 `DATABASE_URL`

数据库信息都可以在 `.env` 中配置：

```dotenv
POSTGRES_DB=hellolangchain
POSTGRES_USER=admin
POSTGRES_PASSWORD=admin123
POSTGRES_HOST_PORT=5433
```

数据库默认映射到宿主机 `5433`，避免和本机已有 PostgreSQL 的 `5432` 冲突。

停止服务：

```bash
docker compose down
```

如果要连数据库调试：

```bash
docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

## 模型配置

可以把本地配置写在 `.env` 里。先复制示例文件：

```bash
cp .env.example .env
```

然后编辑 `.env`：

```dotenv
OPENAI_API_KEY=你的 OpenAI key
OPENAI_MODEL=gpt-4.1-mini
DEEPSEEK_API_KEY=你的 DeepSeek key
DEEPSEEK_MODEL=deepseek-v4-flash
GEMINI_API_KEY=你的 Gemini key
GEMINI_MODEL=gemini-3-flash-preview

LLM_PROVIDER=gemini
CHAT_HOST=127.0.0.1
CHAT_PORT=8000

POSTGRES_DB=hellolangchain
POSTGRES_USER=admin
POSTGRES_PASSWORD=admin123
POSTGRES_HOST_PORT=5433

DATABASE_URL=postgresql://admin:admin123@127.0.0.1:5433/hellolangchain
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-me
ENABLE_PUBLIC_REGISTRATION=true
NORMAL_USER_MEMORY_TURN_LIMIT=5
SESSION_EXPIRE_HOURS=168
SESSION_COOKIE_SECURE=false
```

程序启动时会自动加载 `.env`。系统环境变量优先级更高，如果同名变量已经在 shell 里设置，`.env` 不会覆盖它。

各模型名称都可以在 `.env` 中配置：

```dotenv
OPENAI_MODEL=gpt-4.1-mini
DEEPSEEK_MODEL=deepseek-v4-flash
GEMINI_MODEL=gemini-3-flash-preview
```

页面会自动禁用未配置 key 的云模型，默认只请求已配置的模型。

## 分析模式

页面提供两种模式：

- 普通：代码先拉取完整金融上下文，再进行一次模型调用，速度更快、token 更省，适合单股分析
- Agent：使用 LangChain `create_agent` 和工具调用，让模型自行调用金融数据工具，适合复杂问题、多步骤分析和多股对比

Agent 模式依赖模型的工具调用能力，建议优先搭配 Gemini、OpenAI、DeepSeek 等工具调用能力更强的模型使用。

## 用户和记忆

项目使用 PostgreSQL 存储用户、登录会话和对话记忆。

先创建数据库，例如：

```bash
createdb hellolangchain
```

- 首次启动时，如果配置了 `ADMIN_USERNAME` 和 `ADMIN_PASSWORD`，会自动创建超级用户
- 未登录时会显示登录/注册画面，注册用户默认为普通用户
- 可以通过 `ENABLE_PUBLIC_REGISTRATION=false` 关闭公开注册
- 登录后会得到 bearer token，聊天和清空记忆都需要登录
- Web 页面会优先使用 HttpOnly 会话 cookie；如果部署在 HTTPS 后面，建议设置 `SESSION_COOKIE_SECURE=true`
- 不同用户的历史记忆互相隔离
- 普通用户默认只保留最近 5 轮问答，可通过 `NORMAL_USER_MEMORY_TURN_LIMIT` 调整
- 超级用户不裁剪历史记忆
- 只有超级用户可以通过 `POST /api/users` 创建普通用户或超级用户

创建普通用户示例：

```bash
curl -X POST http://127.0.0.1:8000/api/users \
  -H "Authorization: Bearer <超级用户 token>" \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"alice-password","role":"normal"}'
```

股票问题会自动补充行情上下文：

- A 股：支持中文股票名和 6 位股票代码，例如 `淳中科技`、`603516`
- A 股分析上下文包含：实时/延迟快照、日 K 线、分时走势、近 5/20 个交易日涨跌、成交量变化、换手率变化、涨跌停价格、行业/板块、市值、市盈率和近期公告
- 美股：支持 ticker，例如 `AAPL`、`TSLA`

## 命令行版

```bash
uv run python -m app.cli
```

兼容旧命令：

```bash
uv run python main.py
```
