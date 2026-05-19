import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: Number(__ENV.VUS || 20),
  duration: __ENV.DURATION || "1m",
  thresholds: {
    http_req_failed: ["rate<0.05"],
    "http_req_duration{endpoint:live}": ["p(95)<300", "p(99)<750"],
    "http_req_duration{endpoint:metrics}": ["p(95)<300", "p(99)<750"],
    "http_req_duration{endpoint:goal_disabled}": ["p(95)<500", "p(99)<1000"],
    "http_req_duration{endpoint:abduct}": ["p(95)<1000", "p(99)<2000"],
    "http_req_duration{endpoint:induce_disabled}": ["p(95)<500", "p(99)<1000"],
    "http_req_duration{endpoint:readiness}": ["p(95)<7000"],
    checks: ["rate>0.95"],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const JSON_HEADERS = { headers: { "Content-Type": "application/json" } };

function postJson(path, payload, endpoint) {
  return http.post(`${BASE_URL}${path}`, JSON.stringify(payload), {
    headers: JSON_HEADERS.headers,
    tags: { endpoint },
  });
}

export function setup() {
  const health = http.get(`${BASE_URL}/api/v1/health`, {
    tags: { endpoint: "readiness" },
  });
  check(health, {
    "readiness status is ok": (response) =>
      response.status === 200 && response.json("status") === "ok",
    "readiness exposes worker state": (response) =>
      response.status === 200 && response.json("components.induction_workers") !== undefined,
  });
}

export default function () {
  const live = http.get(`${BASE_URL}/api/v1/live`, {
    tags: { endpoint: "live" },
  });
  check(live, {
    "liveness status is ok": (response) =>
      response.status === 200 && response.json("status") === "ok",
  });

  const metrics = http.get(`${BASE_URL}/metrics`, {
    tags: { endpoint: "metrics" },
  });
  check(metrics, {
    "metrics endpoint is prometheus text": (response) =>
      response.status === 200 &&
      response.headers["Content-Type"] &&
      response.headers["Content-Type"].includes("text/plain"),
    "reasoning metrics are exposed": (response) =>
      response.status === 200 && response.body.includes("inferra_abduction_total"),
  });

  const goal = postJson(
    "/api/v1/reasoning/goal",
    {
      user_query: "Can I claim this benefit?",
      rule_name: "benefit_rule",
      enabled: false,
    },
    "goal_disabled",
  );
  check(goal, {
    "disabled goal mapping falls back": (response) =>
      response.status === 200 && response.json("fallback") === true,
  });

  const abduct = postJson(
    "/api/v1/reasoning/abduct",
    {
      target: "goal",
      working_memory: { known: true },
      graph_snapshot: {
        child_groups: {
          goal: [[1, ["known", "missing"]]],
        },
      },
      enabled: true,
    },
    "abduct",
  );
  check(abduct, {
    "abduction returns missing fact hypothesis": (response) => {
      if (response.status !== 200) {
        return false;
      }
      const hypotheses = response.json("hypotheses");
      return (
        Array.isArray(hypotheses) &&
        hypotheses.length > 0 &&
        hypotheses[0].fact_name === "missing"
      );
    },
  });

  const induction = postJson(
    "/api/v1/reasoning/induce/start",
    {
      session_ids: ["smoke-session"],
      rule_name: "smoke_rule",
      enabled: false,
    },
    "induce_disabled",
  );
  check(induction, {
    "disabled induction returns stub": (response) =>
      response.status === 200 && response.json("status") === "disabled",
  });

  sleep(1);
}
