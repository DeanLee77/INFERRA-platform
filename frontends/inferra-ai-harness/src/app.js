import {
  SCENARIOS,
  buildEvaluationMatrix,
  simulateHarnessRun,
  traceToProvO,
} from "./harnessCore.js";

const elements = {
  canvas: document.querySelector("#traceCanvas"),
  gate: document.querySelector("#gateAction"),
  matrix: document.querySelector("#matrixOutput"),
  prompt: document.querySelector("#promptInput"),
  prov: document.querySelector("#provOutput"),
  reason: document.querySelector("#gateReason"),
  risk: document.querySelector("#riskScore"),
  run: document.querySelector("#runBtn"),
  scenario: document.querySelector("#scenarioSelect"),
  stages: document.querySelector("#stageStrip"),
};

const ctx = elements.canvas.getContext("2d");
const runs = [];

SCENARIOS.forEach((scenario) => {
  const option = document.createElement("option");
  option.value = scenario.id;
  option.textContent = scenario.name;
  elements.scenario.append(option);
});

function selectedScenario() {
  const base = SCENARIOS.find((scenario) => scenario.id === elements.scenario.value) || SCENARIOS[0];
  return { ...base, prompt: elements.prompt.value };
}

function loadScenario() {
  const scenario = SCENARIOS.find((item) => item.id === elements.scenario.value) || SCENARIOS[0];
  elements.prompt.value = scenario.prompt;
  runScenario();
}

function runScenario() {
  const run = simulateHarnessRun(selectedScenario());
  runs.push(run);
  renderRun(run);
}

function renderRun(run) {
  elements.risk.value = run.risk.score.toFixed(2);
  elements.gate.value = run.gate.action;
  elements.gate.className = `gate ${run.gate.action}`;
  elements.reason.value = run.gate.reason;
  elements.stages.innerHTML = run.stages
    .map((stage) => `<div class="stage"><strong>${stage.name}</strong><span>${stage.detail}</span></div>`)
    .join("");
  elements.matrix.textContent = JSON.stringify(buildEvaluationMatrix(runs.slice(-6)), null, 2);
  elements.prov.textContent = traceToProvO(run);
  drawTrace(run);
}

function drawTrace(run) {
  ctx.clearRect(0, 0, elements.canvas.width, elements.canvas.height);
  ctx.fillStyle = "#fbfcfc";
  ctx.fillRect(0, 0, elements.canvas.width, elements.canvas.height);

  const positions = {};
  const columns = {
    input: 120,
    fact: 350,
    missing: 610,
    goal: 880,
  };
  const byType = run.provenance.nodes.reduce((acc, node) => {
    acc[node.type] = acc[node.type] || [];
    acc[node.type].push(node);
    return acc;
  }, {});

  Object.entries(byType).forEach(([type, nodes]) => {
    nodes.forEach((node, index) => {
      positions[node.id] = {
        x: columns[type] || 520,
        y: 90 + index * 82,
      };
    });
  });

  run.provenance.links.forEach((link) => {
    const from = positions[link.from];
    const to = positions[link.to];
    if (!from || !to) return;
    ctx.strokeStyle = "#0f766e";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(from.x + 68, from.y);
    ctx.lineTo(to.x - 68, to.y);
    ctx.stroke();
  });

  run.provenance.nodes.forEach((node) => {
    const pos = positions[node.id];
    if (!pos) return;
    const color = node.type === "missing" ? "#fff7e6" : node.type === "goal" ? "#e8f6f3" : "#f4f6f5";
    ctx.fillStyle = color;
    ctx.strokeStyle = node.type === "missing" ? "#b7791f" : node.type === "goal" ? "#0f766e" : "#66736d";
    ctx.lineWidth = 1.5;
    roundedRect(ctx, pos.x - 68, pos.y - 24, 136, 48, 8);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = "#18211f";
    ctx.textAlign = "center";
    ctx.font = "12px Segoe UI, Arial";
    ctx.fillText(trim(node.label), pos.x, pos.y + 4);
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

function trim(label) {
  return label.length > 17 ? `${label.slice(0, 14)}...` : label;
}

elements.scenario.addEventListener("change", loadScenario);
elements.run.addEventListener("click", runScenario);
elements.scenario.value = SCENARIOS[0].id;
loadScenario();
