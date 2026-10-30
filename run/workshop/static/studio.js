import {
  TASKS,
  eventSummary,
  routeAt,
  trainingFrame,
  sampledAttempt,
  linkedRelay,
  toolSequence,
} from "./studio-model.mjs";
const $ = (id) => document.getElementById(id);
const el = (tag, value, cls) => {
  const n = document.createElement(tag);
  n.textContent = value;
  if (cls) n.className = cls;
  return n;
};
const state = {
  clip: "civil-market",
  task: "describe",
  run: null,
  selected: 0,
  busy: false,
  live: false,
  training: null,
  step: 0,
  reward: 1,
  traceTimer: null,
  trainTimer: null,
  modelReady: false,
  vssReady: false,
  comparisonReady: false,
};
async function get(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : `Request failed (${response.status})`,
    );
  }
  return response.json();
}
function json(id, value) {
  $(id).textContent = JSON.stringify(value, null, 2);
}
function pressed(button, yes) {
  button.setAttribute("aria-pressed", String(yes));
  button.classList.toggle("selected", yes);
}
function busy(yes) {
  state.busy = yes;
  document
    .querySelectorAll(
      ".scenario, [data-task], #task-text, #perception, #saved-run",
    )
    .forEach((b) => (b.disabled = yes));
  $("run").disabled =
    yes ||
    !state.modelReady ||
    ($("perception").value === "live" && !state.vssReady);
  for (const id of ["inspect-failure", "inspect-success"])
    $(id).disabled = yes || !state.comparisonReady;
  $("run").textContent = yes ? "Agent is working…" : "Run the agent ↗";
  $("load-run").disabled = yes || !$("saved-run").value;
}
function stopTrace() {
  clearInterval(state.traceTimer);
  state.traceTimer = null;
  $("trace-play").textContent = "▶ Play trace";
}
function stopTraining() {
  clearInterval(state.trainTimer);
  state.trainTimer = null;
  $("training-play").textContent = "▶ Play updates";
}
function chooseTask(task) {
  state.task = task;
  $("task-text").value = TASKS[task];
  document
    .querySelectorAll("[data-task]")
    .forEach((b) => pressed(b, b.dataset.task === task));
  if (!state.run) showRoute(task === "triage" ? "specialist" : "base");
}
function chooseScene(clip, label) {
  state.clip = clip;
  document
    .querySelectorAll(".scenario")
    .forEach((b) => pressed(b, b.dataset.clip === clip));
  $("scene-video").src = "/api/clips/" + encodeURIComponent(clip);
  $("scene-video").poster =
    "/static/posters/" + encodeURIComponent(clip) + ".jpg";
  $("scene-label").textContent = label;
  $("vss-video").pause();
  $("vss-video").src = $("scene-video").src;
  $("vss-video").poster = $("scene-video").poster;
  $("vss-video").setAttribute("aria-label", `VSS walkthrough video: ${label}`);
  $("vss-clip-label").textContent = `SELECTED CLIP · ${label.toUpperCase()}`;
  stopVss();
  selectVssStep(0);
  $("video-error").hidden = true;
}
$("scene-video").addEventListener("error", () => {
  $("video-error").hidden = false;
});
document
  .querySelectorAll("[data-task]")
  .forEach((b) => (b.onclick = () => chooseTask(b.dataset.task)));
function showRoute(model, recorded = null) {
  const specialist = model === "specialist";
  $("route-map").dataset.route = specialist ? "specialist" : "base";
  pressed($("base-node"), !specialist);
  pressed($("specialist-node"), specialist);
  $("route-caption").textContent = recorded
    ? `Actual route · ${recorded.purpose || "model call"}`
    : "Explicit task routes · preview";
  $("route-detail").textContent = recorded
    ? `${recorded.route} → ${model}. Model choice recorded in this execution.`
    : specialist
      ? "workshop-triage → specialist. Classifies the observation using the existing LoRA adapter."
      : "workshop-reason → base. Chooses tools and writes summaries. Switchyard uses the requested task route.";
}
$("base-node").onclick = () => showRoute("base");
$("specialist-node").onclick = () => showRoute("specialist");
function selectEvent(index, scroll = true) {
  if (!state.run?.events.length) return;
  state.selected = Math.max(
    0,
    Math.min(state.run.events.length - 1, Number(index)),
  );
  const event = state.run.events[state.selected];
  renderToolChoice(state.run.events.slice(0, state.selected + 1));
  $("trace-step").value = state.selected;
  $("trace-position").textContent =
    `${state.selected + 1} / ${state.run.events.length}`;
  $("event-kind").textContent =
    `${event.kind.toUpperCase()} / ${Number(event.elapsed_s).toFixed(3)}s FROM START`;
  $("event-title").textContent = event.name;
  $("event-summary").textContent = eventSummary(event);
  json("event-json", {
    application_event: event,
    related_relay_records: linkedRelay(state.run, event),
  });
  document
    .querySelectorAll(".event-card")
    .forEach((b, i) => pressed(b, i === state.selected));
  if (scroll) {
    const b = $("timeline").children[state.selected];
    if (b)
      $("timeline").scrollTo({
        left: Math.max(0, b.offsetLeft - $("timeline").offsetLeft - 15),
        behavior: "smooth",
      });
  }
  const route = routeAt(state.run.events, state.selected);
  if (route) showRoute(route.model, route);
  else showRoute("base");
}
function renderOutcome(run) {
  $("outcome-fields").replaceChildren();
  const hold =
    run.result?.disposition === "HOLD" ||
    run.status === "failed" ||
    run.status === "cancelled";
  $("outcome-title").textContent =
    run.status === "running"
      ? "Work in progress"
      : hold
        ? "Held for review"
        : run.report
          ? "Draft ready for review"
          : run.item
            ? "Observation classified"
            : "Observation collected";
  for (const [key, value] of Object.entries(run.item || {}))
    $("outcome-fields").append(
      el("span", `${key.replaceAll("_", " ")}: ${value}`),
    );
  if (run.gate)
    $("outcome-fields").append(
      el(
        "span",
        run.gate.valid
          ? `Rule checks passed → ${run.gate.destination}`
          : "Rule checks rejected the classification",
      ),
    );
  const result = run.result || {};
  $("outcome-text").textContent =
    run.report ||
    run.error ||
    (hold
      ? result.reason
        ? "Agent’s review reason: " + result.reason
        : "No report released."
      : run.evidence?.description || "Waiting for an observation…");
  json("run-json", run);
}
function renderRun(run, { live = false, reset = false } = {}) {
  const old = state.run;
  const followEnd =
    reset ||
    !old ||
    !old.events.length ||
    state.selected === old.events.length - 1;
  state.run = run;
  state.live = live;
  $("run-mode").textContent = live
    ? "LIVE EXECUTION · LOCAL MODELS"
    : "RECORDED EXECUTION · PLAYBACK";
  $("run-mode").classList.toggle("blue", !live);
  $("run-status").textContent =
    `${run.status.toUpperCase()} · ${run.clip} · ${run.events.length} events${live ? "" : " · no inference now"}`;
  $("route-map").classList.toggle("running", live && run.status === "running");
  $("trace-count").textContent =
    `${run.events.length} application events · ${run.relay_events?.length || 0} Relay records · ${Number(run.events.at(-1)?.elapsed_s || 0).toFixed(2)}s original elapsed time`;
  $("timeline").replaceChildren();
  if (!run.events.length) {
    renderToolChoice([]);
    $("event-kind").textContent = "WAITING FOR EVENTS";
    $("event-title").textContent = "Starting the agent";
    $("event-summary").textContent = "The first decision will appear shortly.";
    $("trace-position").textContent = "0 / 0";
    $("event-json").textContent = "No event yet.";
    showRoute("base");
    $("route-caption").textContent = "Waiting for the first model call";
  }
  run.events.forEach((event, index) => {
    const failed =
      event.kind === "error" ||
      /fail/i.test(event.name) ||
      (event.kind === "validation" && !event.data?.gate?.valid);
    const button = el("button", "", "event-card" + (failed ? " error" : ""));
    button.append(
      el(
        "small",
        `${String(index + 1).padStart(2, "0")} / ${event.kind.toUpperCase()}`,
      ),
      el("strong", event.name),
      el("span", `${Number(event.elapsed_s).toFixed(2)}s`),
    );
    button.onclick = () => {
      stopTrace();
      selectEvent(index);
    };
    $("timeline").append(button);
  });
  $("trace-step").max = Math.max(0, run.events.length - 1);
  $("trace-step").disabled = !run.events.length;
  $("trace-play").disabled =
    !run.events.length || (live && run.status === "running");
  $("trace-end").disabled = !run.events.length;
  selectEvent(
    reset ? 0 : followEnd ? run.events.length - 1 : state.selected,
    false,
  );
  renderOutcome(run);
  $("download").hidden = run.status === "running";
  $("download").href = "/api/runs/" + run.id + "/download";
}
$("trace-step").oninput = (e) => {
  stopTrace();
  selectEvent(e.target.value);
};
$("trace-end").onclick = () => {
  stopTrace();
  selectEvent(state.run.events.length - 1);
};
$("trace-play").onclick = () => {
  if (state.traceTimer) return stopTrace();
  if (state.selected >= state.run.events.length - 1) selectEvent(0);
  $("trace-play").textContent = "Ⅱ Pause trace";
  state.traceTimer = setInterval(() => {
    selectEvent(state.selected + 1);
    if (state.selected >= state.run.events.length - 1) stopTrace();
  }, 650);
};
async function loadRun(id) {
  stopTrace();
  busy(true);
  try {
    const run = await get("/api/runs/" + encodeURIComponent(id));
    renderRun(run, { reset: true });
    $("follow").scrollIntoView();
  } catch (e) {
    $("run-status").textContent = e.message;
  } finally {
    busy(false);
  }
}
$("saved-run").onchange = () => {
  $("load-run").disabled = state.busy || !$("saved-run").value;
};
$("load-run").onclick = () => loadRun($("saved-run").value);
$("run").onclick = async () => {
  const task = $("task-text").value.trim();
  if (task.length < 5) {
    $("launch-message").textContent =
      "Enter a task of at least five characters.";
    return;
  }
  stopTrace();
  busy(true);
  $("download").hidden = true;
  $("launch-message").textContent = "Starting a real agent run…";
  try {
    const created = await get("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        task,
        clip: state.clip,
        perception: $("perception").value,
      }),
    });
    $("launch-message").textContent =
      "Started. Follow the live execution below.";
    $("follow").scrollIntoView();
    // Clear the previous result immediately; never present a replay as the new live run.
    renderRun(
      {
        id: created.id,
        clip: state.clip,
        status: "running",
        events: [],
        relay_events: [],
        evidence: {},
      },
      { live: true, reset: true },
    );
    let run;
    do {
      run = await get("/api/runs/" + created.id);
      renderRun(run, { live: true });
      if (run.status === "running")
        await new Promise((resolve) => setTimeout(resolve, 700));
    } while (run.status === "running");
    $("launch-message").textContent =
      run.status === "complete"
        ? run.result?.disposition === "HOLD"
          ? `Held for review: ${run.result.reason || "inspect the trace"}`
          : "Run complete. Inspect the steps and result below."
        : `Run ${run.status}: ${run.error || run.result?.reason || "inspect the trace"}`;
  } catch (e) {
    $("launch-message").textContent = e.message;
    $("run-status").textContent = `Live run unavailable: ${e.message}`;
    $("route-map").classList.remove("running");
  } finally {
    busy(false);
  }
};
function sequence(container, tools, bad = null) {
  container.replaceChildren();
  tools.forEach((tool, i) => {
    if (i) container.append(el("i", "→"));
    container.append(el("span", tool, tool === bad ? "bad" : ""));
  });
}
async function failures(info) {
  const badId = info.baselines[0].results.find(
    (r) => r.episode === "triage-market" && !r.success,
  )?.run_id;
  const goodId = info.baselines[1].results.find(
    (r) => r.episode === "triage-market" && r.success,
  )?.run_id;
  if (!badId || !goodId)
    throw new Error("The comparison records are unavailable.");
  const [bad, good] = await Promise.all([
    get("/api/runs/" + badId),
    get("/api/runs/" + goodId),
  ]);
  sequence($("bad-sequence"), toolSequence(bad), "triage");
  sequence($("good-sequence"), toolSequence(good));
  const failure = bad.relay_events.find(
    (e) => e.name === "Tool failed" && e.data?.tool === "triage",
  );
  $("failure-reason").textContent =
    failure?.data?.error ||
    bad.error ||
    "Inspect the trace for the rejected action.";
  state.comparisonReady = true;
  $("inspect-failure").disabled = state.busy;
  $("inspect-success").disabled = state.busy;
  $("inspect-failure").onclick = () => loadRun(badId);
  $("inspect-success").onclick = () => loadRun(goodId);
}
function renderTraining() {
  const t = state.training;
  const intent = $("training-intent").value;
  const frame = trainingFrame(t, state.step, intent);
  state.step = frame.step;
  $("training-step").value = frame.step;
  $("training-position").textContent = `Step ${frame.step} / ${t.steps.length}`;
  $("reward-value").textContent = frame.reward.toFixed(3);
  const points = [
    t.before.expected_reward,
    ...t.steps.map((s) => s.expected_reward),
  ];
  const x = (n) => 40 + (n / t.steps.length) * 540,
    y = (r) => 190 - r * 170;
  const line = points
    .map((r, i) => `${i ? "L" : "M"}${x(i)},${y(r)}`)
    .join(" ");
  $("reward-line").setAttribute("d", line);
  $("reward-area").setAttribute("d", line + " L580,190 L40,190 Z");
  $("chart-cursor").setAttribute("x1", x(frame.step));
  $("chart-cursor").setAttribute("x2", x(frame.step));
  $("chart-dot").setAttribute("cx", x(frame.step));
  $("chart-dot").setAttribute("cy", y(frame.reward));
  $("reward-chart").setAttribute(
    "aria-label",
    `Recorded expected reward at step ${frame.step}: ${frame.reward.toFixed(3)}. The full curve shows ${t.steps.length} updates.`,
  );
  $("probabilities").replaceChildren();
  t.actions.forEach((action, index) => {
    const row = el(
      "div",
      "",
      "probability" + (action.id === "skip_evidence" ? " bad" : ""),
    );
    const heading = el("div", "");
    heading.append(
      el("span", action.label),
      el("strong", (frame.probabilities[index] * 100).toFixed(1) + "%"),
    );
    const track = el("div", "", "bar"),
      fill = el("div", "");
    fill.style.width = frame.probabilities[index] * 100 + "%";
    track.append(fill);
    row.append(heading, track);
    $("probabilities").append(row);
  });
  const sample = sampledAttempt(t, frame.step, intent, state.reward);
  if (sample) {
    sequence(
      $("sample-sequence"),
      sample.transitions.map((s) => s.tool),
      sample.transitions.find((s) => !s.allowed)?.tool,
    );
    $("sample-detail").textContent =
      `Reward ${sample.reward} · advantage ${sample.advantage.toFixed(3)}. ${sample.failures.length ? sample.failures.join("; ") : "The sampled plan satisfies the task contract."}`;
    json("sample-json", sample);
  } else {
    $("sample-sequence").replaceChildren();
    $("sample-detail").textContent = frame.step
      ? `No ${state.reward ? "rewarded" : "rejected"} attempt was captured for this intent at step ${frame.step}. Try another update.`
      : "Initial policy: all four plans are equally likely. Move the slider to see fresh sampled attempts.";
    json("sample-json", null);
  }
}
$("training-step").oninput = (e) => {
  stopTraining();
  state.step = Number(e.target.value);
  renderTraining();
};
$("training-intent").onchange = () => {
  if (state.training) renderTraining();
};
$("training-reset").onclick = () => {
  stopTraining();
  state.step = 0;
  renderTraining();
};
$("training-play").onclick = () => {
  if (state.trainTimer) return stopTraining();
  if (state.step === state.training.steps.length) state.step = 0;
  $("training-play").textContent = "Ⅱ Pause updates";
  state.trainTimer = setInterval(() => {
    state.step++;
    renderTraining();
    if (state.step >= state.training.steps.length) stopTraining();
  }, 250);
};
for (const [id, reward] of [
  ["rewarded", 1],
  ["rejected", 0],
])
  $(id).onclick = () => {
    state.reward = reward;
    pressed($("rewarded"), !!reward);
    pressed($("rejected"), !reward);
    if (state.training) renderTraining();
  };
async function training() {
  try {
    const t = await get("/api/training-demo");
    state.training = t;
    $("training-step").max = t.steps.length;
    for (const id of ["training-step", "training-play", "training-reset"])
      $(id).disabled = false;
    $("training-details").textContent =
      `${t.parameters} CPU parameters · ${t.optimizer_steps} updates · ${t.rollout_count.toLocaleString()} fresh sampled attempts · NeMo Gym ${t.gym_version}. NeMo RL loss functions drive the update; this is not the full distributed trainer. Recorded ${t.created_at}. Viewing this page does not start training.`;
    renderTraining();
  } catch (e) {
    $("training-error").textContent =
      "Training playback unavailable: " + e.message;
  }
}
async function health() {
  try {
    const h = await get("/api/health");
    state.modelReady = h.lightning.ready;
    state.vssReady = h.vss_perception?.ready === true;
    $("vss-connection").textContent = state.vssReady
      ? "VSS API connected · model inference is checked when you run a task."
      : "VSS API offline · live perception is unavailable. Recorded descriptions still work.";
    $("health").textContent = h.lightning.ready
      ? "● LOCAL MODELS ONLINE"
      : "○ LOCAL MODELS OFFLINE";
    $("run").disabled =
      state.busy ||
      !state.modelReady ||
      ($("perception").value === "live" && !state.vssReady);
    if (h.active_run && !state.busy)
      $("launch-message").textContent =
        "Another run is active. Wait for it to finish before starting a new task.";
  } catch {
    state.modelReady = false;
    $("health").textContent = "○ WORKSHOP UNAVAILABLE";
    $("run").disabled = true;
  }
}
async function init() {
  chooseTask("describe");
  try {
    const info = await get("/api/info");
    for (const [id, label] of Object.entries(info.clips)) {
      const b = el("button", "", "scenario");
      b.dataset.clip = id;
      b.setAttribute("aria-label", "Select " + label);
      const img = document.createElement("img");
      img.src = "/static/posters/" + id + ".jpg";
      img.alt = "";
      img.loading = "lazy";
      img.onerror = () => {
        img.removeAttribute("src");
        img.style.visibility = "hidden";
      };
      b.append(img, el("strong", label));
      b.onclick = () => chooseScene(id, label);
      $("scenarios").append(b);
    }
    chooseScene(state.clip, info.clips[state.clip]);
    info.baselines.forEach((baseline, i) =>
      baseline.results.forEach((r) => {
        const option = el(
          "option",
          `${i ? "Constrained" : "Initial"} · ${r.episode} · ${r.success ? "passed" : "failed"}`,
        );
        option.value = r.run_id;
        $("saved-run").append(option);
      }),
    );
    for (const score of info.scores) {
      const card = el("div", "");
      card.append(
        el("small", `${score.label} · ${score.prompt}`),
        el("strong", (score.weighted * 100).toFixed(1) + "%"),
        el("small", `Weighted field accuracy · ${score.precision}`),
      );
      $("adapter-scores").append(card);
    }
    $("versions").textContent = Object.entries(info.versions)
      .map(([k, v]) => `${k} ${v}`)
      .join(" · ");
    await failures(info);
  } catch (e) {
    $("launch-message").textContent = e.message;
    $("failure-reason").textContent = "Comparison unavailable: " + e.message;
  }
}
const observer = new IntersectionObserver(
  (entries) => {
    for (const entry of entries)
      if (entry.isIntersecting)
        document
          .querySelectorAll(".journey a")
          .forEach((a) =>
            a.classList.toggle("active", a.hash === "#" + entry.target.id),
          );
  },
  { rootMargin: "-15% 0px -60% 0px", threshold: 0 },
);
document
  .querySelectorAll(".chapter")
  .forEach((section) => observer.observe(section));
window.addEventListener(
  "scroll",
  () => {
    const max = document.documentElement.scrollHeight - window.innerHeight;
    $("scroll-progress").style.width =
      (max > 0 ? (window.scrollY / max) * 100 : 0) + "%";
  },
  { passive: true },
);
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    stopTrace();
    stopTraining();
  }
});
init();
training();
health();
setInterval(health, 30000);

const vssSteps = [
  [
    "Request",
    "Ask about a clip",
    "QUESTION",
    "The workshop’s perceive tool asks VSS to describe the selected video. In live mode, this goes to the VSS /generate endpoint.",
    "Describe the people, vehicles, structures, and activity in this clip.",
  ],
  [
    "VSS agent",
    "Plan · Nano",
    "NEMOTRON NANO · LANGUAGE MODEL",
    "The VSS agent chooses the video tools needed to answer the question. This is a separate agent from the workshop agent that classifies the observation.",
    "Find the clip, then use video_understanding to describe it.",
  ],
  [
    "Video tools",
    "Retrieve · VST",
    "VIDEO STORAGE TOOLKIT",
    "VST provides the video list, clips, and snapshots. The video-understanding tool uses a clip URL to access the footage.",
    "vst_video_list → choose a clip → vst_video_clip",
  ],
  [
    "Cosmos",
    "See · vision model",
    "COSMOS REASON2 · VISION LANGUAGE MODEL",
    "The video-understanding tool sends video frames to Cosmos. Cosmos describes what is visible; it does not apply the workshop’s specialist classification rules.",
    "A description of the visible scene is returned here. This illustration does not show a live model response.",
  ],
  [
    "Observation",
    "Hand back evidence",
    "VSS → WORKSHOP AGENT",
    "VSS returns a description. The workshop records it with the clip identity as observation-1. The agent can then summarize it, ask the specialist to classify it, or prepare a draft.",
    "Video description → observation-1 → specialist classification",
  ],
];
let vssTimer = null;
const vssVisuals = [
  [
    "✉",
    "Question + clip name",
    "Ask VSS",
    "Request to describe the selected clip",
    ["What is happening here?"],
  ],
  [
    "↗",
    "Request to describe the selected clip",
    "Nano chooses tools",
    "A plan to inspect the clip",
    ["1 · Find video", "2 · Inspect frames", "3 · Describe scene"],
  ],
  [
    "▣",
    "Clip identity",
    "VST retrieves footage",
    "Video frames for analysis",
    ["Video list", "Clip URL", "Frames → Cosmos"],
  ],
  [
    "◎",
    "Video frames + question",
    "Cosmos interprets the scene",
    "A description of visible activity",
    ["Inspect frames", "Describe visible activity"],
  ],
  [
    "≡",
    "VSS description + clip identity",
    "Workshop packages evidence",
    "observation-1 · ready for the agent",
    ["observation-1", "Source: VSS", "Ready for classification"],
  ],
];
function stopVss() {
  clearInterval(vssTimer);
  vssTimer = null;
  $("vss-play").textContent = "▶ Play walkthrough";
  $("vss-play").setAttribute("aria-pressed", "false");
}
function selectVssStep(index) {
  const step = vssSteps[index];
  const visual = vssVisuals[index];
  $("vss-components").style.setProperty(
    "--vss-position",
    `${10 + index * 20}%`,
  );
  $("vss-stage").dataset.step = index;
  $("vss-input").textContent = visual[1];
  $("vss-action").textContent = visual[2];
  $("vss-output").textContent = visual[3];
  $("vss-overlay").replaceChildren(
    ...visual[4].map((label) => el("span", label)),
  );
  $("vss-back").disabled = index === 0;
  $("vss-next").disabled = index === vssSteps.length - 1;
  $("vss-components").style.setProperty("--vss-progress", `${index * 25}%`);
  $("vss-step").value = index;
  $("vss-position").textContent = `${index + 1} / ${vssSteps.length}`;
  $("vss-role").textContent = step[2];
  $("vss-title").textContent = step[0];
  $("vss-description").textContent = step[3];
  $("vss-example").textContent = step[4];
  [...$("vss-components").children].forEach((button, i) =>
    button.setAttribute("aria-pressed", String(i === index)),
  );
}
vssSteps.forEach((step, index) => {
  const button = el("button");
  button.append(
    el("span", vssVisuals[index][0], "vss-icon"),
    el("strong", step[0]),
    el("small", step[1]),
  );
  button.onclick = () => {
    stopVss();
    selectVssStep(index);
  };
  $("vss-components").append(button);
});
$("vss-step").addEventListener("input", (event) => {
  stopVss();
  selectVssStep(Number(event.target.value));
});
function showVssSource() {
  const live = $("perception").value === "live";
  $("vss-source-title").textContent = live
    ? "Selected: live VSS"
    : "Selected: recorded description";
  $("vss-source-detail").textContent = live
    ? "The next run will request a fresh description from VSS. This requires the live VSS stack to be running; selecting this option does not start it."
    : "The next run reads a saved VSS description and starts at the observation handoff. Nano, VST, and Cosmos are not called. The workshop agent and its model calls still run live.";
}
$("perception").addEventListener("change", () => {
  showVssSource();
  busy(state.busy);
  $("launch-message").textContent =
    $("perception").value === "live" && !state.vssReady
      ? "Live VSS is offline on port 8000. Select recorded descriptions to run now."
      : "Click Run the agent to use this source. Step 02 remains an illustrated example.";
  health();
});
$("vss-source-link").addEventListener("click", () => {
  $("perception").closest("details").open = true;
});
selectVssStep(0);
showVssSource();

$("vss-play").setAttribute("aria-pressed", "false");
$("vss-play").onclick = () => {
  if (vssTimer !== null) {
    stopVss();
    return;
  }
  if (Number($("vss-step").value) === 4) selectVssStep(0);
  $("vss-play").textContent = "Ⅱ Pause";
  $("vss-play").setAttribute("aria-pressed", "true");
  vssTimer = setInterval(() => {
    const next = Number($("vss-step").value) + 1;
    selectVssStep(Math.min(next, 4));
    if (next >= 4) stopVss();
  }, 2600);
};
$("vss-back").onclick = () => {
  stopVss();
  selectVssStep(Math.max(0, Number($("vss-step").value) - 1));
};
$("vss-next").onclick = () => {
  stopVss();
  selectVssStep(Math.min(4, Number($("vss-step").value) + 1));
};
$("vss-reset").onclick = () => {
  stopVss();
  selectVssStep(0);
};
document.addEventListener("visibilitychange", () => {
  if (document.hidden) stopVss();
});

const toolCatalog = [
  {
    id: "perceive",
    icon: "◎",
    name: "Perceive",
    verb: "Read the scene",
    description:
      "Fetch a fresh VSS description or read the saved description selected for this run.",
    input:
      "Selected clip and observation source. Offered before evidence is read.",
    output: "Observation text, clip identity, and source.",
  },
  {
    id: "triage",
    icon: "◇",
    name: "Triage",
    verb: "Ask the specialist",
    description:
      "Call the specialist, then check its classification against the workflow rules.",
    input: "An observation must already exist.",
    output: "Classification, validation result, and destination.",
  },
  {
    id: "draft",
    icon: "≡",
    name: "Draft",
    verb: "Prepare a report",
    description:
      "Use the base model to write a factual draft with the validated fields.",
    input: "A specialist result that passed validation.",
    output: "A draft report for human review. Nothing is released.",
  },
  {
    id: "request_review",
    icon: "✋",
    name: "Request review",
    verb: "Stop and hold",
    description:
      "Hold the task when evidence is insufficient or a check fails.",
    input: "The agent’s short explanation of why review is needed.",
    output: "A HOLD result and the review reason.",
  },
];
function exploreTool(id) {
  const tool = toolCatalog.find((t) => t.id === id);
  $("tool-info-title").textContent = tool.name;
  $("tool-info-description").textContent = tool.description;
  $("tool-info-input").textContent = tool.input;
  $("tool-info-output").textContent = tool.output;
  [...$("tool-shelf").children].forEach((button) =>
    button.setAttribute("aria-pressed", String(button.dataset.tool === id)),
  );
}
function renderToolChoice(events) {
  const choice = [...events].reverse().find((e) => e.kind === "decision");
  const action = choice?.data?.action;
  document.querySelectorAll("#tool-shelf button").forEach((button) => {
    const selected = button.dataset.tool === action;
    button.classList.toggle("agent-picked", selected);
    button.querySelector(".tool-picked").textContent = selected
      ? "↳ AGENT CHOSE THIS"
      : "CALLABLE TOOL";
  });
  $("tool-choice-title").textContent = action
    ? `Agent → ${action === "finish" ? "Finish (controller action)" : action}`
    : "Waiting for an agent decision";
  $("tool-choice-reason").textContent = choice
    ? `Recorded explanation: ${choice.data.reason || "No explanation recorded."}`
    : "Run a task or load a saved execution, then scrub the timeline.";
  const evidence = events.some((e) => e.kind === "evidence");
  const gate = [...events].reverse().find((e) => e.kind === "validation");
  const report = events.some((e) => e.kind === "report");
  $("tool-evidence-state").textContent =
    `Evidence: ${evidence ? "read" : "not read yet"} · Checks: ${gate ? (gate.data.gate?.valid ? "passed" : "failed") : "not run"} · Draft: ${report ? "prepared" : "not prepared"}`;
}
for (const tool of toolCatalog) {
  const button = el("button", "");
  button.dataset.tool = tool.id;
  button.append(
    el("span", tool.icon, "tool-icon"),
    el("strong", tool.name),
    el("small", tool.verb),
    el("span", "CALLABLE TOOL", "tool-picked"),
  );
  button.onclick = () => exploreTool(tool.id);
  $("tool-shelf").append(button);
}
exploreTool("perceive");
renderToolChoice([]);
