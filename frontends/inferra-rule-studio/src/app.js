import {
  SAMPLE_RULE_TEXT,
  createPolicyCoverage,
  layoutGraph,
  parseRuleText,
  validateRuleText,
} from "./ruleStudioCore.js";

const state = {
  parsed: parseRuleText(SAMPLE_RULE_TEXT),
  positions: {},
  selectedNode: null,
};

const elements = {
  canvas: document.querySelector("#graphCanvas"),
  coverage: document.querySelector("#coverageMetrics"),
  inspector: document.querySelector("#nodeInspector"),
  layoutBtn: document.querySelector("#layoutBtn"),
  ruleText: document.querySelector("#ruleText"),
  status: document.querySelector("#statusLine"),
  tabs: [...document.querySelectorAll(".tab")],
  traceOutput: document.querySelector("#traceOutput"),
  validateBtn: document.querySelector("#validateBtn"),
  validationOutput: document.querySelector("#validationOutput"),
  views: [...document.querySelectorAll(".view")],
};

const ctx = elements.canvas.getContext("2d");
elements.ruleText.value = SAMPLE_RULE_TEXT;

function refresh() {
  state.parsed = parseRuleText(elements.ruleText.value);
  state.positions = layoutGraph(
    state.parsed.nodes,
    state.parsed.edges,
    elements.canvas.width,
    elements.canvas.height
  );
  drawGraph();
  renderMetrics();
  renderValidation();
  renderTrace();
}

function drawGraph() {
  ctx.clearRect(0, 0, elements.canvas.width, elements.canvas.height);
  ctx.fillStyle = "#fbfcfc";
  ctx.fillRect(0, 0, elements.canvas.width, elements.canvas.height);

  state.parsed.edges.forEach((edge) => {
    const from = state.positions[edge.from];
    const to = state.positions[edge.to];
    if (!from || !to) return;
    ctx.strokeStyle = edge.relation === "OR" ? "#b7791f" : "#0f766e";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(from.x + 70, from.y);
    ctx.lineTo(to.x - 70, to.y);
    ctx.stroke();
    ctx.fillStyle = ctx.strokeStyle;
    ctx.fillText(edge.relation, (from.x + to.x) / 2, (from.y + to.y) / 2 - 7);
  });

  state.parsed.nodes.forEach((node) => {
    const pos = state.positions[node.id];
    if (!pos) return;
    const selected = state.selectedNode === node.id;
    ctx.fillStyle = node.type === "conclusion" ? "#e8f6f3" : node.type === "input" ? "#fff7e6" : "#f3f5f4";
    ctx.strokeStyle = selected ? "#b42318" : node.type === "conclusion" ? "#0f766e" : "#66736d";
    ctx.lineWidth = selected ? 3 : 1.5;
    roundedRect(ctx, pos.x - 70, pos.y - 24, 140, 48, 8);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = "#17201c";
    ctx.font = "12px Segoe UI, Arial";
    ctx.textAlign = "center";
    ctx.fillText(trimLabel(node.label), pos.x, pos.y + 4);
  });
}

function renderMetrics() {
  elements.coverage.innerHTML = createPolicyCoverage(state.parsed)
    .map((metric) => `<div class="metric"><strong>${metric.value}</strong><span>${metric.label}</span></div>`)
    .join("");
}

function renderValidation() {
  const result = validateRuleText(elements.ruleText.value);
  elements.status.value = result.ok ? "Valid graph" : "Validation failed";
  elements.validationOutput.textContent = JSON.stringify(result, null, 2);
}

function renderTrace() {
  const payload = {
    graph_backend: "HyperAdjacencyGraph",
    topological_order: state.parsed.topologicalOrder,
    child_groups: state.parsed.graph,
  };
  elements.traceOutput.textContent = JSON.stringify(payload, null, 2);
}

function setView(name) {
  elements.tabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.view === name));
  elements.views.forEach((view) => view.classList.toggle("active", view.id === `${name}View`));
}

function hitTest(x, y) {
  return state.parsed.nodes.find((node) => {
    const pos = state.positions[node.id];
    return pos && Math.abs(pos.x - x) <= 72 && Math.abs(pos.y - y) <= 26;
  });
}

function roundedRect(context, x, y, width, height, radius) {
  context.beginPath();
  context.moveTo(x + radius, y);
  context.arcTo(x + width, y, x + width, y + height, radius);
  context.arcTo(x + width, y + height, x, y + height, radius);
  context.arcTo(x, y + height, x, y, radius);
  context.arcTo(x, y, x + width, y, radius);
  context.closePath();
}

function trimLabel(value) {
  return value.length > 18 ? `${value.slice(0, 15)}...` : value;
}

elements.canvas.addEventListener("click", (event) => {
  const bounds = elements.canvas.getBoundingClientRect();
  const scaleX = elements.canvas.width / bounds.width;
  const scaleY = elements.canvas.height / bounds.height;
  const node = hitTest((event.clientX - bounds.left) * scaleX, (event.clientY - bounds.top) * scaleY);
  state.selectedNode = node ? node.id : null;
  elements.inspector.innerHTML = node
    ? `<strong>${node.id}</strong><span>${node.type} at line ${node.line}</span>`
    : "<strong>No node selected</strong><span>Click a node to inspect it.</span>";
  drawGraph();
});

elements.tabs.forEach((tab) => tab.addEventListener("click", () => setView(tab.dataset.view)));
elements.validateBtn.addEventListener("click", refresh);
elements.layoutBtn.addEventListener("click", refresh);
elements.exportBtn.addEventListener("click", () => {
  renderTrace();
  setView("trace");
});
elements.ruleText.addEventListener("input", refresh);

refresh();
