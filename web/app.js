import { responseHtml, signalsHtml, sourceSummaryHtml } from "./render.js?v=20260910-1";

const statusEl = document.getElementById("status");
const researchEl = document.getElementById("research");
const draftsEl = document.getElementById("drafts");
const signalsEl = document.getElementById("signals");
const authGateEl = document.getElementById("authGate");
const appShellEl = document.getElementById("appShell");
const authStatusEl = document.getElementById("authStatus");
const authUserEl = document.getElementById("authUser");
const googleButtonEl = document.getElementById("googleButton");
const logoutButtonEl = document.getElementById("logoutButton");
const dismissLoginButtonEl = document.getElementById("dismissLoginButton");
const creationModeEl = document.getElementById("creationMode");
const modeGuideEl = document.getElementById("modeGuide");
const actionFeedbackEl = document.getElementById("actionFeedback");
const actionFeedbackTextEl = document.getElementById("actionFeedbackText");
const sessionStorageKey = "writing-agent-session";
const workflowStorageKey = "writing-agent-workflow";
let authCsrfToken = "";
let authConfig = null;
let currentUser = null;
let sessionToken = "";
let latestSignals = [];
let sourceSummaryToken = null;
let sourceSummaryMaterials = "";
let actionStartedAt = null;
let actionTimer = null;
let actionBaseMessage = "";
let workflowId = "";

try {
  sessionToken = window.sessionStorage.getItem(sessionStorageKey) || "";
} catch (_error) {
  sessionToken = "";
}

try {
  workflowId = window.sessionStorage.getItem(workflowStorageKey) || "";
  if (!workflowId) {
    workflowId = globalThis.crypto?.randomUUID?.().replaceAll("-", "")
      || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    window.sessionStorage.setItem(workflowStorageKey, workflowId);
  }
} catch (_error) {
  workflowId = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

const modeSettings = {
  "external-signal": {
    guide: "适合新消息、帖子、文章或热点。先用线索发现问题，再用原始来源确认事实。",
    contentType: "rapid-analysis",
    materialsLabel: "线索 / 外部来源",
    materialsPlaceholder: "每行一条链接或正文。社交帖子用于发现线索，官方文档、论文和源码用于确认事实。",
  },
  "original-idea": {
    guide: "适合 Harness 工程等你主动提出的问题。先写问题、初步观点和自己的笔记，再补充必要的外部事实。",
    contentType: "opinion",
    materialsLabel: "参考资料（可选）",
    materialsPlaceholder: "每行一条参考链接或正文。纯观点可以暂不填写；涉及产品能力、数据或版本时需要补充来源。",
  },
  "artifact-analysis": {
    guide: "适合 Codex 源码解析、产品实测和工程复盘。请记录具体对象、版本，以及真实阅读或验证过程。",
    contentType: "open-source-analysis",
    materialsLabel: "仓库 / 文档 / 外部来源",
    materialsPlaceholder: "每行一条。源码解析请至少填写仓库链接；产品分析可填写官方文档和相关资料。",
  },
};

function sourceInputFingerprint() {
  return JSON.stringify(materialsPayload());
}

function invalidateSourceSummary(message = "") {
  if (!sourceSummaryToken) return;
  sourceSummaryToken = null;
  sourceSummaryMaterials = "";
  if (message) setStatus(message);
}

function updateCreationMode({ setDefaultType = false } = {}) {
  const mode = creationModeEl.value;
  const settings = modeSettings[mode];
  modeGuideEl.textContent = settings.guide;
  document.querySelectorAll("[data-modes]").forEach((group) => {
    group.hidden = !group.dataset.modes.split(",").includes(mode);
  });
  document.getElementById("materialsLabel").textContent = settings.materialsLabel;
  document.getElementById("materials").placeholder = settings.materialsPlaceholder;
  document.getElementById("materialsHelp").textContent = mode === "original-idea"
    ? "作者观点不需要伪装成外部事实；出现可核验的事实主张时，再补充对应来源。"
    : "需要手动确认等级时，可使用 A!|URL；普通链接会由系统初步判断。";
  if (setDefaultType) {
    document.getElementById("contentType").value = settings.contentType;
  }
}

function renderActionFeedback() {
  if (!actionBaseMessage) {
    actionFeedbackEl.hidden = true;
    return;
  }
  const elapsed = actionStartedAt && actionFeedbackEl.dataset.state === "loading"
    ? ` · 已等待 ${Math.floor((Date.now() - actionStartedAt) / 1000)} 秒`
    : "";
  actionFeedbackTextEl.textContent = `${actionBaseMessage}${elapsed}`;
  actionFeedbackEl.hidden = false;
}

function setStatus(message = "", state = "info") {
  statusEl.textContent = message;
  statusEl.hidden = !message;
  actionBaseMessage = message;
  actionFeedbackEl.dataset.state = state;
  renderActionFeedback();
}

function setActionButtonsDisabled(disabled) {
  document.querySelectorAll(
    "#suggestButton, #summarizeButton, #generateButton, #reviseButton, " +
    "#signalsButton, .signal-create-button"
  ).forEach((button) => {
    button.disabled = disabled;
  });
}

function saveSessionToken(value = "") {
  sessionToken = value;
  try {
    if (value) {
      window.sessionStorage.setItem(sessionStorageKey, value);
    } else {
      window.sessionStorage.removeItem(sessionStorageKey);
    }
  } catch (_error) {
    // 某些内置浏览器会禁用会话存储，当前页面仍可使用内存中的令牌。
  }
}

function authFetch(input, init = {}) {
  const headers = new Headers(init.headers || {});
  if (sessionToken) headers.set("Authorization", `Bearer ${sessionToken}`);
  return fetch(input, {
    ...init,
    headers,
    credentials: "include",
  });
}

async function runButtonAction(button, busyLabel, action) {
  if (actionStartedAt) return;
  const originalLabel = button.textContent;
  actionStartedAt = Date.now();
  setActionButtonsDisabled(true);
  button.innerHTML = `<span class="button-spinner" aria-hidden="true"></span>${busyLabel}`;
  button.setAttribute("aria-busy", "true");
  setStatus(busyLabel, "loading");
  actionTimer = window.setInterval(renderActionFeedback, 1000);
  try {
    await action();
  } catch (error) {
    showRequestError(error);
  } finally {
    window.clearInterval(actionTimer);
    actionTimer = null;
    actionStartedAt = null;
    button.textContent = originalLabel;
    button.removeAttribute("aria-busy");
    setActionButtonsDisabled(false);
    if (actionFeedbackEl.dataset.state === "loading") setStatus();
  }
}

function loadGoogleIdentity() {
  return new Promise((resolve, reject) => {
    if (window.google?.accounts?.id) return resolve();
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = resolve;
    script.onerror = () => reject(new Error("Google 登录组件加载失败"));
    document.head.appendChild(script);
  });
}

function showWorkspace(user) {
  currentUser = user || null;
  authGateEl.hidden = true;
  appShellEl.hidden = false;
  authUserEl.textContent = user?.email || "未登录";
  logoutButtonEl.textContent = user ? "退出登录" : "登录";
}

function showLogin(message) {
  authGateEl.hidden = false;
  authStatusEl.textContent = message;
}

async function refreshAuthConfig() {
  const configResponse = await fetch("/api/auth/config", {
    credentials: "include",
    cache: "no-store",
  });
  if (!configResponse.ok) throw new Error("无法读取登录配置");
  authConfig = await configResponse.json();
  authCsrfToken = authConfig.csrf_token || "";
  return authConfig;
}

async function prepareGoogleLogin(config) {
  await loadGoogleIdentity();
  window.google.accounts.id.initialize({
    client_id: config.google_client_id,
    use_fedcm_for_button: true,
    callback: async ({ credential }) => {
      try {
        const response = await fetch("/api/auth/google", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          cache: "no-store",
          body: JSON.stringify({ credential, csrf_token: authCsrfToken }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "登录失败");
        saveSessionToken(data.session_token || "");
        const meResponse = await authFetch("/api/auth/me", { cache: "no-store" });
        const me = await meResponse.json();
        if (!meResponse.ok || !me.authenticated) {
          saveSessionToken();
          throw new Error("登录会话未能建立，请重试");
        }
        showWorkspace(me.user);
        setStatus();
      } catch (error) {
        showLogin(`登录失败：${error.message}`);
      }
    },
  });
  googleButtonEl.innerHTML = "";
  window.google.accounts.id.renderButton(googleButtonEl, {
    theme: "filled_black",
    size: "large",
    shape: "pill",
    text: "signin_with",
  });
}

async function openLogin(message = "请使用已加入白名单的 Google 账号登录。") {
  showLogin("正在准备 Google 登录……");
  try {
    const config = await refreshAuthConfig();
    if (!config.required) {
      showWorkspace(null);
      return true;
    }
    if (!config.configured || !config.google_client_id) {
      googleButtonEl.innerHTML = "";
      showLogin("Google 登录尚未完成配置，请先设置 GOOGLE_CLIENT_ID。");
      return false;
    }
    showLogin(message);
    await prepareGoogleLogin(config);
    return false;
  } catch (error) {
    googleButtonEl.innerHTML = "";
    showLogin(`登录暂时不可用：${error.message}`);
    return false;
  }
}

async function requireAuthentication(actionName) {
  if (currentUser || authConfig?.required === false) return true;
  await openLogin(`登录后才能${actionName}。`);
  return authConfig?.required === false;
}

async function handleAuthFailure(response) {
  if (response.status !== 401 && response.status !== 403) return false;
  saveSessionToken();
  showWorkspace(null);
  setStatus("需要登录后继续");
  await openLogin("登录已失效或账号不在白名单，请重新登录。");
  return true;
}

async function initializeAuth() {
  showWorkspace(null);
  try {
    const [meResponse] = await Promise.all([
      authFetch("/api/auth/me", { cache: "no-store" }),
      refreshAuthConfig(),
    ]);
    if (!meResponse.ok) throw new Error("无法检查登录状态");
    const me = await meResponse.json();
    if (me.authenticated) {
      showWorkspace(me.user);
      setStatus();
    } else {
      saveSessionToken();
    }
  } catch (error) {
    authUserEl.textContent = "登录状态检查失败";
    console.warn("Auth initialization failed", error);
  }
}

function materialFromLine(line) {
  let content = line;
  let sourceTier = null;
  let forcedKind = null;
  let verifiedByUser = false;
  const tierMatch = content.match(/^([ABC])(!?)\|(.*)$/i);
  if (tierMatch) {
    sourceTier = tierMatch[1].toUpperCase();
    verifiedByUser = tierMatch[2] === "!";
    content = tierMatch[3].trim();
  }
  const kindMatch = content.match(/^(test|tool)\|(.*)$/i);
  if (kindMatch) {
    forcedKind = kindMatch[1].toLowerCase() === "test" ? "test_record" : "tool_record";
    content = kindMatch[2].trim();
  }
  const value = content.toLowerCase();
  let kind = forcedKind || "text";
  if (!forcedKind && (value.startsWith("http://") || value.startsWith("https://"))) {
    kind = (
    value.includes("youtube.com") ||
    value.includes("youtu.be") ||
    value.includes("bilibili.com") ||
    value.includes("douyin.com") ||
    value.includes("vimeo.com")
    ) ? "video" : "article";
  }
  return {
    kind,
    content,
    source: kind === "article" || kind === "video" ? content : null,
    source_tier: sourceTier,
    verified_by_user: verifiedByUser,
  };
}

function materialsPayload() {
  const materialLines = document.getElementById("materials").value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const materials = materialLines.map(materialFromLine);
  const mode = creationModeEl.value;
  const authorNotes = document.getElementById("authorNotes").value.trim();
  const artifactNotes = document.getElementById("artifactNotes").value.trim();
  if (mode === "original-idea" && authorNotes) {
    materials.push({
      kind: "author_note",
      content: authorNotes,
      source: null,
      source_tier: null,
      verified_by_user: true,
    });
  }
  if (mode === "artifact-analysis" && artifactNotes) {
    const contentType = document.getElementById("contentType").value;
    const kind = contentType === "product-review"
      ? "practice_record"
      : contentType === "tool-release"
        ? "tool_record"
        : contentType === "open-source-analysis"
          ? "code_record"
          : "author_note";
    materials.push({
      kind,
      content: artifactNotes,
      source: null,
      source_tier: null,
      verified_by_user: true,
    });
  }
  return materials;
}

function requestPayload() {
  const topicEl = document.getElementById("topic");
  const topic = topicEl.value.trim();
  if (!topic) {
    topicEl.focus();
    throw new Error("请先填写主题");
  }

  const platformMode = document.getElementById("platformMode").value;
  const platforms = platformMode === "both" ? ["wechat", "xiaohongshu"] : [platformMode];

  const audience = document.getElementById("audience").value.trim();
  const tone = document.getElementById("tone").value.trim();
  const goal = document.getElementById("goal").value.trim();
  return {
    workflow_id: workflowId,
    topic,
    creation_mode: creationModeEl.value,
    core_question: document.getElementById("coreQuestion").value.trim() || null,
    initial_thesis: document.getElementById("initialThesis").value.trim() || null,
    analysis_target: document.getElementById("analysisTarget").value.trim() || null,
    ...(audience ? { audience } : {}),
    ...(tone ? { tone } : {}),
    ...(goal ? { goal } : {}),
    content_type: document.getElementById("contentType").value,
    platforms,
    source_version: document.getElementById("sourceVersion").value.trim() || null,
    materials: materialsPayload(),
    source_summary_token: (
      sourceSummaryMaterials === sourceInputFingerprint()
        ? sourceSummaryToken
        : null
    ),
  };
}

function readableApiError(text) {
  try {
    const payload = JSON.parse(text);
    if (typeof payload.detail === "string") return payload.detail;
    if (Array.isArray(payload.detail)) {
      const labels = {
        topic: "主题",
        audience: "受众",
        tone: "语气",
        goal: "目标",
        materials: "素材 / 信息源",
        core_question: "核心问题",
        initial_thesis: "初步观点",
        analysis_target: "分析对象",
        feedback: "修订反馈",
      };
      return payload.detail.map((item) => {
        const field = labels[item.loc?.at(-1)] || item.loc?.at(-1) || "输入内容";
        if (item.type === "string_too_short") return `请填写${field}`;
        if (item.type === "string_too_long") return `${field}内容过长`;
        return `${field}格式不正确`;
      }).join("；");
    }
  } catch (_error) {
    // 非 JSON 响应直接使用原始提示。
  }
  return text || "请求失败";
}

function showRequestError(error) {
  const message = error?.message || String(error);
  setStatus(message.startsWith("请") ? message : `失败：${message}`, "error");
}

function renderResponse(data) {
  const rendered = responseHtml(data);
  researchEl.innerHTML = rendered.research;
  draftsEl.innerHTML = rendered.drafts;
}

function renderSourceSummaryOnly(data) {
  researchEl.innerHTML = sourceSummaryHtml(data);
  draftsEl.innerHTML = "";
}

async function loadSignals() {
  setStatus("正在读取最近采集线索...", "loading");
  const response = await authFetch("/api/signals?limit=30");
  if (!response.ok) {
    if (await handleAuthFailure(response)) throw new Error("请登录后重试");
    throw new Error(readableApiError(await response.text()));
  }
  const items = await response.json();
  latestSignals = items;
  signalsEl.innerHTML = signalsHtml(items);
  setStatus(`已读取 ${items.length} 条线索`, "success");
}

async function callApi(path, payload) {
  setStatus("正在研究材料、生成大纲和图文草稿...", "loading");
  draftsEl.innerHTML = "";
  researchEl.innerHTML = "";
  const response = await authFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    if (await handleAuthFailure(response)) throw new Error("请登录后重试");
    const text = await response.text();
    throw new Error(readableApiError(text));
  }
  const data = await response.json();
  renderResponse(data);
  setStatus("生成完成，结果已显示在右侧", "success");
}

async function suggestFromMaterials() {
  const materials = materialsPayload();
  const coreQuestion = document.getElementById("coreQuestion").value.trim();
  const initialThesis = document.getElementById("initialThesis").value.trim();
  const analysisTarget = document.getElementById("analysisTarget").value.trim();
  if (!materials.length && !coreQuestion && !initialThesis && !analysisTarget) {
    throw new Error("请先填写线索、作者笔记或分析对象");
  }
  if (!(await requireAuthentication("智能整理写作简报"))) return false;
  setStatus("正在分析输入并整理写作简报...", "loading");
  const response = await authFetch("/api/suggest_form", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workflow_id: workflowId,
      creation_mode: creationModeEl.value,
      core_question: coreQuestion || null,
      initial_thesis: initialThesis || null,
      analysis_target: analysisTarget || null,
      materials,
    }),
  });
  if (!response.ok) {
    if (await handleAuthFailure(response)) throw new Error("请登录后重试");
    throw new Error(readableApiError(await response.text()));
  }
  const data = await response.json();
  document.getElementById("topic").value = data.topic;
  document.getElementById("audience").value = data.audience;
  document.getElementById("tone").value = data.tone;
  document.getElementById("goal").value = data.goal;
  document.getElementById("contentType").value = data.content_type;
  document.getElementById("sourceVersion").value = data.source_version || "";
  if (data.core_question) document.getElementById("coreQuestion").value = data.core_question;
  if (data.initial_thesis) document.getElementById("initialThesis").value = data.initial_thesis;
  if (data.analysis_target) document.getElementById("analysisTarget").value = data.analysis_target;
  sourceSummaryToken = data.source_summary_token || null;
  sourceSummaryMaterials = sourceSummaryToken ? sourceInputFingerprint() : "";
  setStatus("写作简报已整理，可继续修改", "success");
  return true;
}

const suggestButtonEl = document.getElementById("suggestButton");
suggestButtonEl.addEventListener("click", () => {
  runButtonAction(suggestButtonEl, "正在整理...", async () => {
    await suggestFromMaterials();
  });
});

signalsEl.addEventListener("click", (event) => {
  const button = event.target.closest(".signal-create-button");
  if (!button) return;
  runButtonAction(button, "正在准备...", async () => {
    const signal = latestSignals[Number(button.dataset.signalIndex)];
    if (!signal) throw new Error("线索不存在，请重新加载");
    const content = String(signal.content || "").replace(/\s+/g, " ").trim();
    document.getElementById("materials").value = [
      `C|${signal.url}`,
      content ? `C|${content}` : "",
    ].filter(Boolean).join("\n");
    creationModeEl.value = "external-signal";
    updateCreationMode({ setDefaultType: true });
    sourceSummaryToken = null;
    sourceSummaryMaterials = "";
    if (await suggestFromMaterials()) {
      document.getElementById("topic").scrollIntoView({ behavior: "smooth", block: "center" });
    }
  });
});

const generateButtonEl = document.getElementById("generateButton");
generateButtonEl.addEventListener("click", () => {
  runButtonAction(generateButtonEl, "正在生成...", async () => {
    const payload = requestPayload();
    if (payload.materials.length && !payload.source_summary_token) {
      document.getElementById("summarizeButton").focus();
      throw new Error("素材尚未分析，请先点击“分析素材与来源”");
    }
    if (!(await requireAuthentication("生成图文草稿"))) return;
    await callApi("/api/generate", payload);
  });
});

const summarizeButtonEl = document.getElementById("summarizeButton");
summarizeButtonEl.addEventListener("click", () => {
  runButtonAction(summarizeButtonEl, "正在分析...", async () => {
    const payload = requestPayload();
    if (!payload.materials.length) {
      throw new Error("请先填写需要分析的素材、笔记或记录");
    }
    if (!(await requireAuthentication("分析素材与来源"))) return;
    setStatus("正在抓取并分析素材与来源...", "loading");
    draftsEl.innerHTML = "";
    researchEl.innerHTML = "";
    const response = await authFetch("/api/summarize_sources", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      if (await handleAuthFailure(response)) throw new Error("请登录后重试");
      const text = await response.text();
      throw new Error(readableApiError(text));
    }
    const data = await response.json();
    sourceSummaryToken = data.source_summary_token || null;
    sourceSummaryMaterials = sourceInputFingerprint();
    renderSourceSummaryOnly(data);
    const failedCount = (data.source_items || []).filter(
      (item) => item.url && !item.fetched
    ).length;
    setStatus(
      failedCount
        ? `来源检查完成 · ${failedCount} 条链接抓取失败`
        : "来源检查完成 · 结果已保存",
      failedCount ? "error" : "success"
    );
  });
});

const reviseButtonEl = document.getElementById("reviseButton");
reviseButtonEl.addEventListener("click", () => {
  runButtonAction(reviseButtonEl, "正在重新生成...", async () => {
    const payload = requestPayload();
    if (payload.materials.length && !payload.source_summary_token) {
      document.getElementById("summarizeButton").focus();
      throw new Error("素材尚未分析，请先点击“分析素材与来源”");
    }
    if (!(await requireAuthentication("根据反馈重新生成"))) return;
    await callApi("/api/revise", {
      request: payload,
      feedback: document.getElementById("feedback").value.trim(),
    });
  });
});

const signalsButtonEl = document.getElementById("signalsButton");
signalsButtonEl.addEventListener("click", () => {
  runButtonAction(signalsButtonEl, "正在读取...", async () => {
    if (!(await requireAuthentication("查看私有采集线索"))) return;
    await loadSignals();
  });
});

["materials", "authorNotes", "artifactNotes"].forEach((id) => {
  document.getElementById(id).addEventListener("input", () => {
    invalidateSourceSummary("素材已修改，请重新分析素材与来源");
  });
});

creationModeEl.addEventListener("change", () => {
  invalidateSourceSummary("创作方式已切换，请重新整理写作简报");
  updateCreationMode({ setDefaultType: true });
});

dismissLoginButtonEl.addEventListener("click", () => {
  authGateEl.hidden = true;
});

logoutButtonEl.addEventListener("click", async () => {
  if (!currentUser) {
    await openLogin();
    return;
  }
  try {
    await authFetch("/api/auth/logout", { method: "POST" });
  } finally {
    saveSessionToken();
  }
  window.google?.accounts?.id?.disableAutoSelect();
  googleButtonEl.innerHTML = "";
  showWorkspace(null);
  setStatus();
});

updateCreationMode();
initializeAuth();
