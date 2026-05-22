const loginForm = document.querySelector("#loginForm");
const registerForm = document.querySelector("#registerForm");
const loginBtn = document.querySelector("#loginBtn");
const registerBtn = document.querySelector("#registerBtn");
const usernameInput = document.querySelector("#username");
const passwordInput = document.querySelector("#password");
const registerUsernameInput = document.querySelector("#registerUsername");
const registerPasswordInput = document.querySelector("#registerPassword");
const registerPasswordConfirmInput = document.querySelector("#registerPasswordConfirm");

redirectIfAlreadyLoggedIn();

async function login(event) {
  event.preventDefault();
  loginBtn.disabled = true;

  try {
    const response = await fetch("/api/login", {
      method: "POST",
      credentials: "same-origin",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        username: usernameInput.value.trim(),
        password: passwordInput.value,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(data.detail, "登录失败"));
    }

    window.location.href = "/";
  } catch (error) {
    alert(error.message);
  } finally {
    loginBtn.disabled = false;
  }
}

async function register(event) {
  event.preventDefault();

  const username = registerUsernameInput.value.trim();
  const password = registerPasswordInput.value;
  if (password !== registerPasswordConfirmInput.value) {
    alert("两次输入的密码不一致");
    return;
  }

  registerBtn.disabled = true;

  try {
    const response = await fetch("/api/register", {
      method: "POST",
      credentials: "same-origin",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({username, password}),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(data.detail, "注册失败"));
    }

    window.location.href = `/login?registered=${encodeURIComponent(username)}`;
  } catch (error) {
    alert(error.message);
  } finally {
    registerBtn.disabled = false;
  }
}

function prefillRegisteredUser() {
  if (!usernameInput) return;

  const params = new URLSearchParams(window.location.search);
  const username = params.get("registered");
  if (username) {
    usernameInput.value = username;
    passwordInput.focus();
  }
}

async function redirectIfAlreadyLoggedIn() {
  try {
    const response = await fetch("/api/me", {credentials: "same-origin"});
    if (response.ok) {
      window.location.href = "/";
    }
  } catch (error) {
    // Stay on the login/register page when the session check fails.
  }
}

function formatApiError(detail, fallback) {
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const field = Array.isArray(item.loc) ? item.loc.slice(1).join(".") : "";
        return field ? `${field}: ${item.msg}` : item.msg;
      })
      .join("\n");
  }
  return detail || fallback;
}

if (loginForm) {
  loginForm.addEventListener("submit", login);
  prefillRegisteredUser();
}

if (registerForm) {
  registerForm.addEventListener("submit", register);
}
