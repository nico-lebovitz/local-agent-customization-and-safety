/* Display only: all values come from the selected execution record. */
function traceRows(events) {
  return events.map((event, index) => {
    const end = Math.max(0, Number(event.elapsed_s) || 0);
    const duration =
      event.kind === "model"
        ? Math.max(0, Number(event.data.latency_s) || 0)
        : 0;
    return { event, index, end, start: Math.max(0, end - duration), duration };
  });
}
let traceRun = null;
let selectedEvent = 0;
function clearTrace() {
  traceRun = null;
  document.getElementById("trace-explorer").hidden = true;
  document.getElementById("trace-stats").textContent =
    "Waiting for execution events…";
  document.getElementById("raw-events").textContent = "No events yet.";
}
function eventSummary(event) {
  const d = event.data;
  if (event.kind === "model")
    return (
      d.model +
      " · " +
      d.purpose +
      " · " +
      d.latency_s +
      "s · " +
      (d.usage?.total_tokens ?? "unreported") +
      " tokens"
    );
  if (event.kind === "routing") return d.route + " → " + d.expected_model;
  if (event.kind === "validation")
    return d.gate.valid
      ? "Validation passed → " + d.gate.destination
      : "HOLD · " + d.gate.errors.join("; ");
  return (
    d.reason ||
    d.error ||
    d.tool ||
    d.source ||
    d.result?.disposition ||
    event.name
  );
}
function inspectEvent(index) {
  selectedEvent = index;
  const event = traceRun.events[index];
  if (!event) return;
  document.getElementById("event-kind").textContent =
    event.kind.toUpperCase() + " / " + event.elapsed_s.toFixed(3) + "s";
  document.getElementById("event-title").textContent = event.name;
  document.getElementById("event-summary").textContent = eventSummary(event);
  document.getElementById("event-data").textContent = JSON.stringify(
    event.data,
    null,
    2,
  );
  document.querySelectorAll("[data-event-index]").forEach((button) => {
    const active = Number(button.dataset.eventIndex) === index;
    button.classList.toggle("selected", active);
    button.setAttribute("aria-pressed", String(active));
  });
}
function renderTrace(run) {
  const changed = traceRun?.id !== run.id;
  traceRun = run;
  if (changed) selectedEvent = 0;
  const byId = (id) => document.getElementById(id);
  const el = (tag, value, cls) => {
    const n = document.createElement(tag);
    n.textContent = value;
    if (cls) n.className = cls;
    return n;
  };
  const rows = traceRows(run.events);
  const total = Math.max(0, ...rows.map((r) => r.end));
  const scale = Math.max(total, 0.001);
  const calls = rows.filter((r) => r.event.kind === "model");
  const stats = byId("trace-stats");
  stats.replaceChildren();
  const metrics = [
    [
      total.toFixed(2) + "s",
      run.status === "running" ? "Elapsed so far" : "Recorded duration",
    ],
    [String(calls.length), "Model calls"],
    [
      String(
        calls.reduce((n, r) => n + (r.event.data.usage?.total_tokens || 0), 0),
      ),
      "Reported tokens",
    ],
    [String(run.relay_events.length), "Relay events"],
  ];
  metrics.forEach(([value, label]) => {
    const card = el("div", "", "trace-metric");
    card.append(el("strong", value), el("span", label));
    stats.append(card);
  });
  byId("trace-explorer").hidden = false;
  byId("trace-duration").textContent = "0 → " + total.toFixed(2) + "s";
  const decisions = byId("decision-strip");
  decisions.replaceChildren();
  rows
    .filter((r) => r.event.kind === "decision")
    .forEach((row) => {
      const b = el("button", "", "decision-node");
      b.dataset.eventIndex = row.index;
      b.append(
        el("span", "STEP " + row.event.data.step),
        el("strong", row.event.data.action),
        el("small", row.end.toFixed(2) + "s"),
      );
      b.onclick = () => inspectEvent(row.index);
      decisions.append(b);
    });
  if (!decisions.children.length)
    decisions.append(
      el("p", "Waiting for a recorded controller choice.", "caption"),
    );
  const filter = byId("trace-filter").value;
  const timeline = byId("timeline");
  const focused = timeline.contains(document.activeElement)
    ? document.activeElement.dataset.eventIndex
    : null;
  timeline.replaceChildren();
  rows
    .filter(
      (r) =>
        filter === "all" ||
        (filter === "validation"
          ? ["validation", "review", "error"].includes(r.event.kind)
          : r.event.kind === filter),
    )
    .forEach((row) => {
      const { event, index, start, end, duration } = row;
      const li = el("li", "");
      const button = el("button", "", "waterfall-row kind-" + event.kind);
      button.dataset.eventIndex = index;
      if (event.kind === "model" && event.data.model === "specialist")
        button.classList.add("model-specialist");
      button.setAttribute(
        "aria-label",
        event.name +
          ", " +
          eventSummary(event) +
          ", at " +
          end.toFixed(3) +
          " seconds",
      );
      const label = el("span", "", "waterfall-label");
      label.append(
        el(
          "strong",
          event.kind === "model"
            ? event.data.model + " / " + event.data.purpose
            : event.data.tool || event.name,
        ),
        el("small", event.kind),
      );
      const track = el("span", "", "waterfall-track");
      const mark = el("span", "", duration ? "duration-bar" : "event-dot");
      mark.style.left = Math.min(start / scale, 0.99) * 100 + "%";
      if (duration)
        mark.style.width = Math.min(duration / scale, 1) * 100 + "%";
      track.append(mark);
      button.append(
        label,
        track,
        el("span", (duration || end).toFixed(2) + "s", "waterfall-time"),
      );
      button.title = duration
        ? "Call duration: " + duration.toFixed(3) + "s"
        : "Event at " + end.toFixed(3) + "s";
      button.onclick = () => inspectEvent(index);
      li.append(button);
      timeline.append(li);
    });
  if (!timeline.children.length)
    timeline.append(el("li", "No matching events in this run.", "caption"));
  inspectEvent(Math.min(selectedEvent, run.events.length - 1));
  if (focused !== null)
    timeline
      .querySelector('[data-event-index="' + focused + '"]')
      ?.focus({ preventScroll: true });
}
document.getElementById("trace-filter").addEventListener("change", () => {
  if (traceRun) renderTrace(traceRun);
});
