import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const PROFILE = (__ENV.PROFILE || "smoke").toLowerCase();
const JSON_HEADERS = { headers: { "Content-Type": "application/json" } };

const profiles = {
  smoke: {
    vus: Number(__ENV.VUS || 1),
    duration: __ENV.DURATION || "30s",
  },
  load: {
    scenarios: {
      steady_load: {
        executor: "constant-vus",
        vus: Number(__ENV.VUS || 100),
        duration: __ENV.DURATION || "3m",
      },
    },
  },
  stress: {
    stages: [
      { duration: "1m", target: Number(__ENV.RAMP_VUS || 100) },
      { duration: "3m", target: Number(__ENV.VUS || 300) },
      { duration: "1m", target: 0 },
    ],
  },
  spike: {
    stages: [
      { duration: "30s", target: Number(__ENV.RAMP_VUS || 50) },
      { duration: "30s", target: Number(__ENV.VUS || 500) },
      { duration: "1m", target: 0 },
    ],
  },
  soak: {
    scenarios: {
      soak: {
        executor: "constant-vus",
        vus: Number(__ENV.VUS || 50),
        duration: __ENV.DURATION || "30m",
      },
    },
  },
};

export const options = {
  ...(profiles[PROFILE] || profiles.smoke),
  thresholds: {
    http_req_failed: ["rate<0.05"],
    "http_req_duration{endpoint:live}": ["p(95)<300", "p(99)<750"],
    "http_req_duration{endpoint:metrics}": ["p(95)<500", "p(99)<1000"],
    "http_req_duration{endpoint:abduct}": ["p(95)<1000", "p(99)<2000"],
    "http_req_duration{endpoint:induce_disabled}": ["p(95)<500", "p(99)<1000"],
    checks: ["rate>0.95"],
  },
};

function postJson(path, payload, endpoint) {
  return http.post(`${BASE_URL}${path}`, JSON.stringify(payload), {
    headers: JSON_HEADERS.headers,
    tags: { endpoint },
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
    "abduction returns hypothesis list": (response) =>
      response.status === 200 && Array.isArray(response.json("hypotheses")),
  });

  const induction = postJson(
    "/api/v1/reasoning/induce/start",
    {
      session_ids: [`${PROFILE}-session`],
      rule_name: `${PROFILE}_rule`,
      enabled: false,
    },
    "induce_disabled",
  );
  check(induction, {
    "disabled induction returns stub": (response) =>
      response.status === 200 && response.json("status") === "disabled",
  });

  sleep(Number(__ENV.USER_SLEEP_SECONDS || 1));
}

