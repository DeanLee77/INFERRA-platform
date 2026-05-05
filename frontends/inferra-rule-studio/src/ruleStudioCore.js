export const SAMPLE_RULE_TEXT = `INPUT applicant.age AS NUMBER
INPUT service.days AS NUMBER
rule.isVeteran IS TRUE IF service.days >= 30
eligibility.homeLoanAssistance IS TRUE IF applicant.age >= 18 AND rule.isVeteran
review.manual IS TRUE IF eligibility.homeLoanAssistance OR service.days < 30`;

const KEYWORDS = new Set([
  "AND",
  "OR",
  "NOT",
  "TRUE",
  "FALSE",
  "IF",
  "IS",
  "AS",
  "INPUT",
  "NUMBER",
  "BOOLEAN",
  "TEXT",
  "STRING",
]);

export function parseRuleText(text) {
  const nodes = new Map();
  const edges = [];
  const diagnostics = [];

  const lines = String(text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  lines.forEach((line, index) => {
    const lineNumber = index + 1;
    const input = line.match(/^INPUT\s+(.+?)\s+AS\s+([A-Z_]+)$/i);
    if (input) {
      addNode(nodes, input[1], "input", lineNumber);
      return;
    }

    const conclusion = line.match(/^(.+?)\s+IS\s+(.+?)\s+IF\s+(.+)$/i);
    if (!conclusion) {
      diagnostics.push({
        severity: "error",
        line: lineNumber,
        message: "Unrecognised INFERRA rule line",
      });
      return;
    }

    const parent = conclusion[1].trim();
    const expression = conclusion[3].trim();
    addNode(nodes, parent, "conclusion", lineNumber);
    const relation = expression.toUpperCase().includes(" OR ") ? "OR" : "AND";

    extractFactNames(expression).forEach((child) => {
      addNode(nodes, child, "fact", lineNumber);
      edges.push({ from: child, to: parent, relation, line: lineNumber });
    });
  });

  const graph = buildHyperAdjacency([...nodes.values()], edges);
  const cycle = detectCycle([...nodes.values()], edges);
  if (cycle.length) {
    diagnostics.push({
      severity: "error",
      line: 0,
      message: `Cycle detected: ${cycle.join(" -> ")}`,
    });
  }

  return {
    nodes: [...nodes.values()],
    edges,
    graph,
    diagnostics,
    topologicalOrder: topologicalSort([...nodes.values()], edges),
  };
}

export function buildHyperAdjacency(nodes, edges) {
  const graph = {};
  nodes.forEach((node) => {
    graph[node.id] = [];
  });
  edges.forEach((edge) => {
    const groups = graph[edge.to] || [];
    const existing = groups.find((group) => group.depType === edge.relation);
    if (existing) {
      existing.children.push(edge.from);
    } else {
      groups.push({ depType: edge.relation, children: [edge.from] });
    }
    graph[edge.to] = groups;
  });
  Object.values(graph).forEach((groups) => {
    groups.forEach((group) => {
      group.children = [...new Set(group.children)].sort();
    });
  });
  return graph;
}

export function topologicalSort(nodes, edges) {
  const ids = nodes.map((node) => node.id);
  const inDegree = Object.fromEntries(ids.map((id) => [id, 0]));
  const outbound = Object.fromEntries(ids.map((id) => [id, []]));
  edges.forEach((edge) => {
    if (!(edge.from in inDegree) || !(edge.to in inDegree)) return;
    inDegree[edge.to] += 1;
    outbound[edge.from].push(edge.to);
  });

  const queue = ids.filter((id) => inDegree[id] === 0).sort();
  const order = [];
  while (queue.length) {
    const current = queue.shift();
    order.push(current);
    outbound[current].sort().forEach((next) => {
      inDegree[next] -= 1;
      if (inDegree[next] === 0) {
        queue.push(next);
        queue.sort();
      }
    });
  }
  return order.length === ids.length ? order : [];
}

export function detectCycle(nodes, edges) {
  const order = topologicalSort(nodes, edges);
  if (order.length === nodes.length) return [];
  const ids = new Set(nodes.map((node) => node.id));
  const blocked = new Set(order);
  return [...ids].filter((id) => !blocked.has(id)).sort();
}

export function layoutGraph(nodes, edges, width = 960, height = 520) {
  const order = topologicalSort(nodes, edges);
  const fallback = nodes.map((node) => node.id).sort();
  const sequence = order.length ? order : fallback;
  const depth = Object.fromEntries(sequence.map((id) => [id, 0]));

  sequence.forEach((id) => {
    edges
      .filter((edge) => edge.from === id)
      .forEach((edge) => {
        depth[edge.to] = Math.max(depth[edge.to] || 0, (depth[id] || 0) + 1);
      });
  });

  const layers = {};
  nodes.forEach((node) => {
    const layer = depth[node.id] || 0;
    layers[layer] = layers[layer] || [];
    layers[layer].push(node.id);
  });

  const maxLayer = Math.max(...Object.keys(layers).map(Number), 0);
  const xGap = Math.max((width - 160) / Math.max(maxLayer, 1), 140);
  const positions = {};
  Object.entries(layers).forEach(([layerKey, ids]) => {
    const layer = Number(layerKey);
    ids.sort();
    const yGap = Math.max((height - 120) / Math.max(ids.length, 1), 76);
    ids.forEach((id, index) => {
      positions[id] = {
        x: 80 + layer * xGap,
        y: 70 + index * yGap,
      };
    });
  });
  return positions;
}

export function validateRuleText(text) {
  const parsed = parseRuleText(text);
  const warnings = [];
  const hasGoal = parsed.nodes.some((node) => node.type === "conclusion");
  if (!hasGoal) {
    warnings.push("No conclusion nodes found");
  }
  const orphanInputs = parsed.nodes.filter(
    (node) => node.type === "input" && !parsed.edges.some((edge) => edge.from === node.id)
  );
  orphanInputs.forEach((node) => warnings.push(`Input is not used: ${node.id}`));
  return {
    ok: parsed.diagnostics.length === 0,
    errors: parsed.diagnostics,
    warnings,
    metrics: {
      nodes: parsed.nodes.length,
      edges: parsed.edges.length,
      conclusions: parsed.nodes.filter((node) => node.type === "conclusion").length,
      inputs: parsed.nodes.filter((node) => node.type === "input").length,
    },
  };
}

export function createPolicyCoverage(parsed) {
  const conclusionCount = parsed.nodes.filter((node) => node.type === "conclusion").length;
  const inputCount = parsed.nodes.filter((node) => node.type === "input").length;
  const branchingCount = parsed.edges.filter((edge) => edge.relation === "OR").length;
  return [
    { label: "Decision goals", value: conclusionCount },
    { label: "Evidence inputs", value: inputCount },
    { label: "Exception branches", value: branchingCount },
    { label: "Topo depth", value: parsed.topologicalOrder.length },
  ];
}

export function buildValidationPayload(ruleText, ruleName = "draft_rule") {
  return {
    rule_name: ruleName,
    rule_text: String(ruleText || ""),
  };
}

export function buildSyncPayload(ruleText, ruleName = "draft_rule") {
  const parsed = parseRuleText(ruleText);
  return {
    ...buildValidationPayload(ruleText, ruleName),
    graph_snapshot: parsed.graph,
    topological_order: parsed.topologicalOrder,
  };
}

export function createRuleStudioApiClient({ baseUrl = "", fetchImpl = globalThis.fetch } = {}) {
  if (typeof fetchImpl !== "function") {
    throw new TypeError("fetchImpl must be a function");
  }

  async function post(path, body) {
    const response = await fetchImpl(`${baseUrl}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok) {
      const message = payload?.detail || payload?.error || `Request failed: ${response.status}`;
      throw new Error(String(message));
    }
    return payload;
  }

  async function get(path) {
    const response = await fetchImpl(`${baseUrl}${path}`, { method: "GET" });
    const payload = await response.json();
    if (!response.ok) {
      const message = payload?.detail || payload?.error || `Request failed: ${response.status}`;
      throw new Error(String(message));
    }
    return payload;
  }

  return {
    validate(ruleText, ruleName = "draft_rule") {
      return post("/api/v1/rules/validate", buildValidationPayload(ruleText, ruleName));
    },
    getImports(ruleName, { depth, offset = 0, limit = 50 } = {}) {
      const params = new URLSearchParams({ offset: String(offset), limit: String(limit) });
      if (depth !== undefined) params.set("depth", String(depth));
      return get(`/api/v1/rules/${encodeURIComponent(ruleName)}/imports?${params.toString()}`);
    },
    syncStatus(ruleName) {
      return get(`/api/v1/sync/status?rule_name=${encodeURIComponent(ruleName)}`);
    },
  };
}

function addNode(nodes, id, type, line) {
  const key = id.trim();
  if (!nodes.has(key)) {
    nodes.set(key, {
      id: key,
      label: key.split(".").pop(),
      type,
      line,
    });
    return;
  }
  const existing = nodes.get(key);
  if (existing.type === "fact" && type !== "fact") {
    nodes.set(key, { ...existing, type, line });
  }
}

function extractFactNames(expression) {
  const matches = String(expression).match(/[A-Za-z_][\w.]*/g) || [];
  return [...new Set(matches.filter((token) => !KEYWORDS.has(token.toUpperCase())))];
}
