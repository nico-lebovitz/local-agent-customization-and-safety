const $ = (id) => document.getElementById(id);
const text = (tag, value, cls) => {
  const e = document.createElement(tag);
  e.textContent = value;
  if (cls) e.className = cls;
  return e;
};
function setBusy(busy) {
  [
    "run",
    "replay",
    "trace-replay",
    "relay-source-trace",
    "clip",
    "task",
    "perception",
  ].forEach((id) => ($(id).disabled = busy));
  document
    .querySelectorAll("[data-task]")
    .forEach((button) => (button.disabled = busy));
}
let runId = null,
  polling = false;
async function get(url, options) {
  const r = await fetch(url, options);
  if (!r.ok) {
    let d;
    try {
      d = await r.json();
    } catch {}
    throw new Error(d?.detail || "HTTP " + r.status);
  }
  return r.json();
}
function video() {
  $("video").src = "/api/clips/" + encodeURIComponent($("clip").value);
}
async function init() {
  try {
    const info = await get("/api/info");
    Object.entries(info.clips).forEach(([id, label]) => {
      const o = text("option", label);
      o.value = id;
      $("clip").append(o);
    });
    video();
    info.baselines.forEach((b, i) => {
      b.results.forEach((r) => {
        const o = text(
          "option",
          (i ? "After constraints" : "Initial controller") +
            " · " +
            r.episode +
            " · " +
            (r.success ? "completed" : "failed"),
        );
        o.value = r.run_id;
        $("trace-replay").append(o.cloneNode(true));
        $("replay").append(o);
      });
    });
    $("agent-baseline").textContent = info.baselines
      .map(
        (b, i) =>
          (i ? "After action constraints: " : "Initial controller: ") +
          b.successes +
          "/" +
          b.episodes +
          " workflow contracts passed",
      )
      .join(" → ");
    info.scores.forEach((s) => {
      const row = document.createElement("tr");
      if (s.label === "Specialist" && s.prompt === "Rules only")
        row.className = "best";
      [
        s.label,
        s.prompt + " / " + s.precision,
        (s.weighted * 100).toFixed(1) + "%",
        s.exact + "/" + s.n,
        s.failures["U1-overclaim"] + " / " + s.failures["U2-civil-misroute"],
      ].forEach((v) => row.append(text("td", v)));
      $("score-body").append(row);
    });
    const best = info.scores[1];
    [
      ["70 MB", "Existing Lightning LoRA adapter"],
      [(best.weighted * 100).toFixed(1) + "%", "Weighted field accuracy"],
      [best.exact + "/" + best.n, "All four fields correct"],
    ].forEach(([v, l]) => {
      const card = text("div", "", "metric");
      card.append(text("strong", v), text("span", l));
      $("metrics").append(card);
    });
    $("sources").textContent = info.scores.map((s) => s.source).join("\n");
    $("versions").textContent = Object.entries(info.versions)
      .map(([k, v]) => k + " " + v)
      .join(" · ");
  } catch (e) {
    $("health").textContent = "Workshop API unavailable";
    $("run-status").textContent = e.message;
  }
}
async function health() {
  try {
    const h = await get("/api/health");
    $("health").textContent = h.lightning.ready
      ? "● LIGHTNING ONLINE · LOCAL"
      : "○ LIGHTNING OFFLINE";
    $("health").style.color = h.lightning.ready
      ? "var(--green)"
      : "var(--gold)";
  } catch {
    $("health").textContent = "○ WORKSHOP OFFLINE";
  }
}
$("clip").addEventListener("change", video);
document.querySelectorAll("[data-task]").forEach(
  (b) =>
    (b.onclick = () => {
      $("task").value = b.dataset.task;
      document
        .querySelectorAll("[data-task]")
        .forEach((x) => x.classList.toggle("selected", x === b));
    }),
);
function render(run) {
  renderCapabilities(run);
  if ($("clip").value !== run.clip) {
    $("clip").value = run.clip;
    video();
  }
  $("task").value = run.task;
  $("perception").value = run.perception;
  $("run-output").hidden = false;
  $("run-badge").textContent = run.status.toUpperCase();
  $("evidence-source").textContent = run.evidence.source || "";
  $("description").textContent =
    run.evidence.description || "Waiting for perception…";
  $("item").textContent = run.item
    ? JSON.stringify(run.item, null, 2)
    : "No specialist output yet.";
  const g = run.gate;
  $("gate").textContent = g
    ? g.valid
      ? "Validated → " +
        g.destination +
        (g.routing_overridden ? " · model routing overridden by table" : "")
      : "HOLD · " + g.errors.join("; ")
    : "Not evaluated";
  $("gate").classList.toggle("hold", Boolean(g && !g.valid));
  $("report").textContent =
    run.report ||
    (run.result?.disposition === "HOLD"
      ? "Held for review. No report issued."
      : "No report drafted.");
  renderTrace(run);
  $("raw-events").textContent = JSON.stringify(run.relay_events, null, 2);
  $("run-status").textContent = run.error
    ? "Held: " + run.error
    : run.status === "running"
      ? "Running · " + (run.events.at(-1)?.name || "Starting NAT workflow")
      : "Complete · " + run.result?.disposition + " · no report released";
  if (run.status !== "running") {
    $("download").hidden = false;
    $("download").href = "/api/runs/" + run.id + "/download";
  }
}
async function poll() {
  if (polling) return;
  polling = true;
  try {
    const r = await get("/api/runs/" + runId);
    render(r);
    if (r.status === "running") setTimeout(poll, 750);
    else {
      setBusy(false);
    }
  } catch (e) {
    $("run-status").textContent = "Could not read run: " + e.message;
    setBusy(false);
  } finally {
    polling = false;
  }
}
$("run").onclick = async () => {
  setBusy(true);
  $("run-output").hidden = true;
  clearTrace();
  $("replay").value = "";
  $("trace-replay").value = "";
  $("trace-mode").textContent = "LIVE EXECUTION";
  $("playback-note").textContent =
    "Live execution: recorded perception (if selected) still calls the agent and specialist.";
  $("download").hidden = true;
  $("run-status").textContent = "Starting NAT workflow…";
  try {
    const r = await get("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        task: $("task").value,
        clip: $("clip").value,
        perception: $("perception").value,
      }),
    });
    runId = r.id;
    await poll();
  } catch (e) {
    $("run-status").textContent = e.message;
    setBusy(false);
  }
};
init();
health();
setInterval(health, 30000);

$("replay").onchange = async () => {
  const id = $("replay").value;
  if (!id) return;
  try {
    const r = await get("/api/runs/" + id);
    render(r);
    $("run-badge").textContent = "RECORDED EXECUTION";
    $("trace-mode").textContent = "RECORDED EXECUTION";
    $("trace-replay").value = id;
    $("run-status").textContent =
      "Viewing a saved run · no model calls made now";
    $("playback-note").textContent =
      "Recorded run " +
      id +
      " · original model calls and timings, replayed without inference.";
  } catch (e) {
    $("playback-note").textContent = e.message;
  }
};

// Native dialogs provide modal focus containment and Escape handling.
document.querySelectorAll("[data-dialog]").forEach((trigger) => {
  trigger.addEventListener("click", () => {
    const dialog = $(trigger.dataset.dialog);
    dialog.showModal();
    document.body.classList.add("dialog-open");
    dialog.scrollTop = 0;
    dialog.addEventListener(
      "close",
      () => {
        document.body.classList.remove("dialog-open");
        trigger.focus();
      },
      { once: true },
    );
  });
});
document.querySelectorAll(".learning-dialog").forEach((dialog) => {
  dialog
    .querySelector(".dialog-close")
    .addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target !== dialog) return;
    const box = dialog.getBoundingClientRect();
    if (
      event.clientX < box.left ||
      event.clientX > box.right ||
      event.clientY < box.top ||
      event.clientY > box.bottom
    )
      dialog.close();
  });
});

$("trace-replay").addEventListener("change", () => {
  $("replay").value = $("trace-replay").value;
  $("replay").onchange();
});
