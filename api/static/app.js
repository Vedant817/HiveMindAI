const state = {
  lastRun: null,
  defaults: null,
  events: [],
  phases: {},
  activePhaseKey: null,
  heartbeatTimer: null,
  runStartedAt: null,
  lastEventAt: null,
  running: false,
};

const $ = (id) => document.getElementById(id);
const apiBase = document.body.dataset.apiBase || window.location.origin;

const routes = {
  demoDefaults: "/demo/defaults",
  demoRun: "/demo/run",
  demoRunStream: "/demo/run/stream",
  configCheck: "/config/check",
};

const phaseDefinitions = [
  { key: "config", label: "Config", detail: "Load provider and fallback settings", icon: "settings" },
  { key: "swarm", label: "Swarm start", detail: "Activate PM, executor, validator", icon: "network" },
  { key: "planning", label: "PM planning", detail: "Build dependency DAG", icon: "list-tree" },
  { key: "execution", label: "Execution", detail: "Run each assigned task", icon: "cpu" },
  { key: "validation", label: "Validation", detail: "Check outputs and confidence", icon: "badge-check" },
  { key: "gate", label: "Human gate", detail: "Route risky work for approval", icon: "user-check" },
  { key: "memory", label: "Memory", detail: "Persist DAG and trace", icon: "database" },
  { key: "reflection", label: "Reflection", detail: "Review run quality", icon: "sparkles" },
  { key: "meeting", label: "Tickets", detail: "Extract Jira-ready actions", icon: "ticket" },
  { key: "debate", label: "Debate", detail: "Score specialist proposals", icon: "messages-square" },
  { key: "summary", label: "Summary", detail: "Prepare manager report", icon: "file-text" },
];

const pipelineDefinitions = [
  { key: "config", label: "Inputs", detail: "Goal and transcript", icon: "inbox" },
  { key: "planning", label: "PM Orchestrator", detail: "DAG and dispatch", icon: "workflow" },
  { key: "execution", label: "Specialist Agents", detail: "Execute tasks", icon: "bot" },
  { key: "validation", label: "Validator", detail: "Score confidence", icon: "shield-check" },
  { key: "gate", label: "Human Gate", detail: "Approval when needed", icon: "user-check" },
  { key: "summary", label: "Outputs", detail: "Tickets and report", icon: "send" },
];

const emptyClass = "flex min-h-56 items-center justify-center rounded-md border border-dashed border-line p-4 text-center text-muted";
const contentClass = "grid gap-2";
const itemBaseClass = "rounded-md border border-line bg-white p-3 shadow-sm";
const titleClass = "font-bold leading-tight text-ink";
const metaClass = "mt-1 text-sm leading-relaxed text-muted";

function initPhaseState() {
  state.phases = Object.fromEntries(
    phaseDefinitions.map((phase) => [
      phase.key,
      {
        ...phase,
        status: "pending",
        message: phase.detail,
      },
    ]),
  );
}

function setLoading(isLoading) {
  state.running = isLoading;
  $("runDemoButton").disabled = isLoading;
  $("configButton").disabled = isLoading;
  $("runDemoButton").querySelector("span").textContent = isLoading ? "Running..." : "Run live demo";
  $("runStatePill").textContent = isLoading ? "Running live stream" : "Idle";
  $("runStatePill").className = isLoading
    ? "inline-flex min-h-9 items-center rounded-full border border-teal/40 bg-teal/10 px-3 text-sm font-semibold text-teal"
    : "inline-flex min-h-9 items-center rounded-full border border-line bg-paper px-3 text-sm font-semibold text-muted";
  if (isLoading) {
    startHeartbeat();
  } else {
    stopHeartbeat();
  }
}

async function postJson(url, body) {
  const response = await fetch(apiUrl(url), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

async function getJson(url) {
  const response = await fetch(apiUrl(url));
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

async function runDemo() {
  const payload = readPayload();
  resetRun(payload);
  setLoading(true);

  try {
    await streamDemo(payload);
  } catch (error) {
    addEvent({ phase: "error", status: "failed", message: `Streaming failed, retrying normal request: ${error.message}` });
    try {
      const data = await postJson(routes.demoRun, payload);
      state.lastRun = data;
      markAllComplete();
      renderAll(data);
    } catch (fallbackError) {
      renderError(fallbackError);
    }
  } finally {
    setLoading(false);
    renderIcons();
  }
}

async function streamDemo(payload) {
  const response = await fetch(apiUrl(routes.demoRunStream), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok || !response.body) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";
    for (const chunk of chunks) {
      handleStreamChunk(chunk);
    }
  }

  if (buffer.trim()) {
    handleStreamChunk(buffer);
  }
}

function handleStreamChunk(chunk) {
  const line = chunk
    .split("\n")
    .find((row) => row.startsWith("data:"));
  if (!line) return;
  const event = JSON.parse(line.replace(/^data:\s*/, ""));
  if (event.type === "complete") {
    updatePhase(event.phase, "complete", event.message);
    addEvent(event);
    state.lastRun = event.data;
    markAllComplete();
    renderAll(event.data);
    return;
  }
  if (event.type === "error") {
    updatePhase(event.phase, "failed", event.message);
    addEvent(event);
    renderError(new Error(event.message));
    return;
  }

  updatePhase(event.phase, event.status, event.message);
  addEvent(event);
  renderPartialEvent(event);
}

async function checkConfig() {
  setLoading(true);
  try {
    const data = await getJson(routes.configCheck);
    renderConfig(data);
    renderMode(configMode(data));
    updatePhase("config", "complete", data.local_test_ready ? "Local testing is ready." : "Configuration needs attention.");
    addEvent({ phase: "config", status: "complete", message: "Configuration check completed." });
  } catch (error) {
    renderError(error);
  } finally {
    setLoading(false);
    renderIcons();
  }
}

async function loadDefaults() {
  try {
    const defaults = await getJson(routes.demoDefaults);
    state.defaults = defaults;
    $("goalInput").value = defaults.goal || "";
    $("transcriptInput").value = defaults.transcript || "";
    renderPromptOverview(readPayload());
  } catch (error) {
    renderError(error);
  }
}

function readPayload() {
  return {
    goal: $("goalInput").value.trim(),
    transcript: $("transcriptInput").value.trim(),
  };
}

function resetRun(payload) {
  state.events = [];
  state.activePhaseKey = null;
  state.runStartedAt = Date.now();
  state.lastEventAt = Date.now();
  initPhaseState();
  renderPromptOverview(payload);
  renderPhases();
  renderPipelineMap();
  renderEventFeed();
  setMetricsEmpty();
  setEmpty("dagView", "The PM agent will render the task graph here.");
  setEmpty("ticketView", "The meeting agent will render extracted tickets here.");
  setEmpty("timelineView", "Execution events will appear as agents complete work.");
  setEmpty("debateView", "Debate results will appear after specialist agents score proposals.");
  $("summaryView").textContent = "Running. The manager summary will appear when the final stage completes.";
}

function renderAll(data) {
  renderMode(data.mode);
  renderMetrics(data.metrics);
  renderPromptOverview({ goal: data.goal, transcript: $("transcriptInput").value.trim() });
  renderDag(data.swarm.dag.tasks);
  renderTickets(data.meeting.tickets);
  renderTimeline(data.swarm.history);
  renderDebate(data.debate);
  $("summaryView").textContent = data.summary;
  renderConfig(data.config);
  renderIcons();
}

function renderPartialEvent(event) {
  if (event.tasks) {
    renderDag(event.tasks);
  }
  if (event.tickets) {
    renderTickets(event.tickets);
  }
  if (event.debate) {
    renderDebate(event.debate);
  }
}

function renderMode(mode) {
  const pill = $("modePill");
  const production = mode === "production";
  const freeCloud = mode === "free-cloud";
  pill.textContent = production
    ? "Azure production ready"
    : freeCloud
      ? "Free cloud stack ready"
      : "Local/free demo mode";
  pill.className = production || freeCloud
    ? "inline-flex min-h-9 items-center rounded-full border border-green/40 bg-green/10 px-3 text-sm font-semibold text-green"
    : "inline-flex min-h-9 items-center rounded-full border border-amber/40 bg-amber/10 px-3 text-sm font-semibold text-amber";
}

function configMode(config) {
  if (config.app_stack === "azure" && config.production_ready) {
    return "production";
  }
  if (config.app_stack === "free" && config.free_stack_ready) {
    return "free-cloud";
  }
  return "local-demo";
}

function renderMetrics(metrics) {
  $("healthMetric").textContent = `${metrics.health}%`;
  $("taskMetric").textContent = `${metrics.done}/${metrics.total}`;
  $("ticketMetric").textContent = String(metrics.tickets_created);
  $("agentMetric").textContent = String(metrics.agents_involved.length);
}

function setMetricsEmpty() {
  $("healthMetric").textContent = "--";
  $("taskMetric").textContent = "--";
  $("ticketMetric").textContent = "--";
  $("agentMetric").textContent = "--";
}

function renderPromptOverview(payload) {
  const transcriptLines = payload.transcript
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const actionLines = transcriptLines.filter((line) => /\b(todo|action|need|needs|build|fix|create|implement|review)\b/i.test(line));
  const goalWords = payload.goal.split(/\s+/).filter(Boolean).length;
  $("promptStats").textContent = `${goalWords} goal words | ${actionLines.length} detected action lines`;
  $("promptOverview").innerHTML = [
    promptCard("Goal", payload.goal || "No goal entered yet.", "target"),
    promptCard("Detected actions", actionLines.slice(0, 4).join("\n") || "No action lines detected yet.", "clipboard-list"),
    promptCard("Expected outputs", "Task DAG, local/Jira tickets, validation trace, debate winner, executive summary.", "panel-top"),
  ].join("");
  renderIcons();
}

function promptCard(title, body, icon) {
  return `
    <div class="min-w-0 rounded-md border border-line bg-[#fbfcfa] p-3">
      <div class="mb-2 flex items-center gap-2 text-sm font-bold">
        <i data-lucide="${icon}" class="h-4 w-4 text-teal"></i>
        <span>${escapeHtml(title)}</span>
      </div>
      <p class="whitespace-pre-wrap break-words text-sm leading-relaxed text-muted">${escapeHtml(body)}</p>
    </div>
  `;
}

function renderPhases() {
  const values = phaseDefinitions.map((phase) => state.phases[phase.key]);
  $("phaseView").innerHTML = values.map(phaseCard).join("");
  const completed = values.filter((phase) => isComplete(phase.status)).length;
  const running = values.some((phase) => phase.status === "running") ? 0.5 : 0;
  const percent = Math.min(100, Math.round(((completed + running) / values.length) * 100));
  $("progressPercent").textContent = `${percent}%`;
  $("progressBar").style.width = `${percent}%`;
  const active =
    (state.activePhaseKey && state.phases[state.activePhaseKey]) ||
    values.find((phase) => phase.status === "running") ||
    [...values].reverse().find((phase) => isComplete(phase.status));
  $("activePhaseLabel").textContent = active ? `${active.label}: ${active.message}` : "No active phase";
  renderIcons();
}

function phaseCard(phase) {
  const styles = statusStyles(phase.status);
  return `
    <div class="grid grid-cols-[32px_minmax(0,1fr)] gap-3 rounded-md border ${styles.border} ${styles.bg} p-2.5">
      <span class="flex h-8 w-8 items-center justify-center rounded-md ${styles.iconBg} ${styles.text}">
        <i data-lucide="${phase.icon}" class="h-4 w-4"></i>
      </span>
      <div class="min-w-0">
        <div class="flex items-center justify-between gap-2">
          <strong class="truncate text-sm leading-tight">${escapeHtml(phase.label)}</strong>
          <span class="shrink-0 text-xs font-bold uppercase tracking-normal ${styles.text}">${escapeHtml(phase.status)}</span>
        </div>
        <p class="mt-1 break-words text-xs leading-relaxed text-muted">${escapeHtml(phase.message)}</p>
      </div>
    </div>
  `;
}

function renderPipelineMap() {
  $("pipelineMap").innerHTML = pipelineDefinitions
    .map((item) => {
      const phase = state.phases[item.key] || { status: "pending" };
      const styles = statusStyles(phase.status);
      return `
        <div class="min-h-32 rounded-md border ${styles.border} ${styles.bg} p-3">
          <div class="flex items-center justify-between gap-2">
            <i data-lucide="${item.icon}" class="h-5 w-5 ${styles.text}"></i>
            <span class="text-xs font-bold uppercase tracking-normal ${styles.text}">${escapeHtml(phase.status)}</span>
          </div>
          <strong class="mt-4 block break-words text-base leading-tight">${escapeHtml(item.label)}</strong>
          <p class="mt-1 break-words text-sm leading-relaxed text-muted">${escapeHtml(item.detail)}</p>
        </div>
      `;
    })
    .join("");
  renderIcons();
}

function updatePhase(phaseKey, status, message) {
  const key = state.phases[phaseKey] ? phaseKey : "swarm";
  if (!state.phases[key]) return;
  const normalized = normalizeStatus(status);
  completeEarlierRunningPhases(key, normalized);
  state.phases[key].status = normalized;
  state.phases[key].message = message || state.phases[key].message;
  if (normalized === "running") {
    state.activePhaseKey = key;
  } else if (normalized === "complete" && state.activePhaseKey === key) {
    state.activePhaseKey = key;
  }
  renderPhases();
  renderPipelineMap();
}

function completeEarlierRunningPhases(currentKey, status) {
  if (status !== "running") return;
  const currentIndex = phaseDefinitions.findIndex((phase) => phase.key === currentKey);
  if (currentIndex < 0) return;
  for (const phase of phaseDefinitions.slice(0, currentIndex)) {
    if (state.phases[phase.key]?.status === "running") {
      state.phases[phase.key].status = "complete";
    }
  }
}

function markAllComplete() {
  for (const phase of Object.values(state.phases)) {
    if (phase.status !== "failed") {
      phase.status = "complete";
    }
  }
  state.activePhaseKey = "summary";
  renderPhases();
  renderPipelineMap();
}

function addEvent(event) {
  state.lastEventAt = Date.now();
  state.events.unshift({
    phase: event.phase || "swarm",
    status: normalizeStatus(event.status || "running"),
    message: event.message || "Agent event received.",
    createdAt: new Date().toLocaleTimeString(),
  });
  state.events = state.events.slice(0, 80);
  renderEventFeed();
}

function startHeartbeat() {
  stopHeartbeat();
  state.runStartedAt = state.runStartedAt || Date.now();
  state.lastEventAt = state.lastEventAt || Date.now();
  state.heartbeatTimer = window.setInterval(() => {
    const elapsed = Math.max(1, Math.round((Date.now() - state.runStartedAt) / 1000));
    const sinceEvent = Math.round((Date.now() - state.lastEventAt) / 1000);
    $("runStatePill").textContent = `Running live stream · ${elapsed}s`;
    const active = state.activePhaseKey ? state.phases[state.activePhaseKey] : null;
    if (active && state.running) {
      const waitText = sinceEvent >= 8 ? ` Still working, last backend event ${sinceEvent}s ago.` : "";
      $("activePhaseLabel").textContent = `${active.label}: ${active.message}${waitText}`;
    }
  }, 1000);
}

function stopHeartbeat() {
  if (state.heartbeatTimer) {
    window.clearInterval(state.heartbeatTimer);
    state.heartbeatTimer = null;
  }
}

function renderEventFeed() {
  $("eventCount").textContent = `${state.events.length} event${state.events.length === 1 ? "" : "s"}`;
  if (!state.events.length) {
    $("eventFeed").innerHTML = `<div class="rounded-md border border-dashed border-line p-3 text-sm text-muted">Run the demo to see live backend events.</div>`;
    return;
  }
  $("eventFeed").innerHTML = state.events
    .map((event) => {
      const styles = statusStyles(event.status);
      return `
        <div class="mb-2 rounded-md border ${styles.border} bg-white p-2.5 last:mb-0">
          <div class="flex items-center justify-between gap-2">
            <span class="text-xs font-bold uppercase tracking-normal ${styles.text}">${escapeHtml(event.phase)}</span>
            <span class="text-xs text-muted">${escapeHtml(event.createdAt)}</span>
          </div>
          <p class="mt-1 break-words text-sm leading-relaxed">${escapeHtml(event.message)}</p>
        </div>
      `;
    })
    .join("");
}

function renderDag(tasks) {
  $("dagView").className = contentClass;
  $("dagView").innerHTML = tasks
    .map(
      (task, index) => `
        <div class="${itemBaseClass} border-l-4 ${itemAccent(index)}">
          <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div class="min-w-0">
              <div class="${titleClass}">${index + 1}. ${escapeHtml(task.title)}</div>
              <div class="${metaClass}">${escapeHtml(task.description)}</div>
            </div>
            <span class="${badgeClass(task.status)}">${escapeHtml(task.status)}</span>
          </div>
          <div class="${metaClass}">Agent: ${escapeHtml(task.assigned_to)} | Depends on: ${escapeHtml((task.depends_on || []).length || "none")}</div>
        </div>
      `,
    )
    .join("");
}

function renderTickets(rows) {
  $("ticketView").className = contentClass;
  $("ticketView").innerHTML = rows
    .map((row, index) => {
      const ticket = row.ticket || row;
      return `
        <div class="${itemBaseClass} border-l-4 ${itemAccent(index)}">
          <div class="${titleClass}">${escapeHtml(ticket.title)}</div>
          <div class="${metaClass}">${escapeHtml(ticket.description)}</div>
          <div class="${metaClass}">Priority: ${escapeHtml(ticket.priority)} | Ticket: ${escapeHtml(ticket.jira_ticket_id || "pending")}</div>
        </div>
      `;
    })
    .join("");
}

function renderTimeline(history) {
  $("timelineView").className = "grid max-h-[540px] gap-2 overflow-y-auto pr-1";
  $("timelineView").innerHTML = history
    .map(
      (msg) => `
        <div class="grid gap-3 rounded-md border border-line bg-white p-3 sm:grid-cols-[88px_minmax(0,1fr)_64px] sm:items-center">
          <span class="${badgeClass(msg.status)}">${escapeHtml(msg.type)}</span>
          <div class="min-w-0">
            <div class="${titleClass}">${escapeHtml(msg.payload.title || "Agent event")}</div>
            <div class="${metaClass}">Agent: ${escapeHtml(msg.assigned_to || "swarm")} | Status: ${escapeHtml(msg.status)}</div>
          </div>
          <strong class="text-right">${Math.round((msg.confidence || 0) * 100)}%</strong>
        </div>
      `,
    )
    .join("");
}

function renderDebate(debate) {
  const winner = debate.winner || {};
  const proposals = debate.proposals || [];
  $("debateView").className = contentClass;
  $("debateView").innerHTML = `
    <div class="${itemBaseClass} border-l-4 border-l-teal">
      <div class="${titleClass}">Winner: ${escapeHtml(winner.winner || "Pending")}</div>
      <div class="${metaClass}">${escapeHtml(winner.rationale || "No rationale returned.")}</div>
    </div>
    ${proposals
      .map(
        (proposal) => `
          <div class="${itemBaseClass}">
            <div class="${titleClass}">${escapeHtml(proposal.agent)}</div>
            <div class="${metaClass}">${escapeHtml(proposal.proposal)}</div>
          </div>
        `,
      )
      .join("")}
  `;
}

function renderConfig(config) {
  const integrations = config.integrations || {};
  if ($("configEyebrow")) {
    $("configEyebrow").textContent = config.app_stack === "azure" ? "Production readiness" : "Free stack readiness";
  }
  if ($("configTitle")) {
    $("configTitle").textContent = config.stack_label || "Configuration check";
  }
  $("configView").innerHTML = Object.entries(integrations)
    .map(([name, value]) => {
      const ready = value.configured;
      const missing = ready ? "Ready" : `Add: ${value.missing.join(", ")}`;
      return `
        <div class="${itemBaseClass} min-w-0 border-l-4 ${ready ? "border-l-green" : "border-l-rose"}">
          <div class="${titleClass}">${escapeHtml(name)}</div>
          <div class="${metaClass} break-words">${escapeHtml(missing)}</div>
        </div>
      `;
    })
    .join("");
}

function renderError(error) {
  setLoading(false);
  updatePhase("swarm", "failed", error.message);
  addEvent({ phase: "error", status: "failed", message: error.message });
  $("summaryView").textContent = `Demo failed:\n${error.message}`;
}

function setEmpty(id, text) {
  $(id).className = emptyClass;
  $(id).textContent = text;
}

function apiUrl(path) {
  return new URL(path, apiBase).toString();
}

function itemAccent(index) {
  return ["border-l-teal", "border-l-amber", "border-l-violet", "border-l-green"][index % 4];
}

function badgeClass(status) {
  const styles = statusStyles(status);
  return `inline-flex min-h-7 items-center justify-center rounded-full px-2.5 text-xs font-bold uppercase tracking-normal ${styles.bg} ${styles.text}`;
}

function statusStyles(status) {
  const normalized = normalizeStatus(status);
  if (normalized === "complete" || normalized === "done") {
    return { border: "border-green/40", bg: "bg-green/10", text: "text-green", iconBg: "bg-green/10" };
  }
  if (normalized === "running") {
    return { border: "border-teal/50", bg: "bg-teal/10", text: "text-teal", iconBg: "bg-teal/10" };
  }
  if (normalized === "failed" || normalized === "blocked") {
    return { border: "border-rose/50", bg: "bg-rose/10", text: "text-rose", iconBg: "bg-rose/10" };
  }
  return { border: "border-line", bg: "bg-paper", text: "text-muted", iconBg: "bg-white" };
}

function normalizeStatus(status) {
  const value = String(status || "pending").toLowerCase();
  if (["complete", "completed", "done", "auto_execute"].includes(value)) return "complete";
  if (["running", "pending"].includes(value)) return value;
  if (["failed", "blocked", "error"].includes(value)) return "failed";
  return value;
}

function isComplete(status) {
  return normalizeStatus(status) === "complete";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderIcons() {
  if (window.lucide) {
    window.lucide.createIcons();
  }
}

initPhaseState();
renderPhases();
renderPipelineMap();
renderEventFeed();
setMetricsEmpty();
$("goalInput").addEventListener("input", () => renderPromptOverview(readPayload()));
$("transcriptInput").addEventListener("input", () => renderPromptOverview(readPayload()));
$("runDemoButton").addEventListener("click", runDemo);
$("configButton").addEventListener("click", checkConfig);
Promise.all([loadDefaults(), checkConfig()]).finally(renderIcons);
