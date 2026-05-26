import assert from "node:assert/strict";
import {
  SAMPLE_RULE_TEXT,
  buildSyncPayload,
  buildValidationPayload,
  createPolicyCoverage,
  createRuleStudioApiClient,
  detectCycle,
  layoutGraph,
  parseRuleText,
  validateRuleText,
} from "../src/ruleStudioCore.js";

const parsed = parseRuleText(SAMPLE_RULE_TEXT);

assert.equal(parsed.diagnostics.length, 0);
assert.equal(parsed.nodes.some((node) => node.id === "eligibility.homeLoanAssistance"), true);
assert.equal(parsed.edges.some((edge) => edge.relation === "OR"), true);
assert.ok(parsed.topologicalOrder.indexOf("applicant.age") < parsed.topologicalOrder.indexOf("eligibility.homeLoanAssistance"));

const validation = validateRuleText(SAMPLE_RULE_TEXT);
assert.equal(validation.ok, true);
assert.equal(validation.metrics.conclusions, 3);

const positions = layoutGraph(parsed.nodes, parsed.edges, 800, 400);
assert.ok(Number.isFinite(positions["applicant.age"].x));
assert.ok(Number.isFinite(positions["eligibility.homeLoanAssistance"].y));

const coverage = createPolicyCoverage(parsed);
assert.equal(coverage.length, 4);

const cyclic = parseRuleText("A IS TRUE IF B\nB IS TRUE IF A");
assert.deepEqual(detectCycle(cyclic.nodes, cyclic.edges), ["A", "B"]);

const validationPayload = buildValidationPayload(SAMPLE_RULE_TEXT, "loan_rule");
assert.equal(validationPayload.rule_name, "loan_rule");
assert.equal(validationPayload.rule_text, SAMPLE_RULE_TEXT);

const syncPayload = buildSyncPayload(SAMPLE_RULE_TEXT, "loan_rule");
assert.equal(syncPayload.rule_name, "loan_rule");
assert.deepEqual(syncPayload.topological_order, parsed.topologicalOrder);
assert.ok(syncPayload.graph_snapshot["eligibility.homeLoanAssistance"]);

const calls = [];
const client = createRuleStudioApiClient({
  baseUrl: "http://localhost:8000",
  fetchImpl: async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return { ok: true, json: async () => ({ valid: true }) };
  },
});
const validationResponse = await client.validate(SAMPLE_RULE_TEXT, "loan_rule");
assert.equal(validationResponse.valid, true);
assert.equal(calls[0].url, "http://localhost:8000/api/v1/rules/validate");
assert.equal(calls[0].body.rule_name, "loan_rule");
