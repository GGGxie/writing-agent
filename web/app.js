import { responseHtml, signalsHtml, sourceSummaryHtml } from "./render.js?v=20260918-1";

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
const viewTabResultsEl = document.getElementById("viewTabResults");
const viewTabSignalsEl = document.getElementById("viewTabSignals");
const sessionStorageKey = "writing-agent-session";
const workflowStorageKey = "writing-agent-workflow";
const activeJobStorageKey = "writing-agent-active-job";
const jobPollIntervalMs = 1500;
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

function setActiveView(view) {
  document.querySelectorAll("[data-view-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.viewPanel !== view;
  });
  viewTabResultsEl.setAttribute("aria-selected", String(view === "results"));
  viewTabSignalsEl.setAttribute("aria-selected", String(view === "signals"));
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
    "#signalsButton, #collectButton, .signal-create-button, .signal-relay-button"
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

function saveActiveJob(job = null) {
  try {
    if (job) {
      window.sessionStorage.setItem(activeJobStorageKey, JSON.stringify(job));
    } else {
      window.sessionStorage.removeItem(activeJobStorageKey);
    }
  } catch (_error) {
    // 会话存储不可用时仍可在当前页面等待任务完成。
  }
}

function loadActiveJob() {
  try {
    const raw = window.sessionStorage.getItem(activeJobStorageKey);
    return raw ? JSON.parse(raw) : null;
  } catch (_error) {
    return null;
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

async function populateModelOptions() {
  const modelIdEl = document.getElementById("modelId");
  try {
    const response = await authFetch("/api/models", { cache: "no-store" });
    if (!response.ok) throw new Error("无法读取模型列表");
    const catalog = await response.json();
    modelIdEl.innerHTML = "";
    for (const model of catalog.models) {
      const option = document.createElement("option");
      option.value = model.id;
      option.textContent = model.available ? model.name : `${model.name}（未配置）`;
      option.disabled = !model.available;
      modelIdEl.appendChild(option);
    }
    modelIdEl.value = catalog.default_model_id;
  } catch (error) {
    console.warn("Loading model catalog failed", error);
  }
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
        await resumeActiveJob();
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
      populateModelOptions(),
    ]);
    if (!meResponse.ok) throw new Error("无法检查登录状态");
    const me = await meResponse.json();
    if (me.authenticated) {
      showWorkspace(me.user);
      setStatus();
    } else {
      saveSessionToken();
    }
    await resumeActiveJob();
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
    model_id: document.getElementById("modelId").value || null,
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
  setActiveView("results");
  const rendered = responseHtml(data);
  researchEl.innerHTML = rendered.research;
  draftsEl.innerHTML = rendered.drafts;
}

function renderSourceSummaryOnly(data) {
  setActiveView("results");
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
  setActiveView("signals");
  setStatus(`已读取 ${items.length} 条线索`, "success");
}

async function collectSignals() {
  setStatus("正在执行 RSS 采集...", "loading");
  const response = await authFetch("/api/collect/rss", { method: "POST" });
  if (!response.ok) {
    if (await handleAuthFailure(response)) throw new Error("请登录后重试");
    throw new Error(readableApiError(await response.text()));
  }
  const result = await response.json();
  await loadSignals();
  setStatus(
    `采集完成 · 新增 ${result.saved} 条 · 重复 ${result.duplicates} 条 · `
    + `失败 ${result.failed_feeds} 个源`,
    "success"
  );
}

async function callApi(path, payload) {
  setStatus("正在提交后台生成任务...", "loading");
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
  const job = await response.json();
  if (!job.job_id || !job.poll_url) {
    throw new Error("服务未返回可查询的任务 ID");
  }
  saveActiveJob(job);
  const data = await pollOperationJob(job);
  renderResponse(data);
  setStatus("生成完成，结果已显示在右侧", "success");
}

function wait(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function pollOperationJob(
  job,
  { ignoreMissing = false, pollImmediately = false } = {},
) {
  let transientFailures = 0;
  let firstPoll = true;
  while (true) {
    if (!firstPoll || !pollImmediately) await wait(jobPollIntervalMs);
    firstPoll = false;
    let response;
    try {
      response = await authFetch(job.poll_url, { cache: "no-store" });
    } catch (_error) {
      transientFailures += 1;
      if (transientFailures <= 10) {
        setStatus("暂时无法读取任务进度，正在重试...", "loading");
        continue;
      }
      throw new Error("暂时无法读取任务进度；任务仍可能在后台运行，刷新页面后可继续查询");
    }

    if (response.status >= 500) {
      transientFailures += 1;
      if (transientFailures <= 10) {
        setStatus("服务暂时不可用，正在重试任务进度...", "loading");
        continue;
      }
    }
    transientFailures = 0;

    if (!response.ok) {
      if (await handleAuthFailure(response)) throw new Error("请登录后继续查询任务");
      const text = await response.text();
      if (response.status === 404) {
        saveActiveJob();
        if (ignoreMissing) return null;
      }
      throw new Error(readableApiError(text));
    }

    const state = await response.json();
    if (state.status === "queued") {
      setStatus("任务已排队，等待可用生成槽位...", "loading");
      continue;
    }
    if (state.status === "running") {
      setStatus("后台正在研究、配图和生成草稿...", "loading");
      continue;
    }
    if (state.status === "failed") {
      saveActiveJob();
      throw new Error(state.error || "后台生成任务失败");
    }
    if (state.status === "succeeded" && state.result) {
      saveActiveJob();
      return state.result;
    }
    saveActiveJob();
    throw new Error("任务返回了无法识别的状态");
  }
}

async function resumeActiveJob() {
  const job = loadActiveJob();
  if (!job || actionStartedAt) return;
  if (!currentUser && authConfig?.required !== false) return;
  const button = job.operation === "revise" ? reviseButtonEl : generateButtonEl;
  await runButtonAction(button, "正在恢复任务...", async () => {
    const data = await pollOperationJob(job, {
      ignoreMissing: true,
      pollImmediately: true,
    });
    if (!data) {
      setStatus("上次后台任务已失效，可以重新点击生成", "info");
      return;
    }
    renderResponse(data);
    setStatus("后台任务已完成，结果已恢复", "success");
  });
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
      model_id: document.getElementById("modelId").value || null,
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
      setActiveView("results");
      document.getElementById("topic").scrollIntoView({ behavior: "smooth", block: "center" });
    }
  });
});

signalsEl.addEventListener("click", (event) => {
  const button = event.target.closest(".signal-relay-button");
  if (!button) return;
  runButtonAction(button, "正在翻译整理原文...", async () => {
    const signal = latestSignals[Number(button.dataset.signalIndex)];
    if (!signal) throw new Error("线索不存在，请重新加载");
    const response = await authFetch("/api/relay_signal", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        signal,
        model_id: document.getElementById("modelId").value || null,
      }),
    });
    if (!response.ok) {
      if (await handleAuthFailure(response)) throw new Error("请登录后重试");
      throw new Error(readableApiError(await response.text()));
    }
    const data = await response.json();
    renderResponse(data);
    setStatus("已生成快讯草稿，请审核后发布", "success");
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
    await callApi("/api/generate/jobs", payload);
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
    await callApi("/api/revise/jobs", {
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

const collectButtonEl = document.getElementById("collectButton");
collectButtonEl.addEventListener("click", () => {
  runButtonAction(collectButtonEl, "正在采集...", async () => {
    if (!(await requireAuthentication("执行 RSS 采集"))) return;
    await collectSignals();
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

viewTabResultsEl.addEventListener("click", () => setActiveView("results"));
viewTabSignalsEl.addEventListener("click", () => setActiveView("signals"));

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
