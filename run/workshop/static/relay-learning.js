// Connect independently captured evidence; do not imply logs were training inputs.
(async () => {
  const id = "dddb5bc4073b4d649ce1a1719abacd69";
  const el = (id) => document.getElementById(id);
  try {
    const fetchJson = async (url) => {
      const r = await fetch(url);
      if (!r.ok) throw Error("Record unavailable: " + r.status);
      return r.json();
    };
    const [run, training] = await Promise.all([
      fetchJson("/api/runs/" + id),
      fetchJson("/api/training-demo"),
    ]);
    const firstTool = run.events.find((e) => e.kind === "tool");
    const failure = run.relay_events.find(
      (e) => e.name === "Tool failed" && e.data?.tool === "triage",
    );
    const sample = training.sample_rollouts.find(
      (r) =>
        r.intent === "triage" &&
        r.plan_id === "skip_evidence" &&
        r.reward === 0,
    );
    const intent = training.intents.indexOf("triage"),
      action = training.actions.findIndex((a) => a.id === "skip_evidence");
    if (
      firstTool?.data.tool !== "triage" ||
      !failure ||
      !sample ||
      intent < 0 ||
      action < 0
    )
      throw Error("The linked evidence does not match the example");
    el("relay-failure").textContent =
      "First tool: " +
      firstTool.data.tool +
      " at " +
      firstTool.elapsed_s.toFixed(3) +
      "s\n" +
      failure.data.error;
    el("relay-gym-example").textContent =
      "Step " +
      sample.step +
      " · intent: " +
      sample.intent +
      "\nPlan: " +
      training.actions[action].label +
      "\nReward: " +
      sample.reward +
      " · advantage: " +
      sample.advantage.toFixed(3) +
      "\n" +
      sample.failures.join("\n");
    const before = training.before.probabilities[intent][action],
      after = training.after.probabilities[intent][action];
    el("relay-policy-impact").textContent =
      "In the teaching policy, probability of skipping evidence for a triage task: " +
      (before * 100).toFixed(2) +
      "% → " +
      (after * 100).toFixed(2) +
      "% after " +
      training.optimizer_steps +
      " updates. This is the finite teaching environment; the production controller is unchanged.";
    el("relay-learning-provenance").textContent = JSON.stringify(
      {
        mapping:
          "Observed failure pattern → existing verifier rule → separately sampled training example",
        relay: {
          run_id: run.id,
          event_uuid: failure.uuid,
          timestamp: failure.timestamp,
          error: failure.data.error,
        },
        verifier: {
          source: "gym/resources.py",
          rule: "triage requires observed evidence",
          reward_source: "Gym /verify",
        },
        training: {
          step: sample.step,
          sample: sample.sample,
          intent: sample.intent,
          plan_id: sample.plan_id,
          reward: sample.reward,
          advantage: sample.advantage,
          checkpoint: training.after.checkpoint.sha256,
          relay_logs_used_as_training_input: false,
        },
      },
      null,
      2,
    );
    const traceButton = el("relay-source-trace");
    traceButton.disabled = false;
    traceButton.addEventListener("click", async () => {
      const replay = el("replay");
      if (replay.disabled || ![...replay.options].some((o) => o.value === id))
        return;
      replay.value = id;
      await replay.onchange();
      el("observe").scrollIntoView({ behavior: "smooth" });
    });
    const trainingButton = el("relay-training-example");
    // The training component enables this when its own controls have loaded.
    const enable = () => {
      trainingButton.disabled = el("training-content").hidden;
    };
    enable();
    document.addEventListener("training-ready", enable, { once: true });
    trainingButton.addEventListener("click", () => {
      el("training-intent").value = String(intent);
      const frame = training.steps.findIndex((s) => s.step === sample.step) + 1;
      el("training-step").value = frame;
      el("training-step").dispatchEvent(new Event("input"));
      el("training-demo").scrollIntoView({ behavior: "smooth" });
    });
  } catch (error) {
    el("relay-policy-impact").textContent =
      "Could not load the evidence mapping: " + error.message;
  }
})();
