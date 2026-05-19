import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const USER_VUS = Number(__ENV.VUS || 500);
const DURATION = __ENV.DURATION || "1m";
const METRICS_RATE = Number(__ENV.METRICS_RATE || 4);
const LIVE_RATE = Number(__ENV.LIVE_RATE || 12);
const USER_SLEEP_SECONDS = Number(__ENV.USER_SLEEP_SECONDS || 3);
const JSON_HEADERS = { headers: { "Content-Type": "application/json" } };

export const options = {
  scenarios: {
    user_sessions: {
      executor: "constant-vus",
      vus: USER_VUS,
      duration: DURATION,
      exec: "userSession",
    },
    metrics_scrape: {
      executor: "constant-arrival-rate",
      rate: METRICS_RATE,
      timeUnit: "1m",
      duration: DURATION,
      preAllocatedVUs: 1,
      maxVUs: 5,
      exec: "metricsScrape",
    },
    liveness_probe: {
      executor: "constant-arrival-rate",
      rate: LIVE_RATE,
      timeUnit: "1m",
      duration: DURATION,
      preAllocatedVUs: 1,
      maxVUs: 5,
      exec: "livenessProbe",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.05"],
    "http_req_duration{endpoint:live}": ["p(95)<300", "p(99)<750"],
    "http_req_duration{endpoint:metrics}": ["med<100", "p(99)<1000"],
    "http_req_duration{endpoint:goal_disabled}": ["p(95)<500", "p(99)<1000"],
    "http_req_duration{endpoint:abduct}": ["p(95)<1000", "p(99)<2000"],
    "http_req_duration{endpoint:induce_disabled}": ["p(95)<500", "p(99)<1000"],
    "http_req_duration{endpoint:readiness}": ["p(95)<7000"],
    checks: ["rate>0.95"],
  },
};

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

export function userSession() {
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
      session_ids: ["load-session"],
      rule_name: "load_rule",
      enabled: false,
    },
    "induce_disabled",
  );
  check(induction, {
    "disabled induction returns stub": (response) =>
      response.status === 200 && response.json("status") === "disabled",
  });

  sleep(USER_SLEEP_SECONDS);
}

export function livenessProbe() {
  const live = http.get(`${BASE_URL}/api/v1/live`, {
    tags: { endpoint: "live" },
  });
  check(live, {
    "liveness status is ok": (response) =>
      response.status === 200 && response.json("status") === "ok",
  });
}

export function metricsScrape() {
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
}
