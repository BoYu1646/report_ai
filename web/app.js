let currentConfig = null;
let latestReportSignature = "";

const AUTO_REFRESH_MS = 15000;
const CRON_PRESETS = new Set(["*/2 * * * *", "*/5 * * * *", "0 * * * *", "0 18 * * 5"]);

const $ = (id) => document.getElementById(id);

function setStatus(message) {
  $("status").textContent = message;
}

function setButtonBusy(id, busy, label) {
  const button = $(id);
  if (!button) return;
  if (!button.dataset.defaultLabel) {
    button.dataset.defaultLabel = button.textContent;
  }
  button.disabled = busy;
  button.textContent = busy ? label : button.dataset.defaultLabel;
}

function updateFeishuAuthFields() {
  const mode = $("feishuAuthMode").value;
  $("feishuLarkCliFields").hidden = mode !== "lark_cli";
  $("feishuOpenApiFields").hidden = mode !== "openapi";
}

function updateSchedulePreset(cron) {
  const isPreset = CRON_PRESETS.has(cron);
  $("schedulePreset").value = isPreset ? cron : "custom";
  $("scheduleCron").hidden = isPreset;
  if (!isPreset) {
    $("scheduleCron").value = cron;
  }
}

function applySchedulePreset() {
  const preset = $("schedulePreset").value;
  $("scheduleCron").hidden = preset !== "custom";
  if (preset !== "custom") {
    $("scheduleCron").value = preset;
    return;
  }
  $("scheduleCron").focus();
}

function validateCron(cron) {
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5 || parts.some((part) => !part)) {
    throw new Error("Cron 表达式必须是 5 段格式，例如 */2 * * * *");
  }
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
  updateSchedulePreset(config.schedule.cron);
  $("gitEnabled").checked = Boolean(config.sources.git.enabled);
  $("gitToken").value = "";
  $("gitRepos").value = (config.sources.git.repos || []).join(", ");
  $("feishuAppId").value = "";
  $("feishuAppSecret").value = "";
  $("feishuTenantToken").value = "";
  $("feishuUserToken").value = "";
  $("feishuAuthMode").value = config.sources.feishu.auth_mode || "openapi";
  $("feishuLarkCliIdentity").value = config.sources.feishu.lark_cli_identity || "user";
  updateFeishuAuthFields();
  $("feishuMessagesEnabled").checked = Boolean(config.sources.feishu.messages.enabled);
  $("feishuChatIds").value = (config.sources.feishu.messages.chat_ids || []).join(", ");
  $("feishuCalendarEnabled").checked = Boolean(config.sources.feishu.calendar.enabled);
  $("feishuCalendarIds").value = (config.sources.feishu.calendar.calendar_ids || []).join(", ");
  $("template").value = config.report.template || "";
  $("outputDir").value = config.report.output_dir || "./reports";
}

function clearSecretFields(config) {
  config.sources.git.token = "";
  config.sources.feishu.app_id = "";
  config.sources.feishu.app_secret = "";
  config.sources.feishu.tenant_access_token = "";
  config.sources.feishu.user_access_token = "";
  config.llm.api_key = "";
}

function clearSecretInputs() {
  $("gitToken").value = "";
  $("feishuAppId").value = "";
  $("feishuAppSecret").value = "";
  $("feishuTenantToken").value = "";
  $("feishuUserToken").value = "";
}

function readForm() {
  const config = structuredClone(currentConfig);
  const schedulePreset = $("schedulePreset").value;
  config.schedule.cron = schedulePreset === "custom" ? $("scheduleCron").value.trim() : schedulePreset;
  validateCron(config.schedule.cron);
  config.sources.git.enabled = $("gitEnabled").checked;
  config.sources.git.token = $("gitToken").value.trim();
  config.sources.git.repos = $("gitRepos")
    .value.split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  config.sources.feishu.app_id = $("feishuAppId").value.trim();
  config.sources.feishu.app_secret = $("feishuAppSecret").value.trim();
  config.sources.feishu.tenant_access_token = $("feishuTenantToken").value.trim();
  config.sources.feishu.user_access_token = $("feishuUserToken").value.trim();
  config.sources.feishu.auth_mode = $("feishuAuthMode").value;
  config.sources.feishu.lark_cli_identity = $("feishuLarkCliIdentity").value;
  config.sources.feishu.messages.enabled = $("feishuMessagesEnabled").checked;
  config.sources.feishu.messages.chat_ids = $("feishuChatIds")
    .value.split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  config.sources.feishu.calendar.enabled = $("feishuCalendarEnabled").checked;
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
    setButtonBusy("saveConfig", true, "保存中...");
    const config = readForm();
    await requestJson("/api/config", { method: "POST", body: JSON.stringify(config) });
    clearSecretFields(config);
    clearSecretInputs();
    currentConfig = config;
    setStatus("配置已保存，定时任务已重新加载；密钥仅在当前后端进程中生效，不写入 YAML。");
  } catch (error) {
    setStatus(`保存失败：${error.message}`);
  } finally {
    setButtonBusy("saveConfig", false);
  }
});

$("generate").addEventListener("click", async () => {
  try {
    setButtonBusy("generate", true, "生成中...");
    setStatus("正在生成周报...");
    const result = await requestJson("/api/reports/generate", {
      method: "POST",
      body: JSON.stringify({
        template: $("template").value.trim(),
      }),
    });
    renderMarkdown(result.markdown);
    latestReportSignature = result.meta.output_path;
    $("meta").textContent = `最新报告：${reportFilename(result.meta.output_path)}，周期 ${result.meta.week_start} 至 ${result.meta.week_end}，工作项 ${result.meta.item_count} 条，LLM：${
      result.meta.used_llm ? "已启用" : "本地兜底"
    }`;
    const warningCount = (result.meta.collection_errors || []).length;
    setStatus(
      warningCount
        ? `已生成：${result.meta.output_path}；采集告警 ${warningCount} 条，请查看报告末尾。`
        : `已生成：${result.meta.output_path}`
    );
  } catch (error) {
    setStatus(`生成失败：${error.message}`);
  } finally {
    setButtonBusy("generate", false);
  }
});

$("feishuAuthMode").addEventListener("change", updateFeishuAuthFields);
$("schedulePreset").addEventListener("change", applySchedulePreset);

loadInitial().catch((error) => setStatus(`初始化失败：${error.message}`));
setInterval(() => {
  loadLatestReport({ silent: true }).catch((error) => setStatus(`自动刷新失败：${error.message}`));
}, AUTO_REFRESH_MS);
