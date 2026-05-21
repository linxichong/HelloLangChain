let providers = [
  ["gemini", "Gemini"],
  ["openai", "OpenAI"],
  ["deepseek", "DeepSeek"],
];
let configuredProviders = ["gemini"];

const providerIconLabels = {
  gemini: "Gemini",
  openai: "OpenAI",
  deepseek: "DeepSeek",
};

const modelRoot = document.querySelector("#models");
const sendBtn = document.querySelector("#sendBtn");
const clearBtn = document.querySelector("#clearBtn");
const questionInput = document.querySelector("#question");
const targetModels = document.querySelector("#targetModels");
const logoutBtn = document.querySelector("#logoutBtn");
const userInfo = document.querySelector("#userInfo");
const currentUser = document.querySelector("#currentUser");

let authToken = localStorage.getItem("authToken") || "";
let activeUser = null;

function authHeaders(extraHeaders = {}) {
  if (!authToken) return extraHeaders;
  return {
    ...extraHeaders,
    Authorization: `Bearer ${authToken}`,
  };
}

function updateAuthUi() {
  const loggedIn = Boolean(activeUser && authToken);
  currentUser.textContent = loggedIn ? `${activeUser.username} · ${activeUser.role}` : "";
  sendBtn.disabled = !loggedIn;
  clearBtn.disabled = !loggedIn;
  userInfo.hidden = !loggedIn;
}

async function loadCurrentUser() {
  if (!authToken) {
    window.location.href = "/login";
    return;
  }

  try {
    const response = await fetch("/api/me", {headers: authHeaders()});
    if (!response.ok) throw new Error("session expired");
    activeUser = await response.json();
  } catch (error) {
    authToken = "";
    activeUser = null;
    localStorage.removeItem("authToken");
    window.location.href = "/login";
    return;
  }
  updateAuthUi();
}

async function logout() {
  if (authToken) {
    await fetch("/api/logout", {
      method: "POST",
      headers: authHeaders(),
    }).catch(() => {});
  }
  authToken = "";
  activeUser = null;
  localStorage.removeItem("authToken");
  window.location.href = "/login";
}

async function loadModels() {
  try {
    const response = await fetch("/api/models");
    const models = await response.json();
    providers = models.map((model) => [model.provider, model.label]);
    renderModelOptions(models);
    createPanels(models);
  } catch (error) {
    createPanels(providers.map(([provider, label]) => ({provider, label, configured: true})));
  }
}

function renderModelOptions(models) {
  targetModels.innerHTML = "";
  const configuredModels = models.filter((model) => model.configured);
  configuredProviders = configuredModels.map((model) => model.provider);

  if (configuredModels.length > 1) {
    targetModels.appendChild(new Option("全部已配置模型", "all"));
  }

  for (const model of models) {
    const suffix = model.configured ? "" : "（未配置）";
    const option = new Option(`仅 ${model.label}${suffix}`, model.provider);
    option.disabled = !model.configured;
    targetModels.appendChild(option);
  }

  targetModels.value = configuredModels[0]?.provider || "gemini";
}

function createPanels(models) {
  modelRoot.innerHTML = "";

  for (const model of models) {
    const provider = Array.isArray(model) ? model[0] : model.provider;
    const label = Array.isArray(model) ? model[1] : model.label;
    const configured = Array.isArray(model) ? true : model.configured;
    const panel = document.createElement("article");
    panel.className = "model-panel";
    panel.dataset.provider = provider;
    panel.innerHTML = `
      <div class="model-head">
        <div class="model-title">
          <span class="provider-icon provider-${provider}" aria-label="${providerIconLabels[provider] || label}" role="img"></span>
          <span>${label}</span>
        </div>
        <div class="status" id="status-${provider}">${configured ? "就绪" : "未配置"}</div>
      </div>
      <div class="messages" id="messages-${provider}"></div>
    `;
    modelRoot.appendChild(panel);
  }
}

function appendMessage(provider, role, text, kind = "") {
  const root = document.querySelector(`#messages-${provider}`);
  const msg = document.createElement("div");
  msg.className = `msg ${role === "assistant" ? "assistant" : "user"} ${kind}`;
  msg.innerHTML = `
    <div class="role">${role === "user" ? "你" : "助手"}</div>
    <div class="bubble"></div>
  `;
  msg.querySelector(".bubble").textContent = text;
  root.appendChild(msg);
  root.scrollTop = root.scrollHeight;
  return msg;
}

function updateMessage(provider, msg, text, kind = "") {
  msg.className = `msg assistant ${kind}`;
  msg.querySelector(".bubble").textContent = text;
  const root = document.querySelector(`#messages-${provider}`);
  root.scrollTop = root.scrollHeight;
}

function setStatus(provider, text) {
  document.querySelector(`#status-${provider}`).textContent = text;
}

function selectedProviders() {
  const value = targetModels.value;
  if (value === "all") {
    return configuredProviders;
  }
  return [value];
}

function buildPayload(provider, question) {
  return {
    provider,
    analysis_mode: document.querySelector("#analysisMode").value,
    role: document.querySelector("#role").value,
    language: document.querySelector("#language").value,
    style: document.querySelector("#style").value,
    question,
    use_memory: document.querySelector("#useMemory").value === "true",
  };
}

async function sendQuestion() {
  const question = questionInput.value.trim();
  if (!question) return;
  if (!authToken) {
    alert("请先登录");
    return;
  }

  const targets = selectedProviders();
  questionInput.value = "";
  sendBtn.disabled = true;

  for (const provider of targets) {
    appendMessage(provider, "user", question);
    setStatus(provider, "思考中");
  }

  await Promise.all(targets.map((provider) => requestModel(provider, question)));

  sendBtn.disabled = false;
  questionInput.focus();
}

async function requestModel(provider, question) {
  if (window.ReadableStream) {
    await requestModelStream(provider, question);
    return;
  }

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: authHeaders({"Content-Type": "application/json"}),
      body: JSON.stringify(buildPayload(provider, question)),
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(formatApiError(data.detail, response.status));
    }

    const modeLabel = data.analysis_mode === "agent" ? "Agent" : "普通";
    const answer = `${data.answer}\n\n模式：${modeLabel}｜可信度：${Number(data.confidence).toFixed(2)}`;
    appendMessage(provider, "assistant", answer);
    setStatus(provider, "完成");
  } catch (error) {
    appendMessage(provider, "assistant", error.message, "error");
    setStatus(provider, "失败");
  }
}

async function requestModelStream(provider, question) {
  const assistantMsg = appendMessage(provider, "assistant", "");
  let answer = "";
  let confidence = null;
  let analysisMode = document.querySelector("#analysisMode").value;

  try {
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: authHeaders({"Content-Type": "application/json"}),
      body: JSON.stringify(buildPayload(provider, question)),
    });

    if (!response.ok || !response.body) {
      const data = await response.json().catch(() => ({}));
      throw new Error(formatApiError(data.detail, response.status));
    }

    setStatus(provider, "接收中");
    for await (const event of readNdjson(response.body)) {
      if (event.event === "delta") {
        answer += event.text || "";
        updateMessage(provider, assistantMsg, answer || " ");
      } else if (event.event === "done") {
        confidence = event.confidence;
        analysisMode = event.analysis_mode || analysisMode;
      } else if (event.event === "error") {
        throw new Error(formatApiError(event.detail, response.status));
      }
    }

    const modeLabel = analysisMode === "agent" ? "Agent" : "普通";
    const score = Number(confidence ?? 0).toFixed(2);
    updateMessage(provider, assistantMsg, `${answer}\n\n模式：${modeLabel}｜可信度：${score}`);
    setStatus(provider, "完成");
  } catch (error) {
    updateMessage(provider, assistantMsg, error.message, "error");
    setStatus(provider, "失败");
  }
}

async function* readNdjson(stream) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const {done, value} = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, {stream: true});
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.trim()) {
        yield JSON.parse(line);
      }
    }
  }

  buffer += decoder.decode();
  if (buffer.trim()) {
    yield JSON.parse(buffer);
  }
}

function formatApiError(detail, status) {
  if (detail && typeof detail === "object") {
    const provider = detail.provider ? `${detail.provider}: ` : "";
    return `${provider}${detail.message || detail.code || `HTTP ${status}`}`;
  }
  return detail || `HTTP ${status}`;
}

async function clearMemory() {
  if (!authToken) {
    alert("请先登录");
    return;
  }

  await fetch("/api/reset", {
    method: "POST",
    headers: authHeaders(),
  });

  for (const [provider] of providers) {
    document.querySelector(`#messages-${provider}`).innerHTML = "";
    setStatus(provider, "已清空");
  }
}

logoutBtn.addEventListener("click", logout);
sendBtn.addEventListener("click", sendQuestion);
clearBtn.addEventListener("click", clearMemory);
questionInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendQuestion();
  }
});

loadModels();
loadCurrentUser();
