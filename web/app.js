let currentConfig = null;
let latestReportSignature = "";

const AUTO_REFRESH_MS = 15000;

const $ = (id) => document.getElementById(id);

function setStatus(message) {
  $("status").textContent = message;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

function fillForm(config) {
  currentConfig = config;
  $("scheduleCron").value = config.schedule.cron;
  $("gitToken").value = config.sources.git.token || "";
  $("gitRepos").value = (config.sources.git.repos || []).join(", ");
  $("feishuAppId").value = config.sources.feishu.app_id || "";
  $("feishuAppSecret").value = config.sources.feishu.app_secret || "";
  $("feishuTenantToken").value = config.sources.feishu.tenant_access_token || "";
  $("feishuUserToken").value = config.sources.feishu.user_access_token || "";
  $("feishuChatIds").value = (config.sources.feishu.messages.chat_ids || []).join(", ");
  $("feishuCalendarIds").value = (config.sources.feishu.calendar.calendar_ids || []).join(", ");
  $("template").value = config.report.template || "";
  $("outputDir").value = config.report.output_dir || "./reports";
}

function readForm() {
  const config = structuredClone(currentConfig);
  config.schedule.cron = $("scheduleCron").value.trim();
  config.sources.git.token = $("gitToken").value.trim();
  config.sources.git.repos = $("gitRepos")
    .value.split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  config.sources.feishu.app_id = $("feishuAppId").value.trim();
  config.sources.feishu.app_secret = $("feishuAppSecret").value.trim();
  config.sources.feishu.tenant_access_token = $("feishuTenantToken").value.trim();
  config.sources.feishu.user_access_token = $("feishuUserToken").value.trim();
  config.sources.feishu.messages.chat_ids = $("feishuChatIds")
    .value.split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  config.sources.feishu.calendar.calendar_ids = $("feishuCalendarIds")
    .value.split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  config.report.template = $("template").value.trim() || currentConfig.report.template;
  config.report.output_dir = $("outputDir").value.trim() || "./reports";
  return config;
}

function renderMarkdown(markdown) {
  $("report").innerHTML = marked.parse(markdown || "# 暂无周报");
}

function reportFilename(outputPath) {
  return outputPath ? outputPath.split(/[\\/]/).pop() : "";
}

function updateLatestMeta(latest) {
  if (!latest.output_path) {
    $("meta").textContent = "暂无生成记录";
    return;
  }
  $("meta").textContent = `最新报告：${reportFilename(latest.output_path)}，更新时间：${latest.updated_at || "未知"}`;
}

async function loadLatestReport({ silent = false } = {}) {
  const latest = await requestJson("/api/reports/latest");
  const signature = latest.output_path || "";
  const changed = signature !== latestReportSignature;

  // 后端定时任务生成新文件后，页面自动刷新展示最新 Markdown。
  if (changed || !silent) {
    renderMarkdown(latest.markdown);
    updateLatestMeta(latest);
    latestReportSignature = signature;
  }

  if (changed && silent && latest.output_path) {
    setStatus(`检测到定时任务生成的新周报：${reportFilename(latest.output_path)}`);
  }
}

async function loadInitial() {
  const config = await requestJson("/api/config");
  fillForm(config);
  await loadLatestReport();
  setStatus("配置已加载，页面会自动刷新最新周报。");
}

$("saveConfig").addEventListener("click", async () => {
  try {
    const config = readForm();
    await requestJson("/api/config", { method: "POST", body: JSON.stringify(config) });
    currentConfig = config;
    setStatus("配置已保存，定时任务已重新加载。");
  } catch (error) {
    setStatus(`保存失败：${error.message}`);
  }
});

$("generate").addEventListener("click", async () => {
  try {
    setStatus("正在生成周报...");
    const result = await requestJson("/api/reports/generate", {
      method: "POST",
      body: JSON.stringify({
        template: $("template").value.trim(),
      }),
    });
    renderMarkdown(result.markdown);
    latestReportSignature = result.meta.output_path;
    $("meta").textContent = `周期 ${result.meta.week_start} 至 ${result.meta.week_end}，工作项 ${result.meta.item_count} 条，LLM：${
      result.meta.used_llm ? "已启用" : "本地兜底"
    }`;
    setStatus(`已生成：${result.meta.output_path}`);
  } catch (error) {
    setStatus(`生成失败：${error.message}`);
  }
});

loadInitial().catch((error) => setStatus(`初始化失败：${error.message}`));
setInterval(() => {
  loadLatestReport({ silent: true }).catch((error) => setStatus(`自动刷新失败：${error.message}`));
}, AUTO_REFRESH_MS);
