export const TASKS = {
  describe:
    "Describe the selected scene. Read the observation and summarize what is visible. Do not classify or draft a report.",
  triage:
    "Read the selected observation, then classify it with the specialist. Return the validated classification without drafting a report.",
  draft:
    "Read the selected observation, classify it with the specialist, then prepare a short factual draft report for human review.",
};
export function eventSummary(event) {
  const d = event.data || {};
  if (event.kind === "routing")
    return `${d.route} → ${d.expected_model}. ${d.policy || "Explicit task route"}.`;
  if (event.kind === "model")
    return `${d.model} answered the ${d.purpose} request in ${Number(d.latency_s).toFixed(2)}s. ${d.usage?.total_tokens ?? "Unreported"} total tokens.`;
  if (event.kind === "validation")
    return d.gate?.valid
      ? `Checks passed. Destination: ${d.gate.destination}.`
      : `Held for review: ${(d.gate?.errors || []).join("; ")}`;
  if (event.kind === "evidence")
    return `${d.source || "Observation"}: ${d.description || ""}`;
  if (event.kind === "report")
    return "A draft was prepared for human review. It has not been released.";
  return (
    d.error ||
    d.reason ||
    d.tool ||
    d.result?.reason ||
    d.result?.disposition ||
    event.name
  );
}
export function routeAt(events, index) {
  for (let i = index; i >= 0; i--) {
    const e = events[i],
      d = e.data || {};
    if (e.kind === "routing")
      return { model: d.expected_model, route: d.route, purpose: d.purpose };
    if (e.kind === "model")
      return { model: d.model, route: d.route, purpose: d.purpose };
  }
  return null;
}
export function trainingFrame(training, step, intent) {
  const index = training.intents.indexOf(intent);
  if (index < 0) throw new Error("Unknown training intent");
  const n = Math.max(
    0,
    Math.min(training.steps.length, Math.round(Number(step) || 0)),
  );
  const state = n ? training.steps[n - 1] : training.before;
  return {
    step: n,
    reward: state.expected_reward,
    probabilities: state.probabilities[index],
  };
}
export function sampledAttempt(training, step, intent, reward) {
  return (
    training.sample_rollouts.find(
      (r) => r.step === step && r.intent === intent && r.reward === reward,
    ) || null
  );
}
export function linkedRelay(run, event) {
  // These are related records, not a claim of a one-to-one event mapping.
  return (run.relay_events || []).filter(
    (e) =>
      e.name === event.name ||
      (event.kind === "tool" &&
        (e.name === event.data?.tool || e.data?.tool === event.data?.tool)) ||
      (event.kind === "model" &&
        e.name === "switchyard" &&
        e.data?.model === event.data?.model),
  );
}
export function toolSequence(run) {
  return (run.events || [])
    .filter((e) => e.kind === "tool")
    .map((e) => e.data.tool);
}
