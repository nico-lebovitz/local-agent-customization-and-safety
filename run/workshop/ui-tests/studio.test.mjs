import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { Window } from "happy-dom";
import * as model from "../static/studio-model.mjs";
const json = async (path) =>
  JSON.parse(await readFile(new URL(path, import.meta.url), "utf8"));
const [initial, constrained, training] = await Promise.all([
  json("../eval/baseline-initial.json"),
  json("../eval/baseline-constrained.json"),
  json("../gym/artifacts/demo.json"),
]);
const records = {};
for (const baseline of [initial, constrained])
  for (const row of baseline.results)
    records[row.run_id] = await json("../eval/records/" + row.run_id + ".json");
const goodId = constrained.results.find(
  (r) => r.episode === "report-market",
).run_id;
const html = await readFile(
  new URL("../static/index.html", import.meta.url),
  "utf8",
);
const script = (
  await readFile(new URL("../static/studio.js", import.meta.url), "utf8")
).replace(
  /^import[\s\S]*?;\n/,
  "const {TASKS,eventSummary,routeAt,trainingFrame,sampledAttempt,linkedRelay,toolSequence}=globalThis.model;\n",
);
async function settled() {
  for (let i = 0; i < 12; i++) await new Promise((r) => setImmediate(r));
}
async function setup({ offline = false, failReplay = false } = {}) {
  const w = new Window({
    url: "http://localhost:7861",
    settings: {
      disableCSSFileLoading: true,
      disableJavaScriptFileLoading: true,
    },
  });
  w.document.write(html);
  w.model = model;
  w.HTMLElement.prototype.scrollIntoView = function () {};
  w.HTMLElement.prototype.scrollTo = function () {};
  w.IntersectionObserver = class {
    observe() {}
  };
  const timers = new Map();
  let timerId = 0;
  w.setInterval = (callback) => {
    timers.set(++timerId, callback);
    return timerId;
  };
  w.clearInterval = (id) => timers.delete(id);
  w.setTimeout = (callback) => {
    queueMicrotask(callback);
    return 1;
  };
  const calls = [];
  w.fetch = async (url, options) => {
    calls.push({ url, options });
    let body;
    if (url === "/api/info")
      body = {
        clips: {
          "civil-market": "Civilian market",
          "sample-drone-bridge": "Bridge overflight",
        },
        baselines: [initial, constrained],
        scores: [],
        versions: { "nemo-relay": "0.9.4" },
      };
    else if (url === "/api/health")
      body = { lightning: { ready: !offline }, active_run: null };
    else if (url === "/api/training-demo") body = training;
    else if (url === "/api/runs") body = { id: goodId };
    else if (url.startsWith("/api/runs/")) {
      if (failReplay)
        return {
          ok: false,
          status: 404,
          json: async () => ({ detail: "Recorded run missing" }),
        };
      body = records[url.split("/").at(-1)];
    } else throw Error("Unexpected request: " + url);
    return { ok: true, json: async () => structuredClone(body) };
  };
  w.eval(script + "\nwindow.testState = state;");
  await settled();
  return {
    w,
    $: (id) => w.document.getElementById(id),
    calls,
    timers,
    close: () => w.happyDOM.abort(),
  };
}
test("selectors, scene selection and task instructions initialize", async () => {
  const h = await setup();
  try {
    const ids = [...h.w.document.querySelectorAll("[id]")].map((e) => e.id);
    assert.equal(new Set(ids).size, ids.length);
    assert.equal(h.w.document.querySelectorAll(".scenario").length, 2);
    h.w.document.querySelector('[data-clip="sample-drone-bridge"]').click();
    assert.match(h.$("scene-video").src, /sample-drone-bridge/);
    assert.match(h.$("vss-video").src, /sample-drone-bridge/);
    assert.match(h.$("vss-video").poster, /sample-drone-bridge/);
    assert.match(h.$("vss-clip-label").textContent, /BRIDGE OVERFLIGHT/);
    h.$("vss-components").children[3].click();
    assert.doesNotMatch(h.$("vss-example").textContent, /market stalls/);
    assert.doesNotMatch(h.$("vss-overlay").textContent, /Market stalls/);
    h.w.document.querySelector('[data-task="triage"]').click();
    assert.equal(h.$("task-text").value, model.TASKS.triage);
    assert.equal(h.$("specialist-node").getAttribute("aria-pressed"), "true");
    assert.equal(h.$("run").disabled, false);
  } finally {
    await h.close();
  }
});
test("recorded failure replay exposes error and real Relay evidence", async () => {
  const h = await setup();
  try {
    h.$("inspect-failure").click();
    await settled();
    assert.match(h.$("run-mode").textContent, /RECORDED/);
    const r = h.w.testState.run;
    const index = r.events.findIndex((e) => e.name === "Tool failed");
    h.$("trace-step").value = index;
    h.$("trace-step").dispatchEvent(new h.w.Event("input"));
    assert.match(
      h.$("event-summary").textContent,
      /Perceive the observation before triage/,
    );
    assert.match(h.$("event-json").textContent, /related_relay_records/);
    assert.equal(
      h.$("trace-position").textContent,
      `${index + 1} / ${r.events.length}`,
    );
    assert.match(h.$("outcome-title").textContent, /Held/);
    assert.equal(h.calls.filter((c) => c.options?.method === "POST").length, 0);
  } finally {
    await h.close();
  }
});
test("live task sends selected inputs and follows the latest event", async () => {
  const h = await setup();
  try {
    h.w.document.querySelector('[data-task="draft"]').click();
    h.$("run").click();
    await settled();
    const request = h.calls.find((c) => c.options?.method === "POST");
    assert.deepEqual(JSON.parse(request.options.body), {
      task: model.TASKS.draft,
      clip: "civil-market",
      perception: "recorded",
    });
    assert.match(h.$("run-mode").textContent, /LIVE EXECUTION/);
    assert.equal(h.w.testState.selected, h.w.testState.run.events.length - 1);
    assert.equal(h.$("download").hidden, false);
    assert.equal(h.$("run").disabled, false);
    assert.match(h.$("outcome-title").textContent, /Draft ready/);
  } finally {
    await h.close();
  }
});
test("training scrubber, intent and sample toggles use recorded values", async () => {
  const h = await setup();
  try {
    h.$("training-step").value = "40";
    h.$("training-step").dispatchEvent(new h.w.Event("input"));
    assert.equal(
      h.$("reward-value").textContent,
      training.after.expected_reward.toFixed(3),
    );
    const index = training.intents.indexOf("draft");
    assert.equal(
      h.w.document.querySelectorAll(".probability strong")[2].textContent,
      (training.after.probabilities[index][2] * 100).toFixed(1) + "%",
    );
    h.$("training-intent").value = "triage";
    h.$("training-intent").dispatchEvent(new h.w.Event("change"));
    h.$("training-step").value = "1";
    h.$("training-step").dispatchEvent(new h.w.Event("input"));
    h.$("rejected").click();
    assert.equal(JSON.parse(h.$("sample-json").textContent).reward, 0);
    h.$("training-reset").click();
    assert.equal(h.$("training-position").textContent, "Step 0 / 40");
    assert.equal(h.$("sample-json").textContent, "null");
    assert.equal(h.calls.filter((c) => c.options?.method === "POST").length, 0);
  } finally {
    await h.close();
  }
});
test("offline models keep live run disabled but recorded exploration available", async () => {
  const h = await setup({ offline: true });
  try {
    assert.equal(h.$("run").disabled, true);
    assert.equal(h.$("inspect-failure").disabled, false);
    h.$("inspect-success").click();
    await settled();
    assert.equal(h.$("run").disabled, true);
    assert.match(h.$("run-mode").textContent, /RECORDED/);
  } finally {
    await h.close();
  }
});
test("record fetch errors are visible and unavailable comparisons stay disabled", async () => {
  const h = await setup({ failReplay: true });
  try {
    assert.match(h.$("failure-reason").textContent, /unavailable/);
    assert.equal(h.$("inspect-failure").disabled, true);
    h.$("saved-run").value = goodId;
    h.$("saved-run").dispatchEvent(new h.w.Event("change"));
    h.$("load-run").click();
    await settled();
    assert.match(h.$("run-status").textContent, /Recorded run missing/);
    assert.equal(h.$("inspect-failure").disabled, true);
  } finally {
    await h.close();
  }
});
test("actual data supports base/specialist routing and bounded training steps", () => {
  const run = records[goodId];
  const specialist = run.events.findIndex(
    (e) => e.kind === "routing" && e.data.expected_model === "specialist",
  );
  assert.equal(model.routeAt(run.events, specialist).model, "specialist");
  assert.equal(model.routeAt(run.events, 0), null);
  assert.equal(model.trainingFrame(training, 999, "draft").step, 40);
  assert.equal(model.trainingFrame(training, -1, "draft").step, 0);
  assert.throws(() => model.trainingFrame(training, 1, "unsupported"));
});
test("playback controls advance, pause, and stop at the final update", async () => {
  const h = await setup();
  try {
    h.$("training-play").click();
    assert.match(h.$("training-play").textContent, /Pause/);
    const trainingTimer = [...h.timers.keys()].at(-1);
    for (let i = 0; i < 40; i++) h.timers.get(trainingTimer)?.();
    assert.equal(h.$("training-position").textContent, "Step 40 / 40");
    assert.match(h.$("training-play").textContent, /Play/);
    h.$("inspect-success").click();
    await settled();
    h.$("trace-play").click();
    const traceTimer = [...h.timers.keys()].at(-1);
    h.timers.get(traceTimer)();
    assert.equal(h.w.testState.selected, 1);
    h.$("trace-play").click();
    assert.equal(h.timers.has(traceTimer), false);
  } finally {
    await h.close();
  }
});

test("VSS walkthrough explores components without executing and explains source selection", async () => {
  const h = await setup();
  try {
    const cards = h.$("vss-components").children;
    assert.equal(cards.length, 5);
    cards[3].click();
    assert.equal(h.$("vss-title").textContent, "Cosmos");
    assert.equal(cards[3].getAttribute("aria-pressed"), "true");
    h.$("vss-step").value = 4;
    h.$("vss-step").dispatchEvent(new h.w.Event("input"));
    assert.match(h.$("vss-description").textContent, /observation-1/);
    assert.match(h.$("vss-source-detail").textContent, /are not called/);
    h.$("vss-source-link").click();
    assert.equal(h.$("perception").closest("details").open, true);
    h.$("perception").value = "live";
    h.$("perception").dispatchEvent(new h.w.Event("change"));
    assert.match(h.$("vss-source-detail").textContent, /does not start it/);
    await settled();
    assert.equal(h.$("run").disabled, true);
    assert.match(h.$("vss-connection").textContent, /offline/);
    h.$("perception").value = "recorded";
    h.$("perception").dispatchEvent(new h.w.Event("change"));
    await settled();
    assert.equal(h.$("run").disabled, false);
    assert.match(h.$("vss-video").src, /api\/clips\/civil-market/);
    assert.equal(h.calls.filter((c) => c.options?.method === "POST").length, 0);
  } finally {
    await h.close();
  }
});

test("VSS playback pauses, finishes, and resets its visual handoff", async () => {
  const h = await setup();
  try {
    const tick = () => [...h.timers.values()].forEach((callback) => callback());
    h.$("vss-play").click();
    tick();
    assert.equal(h.$("vss-stage").dataset.step, "1");
    assert.match(h.$("vss-output").textContent, /plan/);
    h.$("vss-play").click();
    tick();
    assert.equal(h.$("vss-step").value, "1");
    h.$("vss-play").click();
    tick();
    tick();
    tick();
    assert.equal(h.$("vss-stage").dataset.step, "4");
    assert.equal(h.$("vss-play").getAttribute("aria-pressed"), "false");
    assert.equal(h.$("vss-next").disabled, true);
    assert.match(h.$("vss-output").textContent, /observation-1/);
    h.$("vss-reset").click();
    assert.equal(h.$("vss-step").value, "0");
    assert.equal(h.$("vss-back").disabled, true);
    assert.equal(h.calls.filter((c) => c.options?.method === "POST").length, 0);
  } finally {
    await h.close();
  }
});

test("tool shelf follows recorded choices and browsing does not change execution", async () => {
  const h = await setup();
  try {
    assert.equal(h.$("tool-shelf").children.length, 4);
    h.$("inspect-failure").click();
    await settled();
    const events = h.w.testState.run.events;
    const i = events.findIndex((e) => e.kind === "decision");
    assert.ok(i >= 0);
    h.$("trace-step").value = i;
    h.$("trace-step").dispatchEvent(new h.w.Event("input"));
    assert.match(
      h.$("tool-choice-title").textContent,
      new RegExp(events[i].data.action),
    );
    assert.ok(
      h.$("tool-choice-reason").textContent.includes(events[i].data.reason),
    );
    const picked = h.w.document.querySelector("#tool-shelf .agent-picked");
    assert.equal(picked.dataset.tool, events[i].data.action);
    h.w.document.querySelector('#tool-shelf [data-tool="draft"]').click();
    assert.equal(h.$("tool-info-title").textContent, "Draft");
    assert.equal(
      h.w.document.querySelector("#tool-shelf .agent-picked"),
      picked,
    );
    h.$("trace-step").value = 0;
    h.$("trace-step").dispatchEvent(new h.w.Event("input"));
    assert.equal(h.w.document.querySelector("#tool-shelf .agent-picked"), null);
    assert.match(h.$("tool-evidence-state").textContent, /not read yet/);
    assert.equal(h.calls.filter((c) => c.options?.method === "POST").length, 0);
  } finally {
    await h.close();
  }
});
