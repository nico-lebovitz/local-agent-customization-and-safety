// Replay a captured CPU teaching experiment; this page never starts training.
(() => {
  const el = (id) => document.getElementById(id);
  const node = (tag, value, cls) => {
    const n = document.createElement(tag);
    n.textContent = value;
    if (cls) n.className = cls;
    return n;
  };
  let artifact,
    frames = [],
    timer = null;
  const stop = () => {
    clearInterval(timer);
    timer = null;
    el("training-play").textContent = "Replay training";
  };
  const svgNode = (tag, attrs, value) => {
    const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, String(v)));
    if (value !== undefined) n.textContent = value;
    return n;
  };
  function chart(index) {
    const svg = svgNode("svg", {
      viewBox: "0 0 520 285",
      role: "img",
      "aria-label":
        "Expected and sampled reward over the captured training run. Selected optimizer step " +
        frames[index].step,
    });
    const x = (step) => 45 + (step / artifact.optimizer_steps) * 445,
      y = (reward) => 225 - Math.max(0, Math.min(1, reward)) * 180;
    [0, 0.5, 1].forEach((r) => {
      svg.append(
        svgNode("line", {
          x1: 45,
          y1: y(r),
          x2: 490,
          y2: y(r),
          stroke: "#35453e",
        }),
        svgNode(
          "text",
          {
            x: 30,
            y: y(r) + 4,
            fill: "#a0ada8",
            "font-size": 11,
            "text-anchor": "end",
          },
          r.toFixed(1),
        ),
      );
    });
    [0, 10, 20, 30, 40]
      .filter((s) => s <= artifact.optimizer_steps)
      .forEach((s) =>
        svg.append(
          svgNode(
            "text",
            {
              x: x(s),
              y: 246,
              fill: "#a0ada8",
              "font-size": 11,
              "text-anchor": "middle",
            },
            s,
          ),
        ),
      );
    const line = (data, color, key) =>
      svgNode("polyline", {
        points: data.map((d) => x(d.step) + "," + y(d[key])).join(" "),
        fill: "none",
        stroke: color,
        "stroke-width": 2,
      });
    svg.append(
      line(artifact.steps, "#88c9f1", "mean_reward"),
      line(frames, "#b8eb59", "expected_reward"),
    );
    const f = frames[index];
    svg.append(
      svgNode("line", {
        x1: x(f.step),
        y1: 40,
        x2: x(f.step),
        y2: 225,
        stroke: "#dce8d7",
        "stroke-dasharray": "4 4",
      }),
      svgNode("circle", {
        cx: x(f.step),
        cy: y(f.expected_reward),
        r: 5,
        fill: "#b8eb59",
      }),
    );
    svg.append(
      svgNode(
        "text",
        { x: 45, y: 273, fill: "#b8eb59", "font-size": 11 },
        "Expected reward",
      ),
      svgNode(
        "text",
        { x: 190, y: 273, fill: "#88c9f1", "font-size": 11 },
        "Sampled reward",
      ),
      svgNode(
        "text",
        {
          x: 490,
          y: 273,
          fill: "#a0ada8",
          "font-size": 11,
          "text-anchor": "end",
        },
        "Optimizer step",
      ),
    );
    el("reward-chart").replaceChildren(svg);
  }
  function render() {
    const index = Number(el("training-step").value),
      frame = frames[index];
    el("training-step-label").textContent =
      frame.step + " / " + artifact.optimizer_steps;
    const metrics = [
      [String(artifact.parameters), "Trainable parameters"],
      [artifact.before.expected_reward.toFixed(3), "Starting expected reward"],
      [frame.expected_reward.toFixed(3), "Expected reward at selected step"],
      [
        artifact.rollout_count.toLocaleString(),
        "Total sampled plans in this run",
      ],
    ];
    el("training-metrics").replaceChildren(
      ...metrics.map(([value, label]) => {
        const d = node("div", "");
        d.append(node("strong", value), node("span", label));
        return d;
      }),
    );
    chart(index);
    const intent = Number(el("training-intent").value),
      probs = el("policy-probabilities");
    probs.replaceChildren();
    artifact.actions.forEach((action, i) => {
      const row = node("div", "", "probability-row"),
        label = node("div", "", "probability-label");
      label.append(
        node("span", action.label),
        node("span", (frame.probabilities[intent][i] * 100).toFixed(1) + "%"),
      );
      const track = node("div", "", "probability-track"),
        before = node("span", "", "probability-start"),
        current = node("span", "", "probability-current");
      before.style.width = artifact.before.probabilities[intent][i] * 100 + "%";
      current.style.width = frame.probabilities[intent][i] * 100 + "%";
      track.append(current, before);
      row.append(label, track);
      probs.append(row);
    });
    const captured = [
      ...new Set(artifact.sample_rollouts.map((r) => r.step)),
    ].sort((a, b) => a - b);
    const sampleStep =
      captured.filter((s) => s <= frame.step).at(-1) ?? captured[0];
    el("rollout-step").textContent = "CAPTURED SAMPLES · STEP " + sampleStep;
    el("training-rollouts").replaceChildren(
      ...artifact.sample_rollouts
        .filter((r) => r.step === sampleStep)
        .slice(0, 9)
        .map((r) => {
          const row = node("tr", "");
          const action = artifact.actions.find((a) => a.id === r.plan_id);
          [
            r.intent,
            action?.label || r.plan_id,
            r.reward.toFixed(1),
            r.failures.length
              ? r.failures.join("; ")
              : "Required tool sequence satisfied",
          ].forEach((v, i) =>
            row.append(
              node(
                "td",
                v,
                i === 2 ? (r.reward ? "reward-pass" : "reward-fail") : "",
              ),
            ),
          );
          return row;
        }),
    );
  }
  async function initTraining() {
    try {
      const response = await fetch("/api/training-demo");
      if (!response.ok)
        throw Error(
          "Experiment record unavailable (HTTP " + response.status + ")",
        );
      artifact = await response.json();
      if (
        !artifact.steps?.length ||
        !artifact.before?.probabilities ||
        !artifact.sample_rollouts?.length
      )
        throw Error("Experiment record is incomplete");
      frames = [
        {
          step: 0,
          expected_reward: artifact.before.expected_reward,
          probabilities: artifact.before.probabilities,
        },
        ...artifact.steps,
      ];
      el("training-intent").replaceChildren(
        ...artifact.intents.map((intent, i) => {
          const o = node("option", intent);
          o.value = i;
          return o;
        }),
      );
      el("training-step").max = frames.length - 1;
      el("training-step").value = frames.length - 1;
      el("training-content").hidden = false;
      el("training-badge").textContent = "RECORDED CPU TRAINING";
      el("training-status").textContent =
        artifact.parameters +
        "-parameter teaching controller · " +
        artifact.optimizer_steps +
        " optimizer updates · actual weight update: " +
        artifact.weight_update +
        ". Lightning and the production agent are unchanged.";
      el("training-scope").textContent =
        "This experiment uses a real NeMo Gym verifier and pinned NeMo RL loss functions on a tiny categorical policy. It scores fixed tool plans without executing VSS or Lightning. Rewards describe this teaching environment, not held-out agent performance. The slider replays captured results; it does not retrain a model.";
      el("training-provenance").textContent = JSON.stringify(
        {
          created_at: artifact.created_at,
          seed: artifact.seed,
          gym_version: artifact.gym_version,
          torch_version: artifact.torch_version,
          device: artifact.device,
          gym_transport: artifact.gym_transport,
          rl_source: artifact.rl_source,
          optimizer: artifact.optimizer,
          learning_rate: artifact.learning_rate,
          group_size: artifact.group_size,
          checkpoint: artifact.checkpoint,
          weight_update: artifact.weight_update,
          production_weights_changed: artifact.production_weights_changed,
          full_nemo_rl_trainer: artifact.full_nemo_rl_trainer,
          limitations: artifact.limitations,
        },
        null,
        2,
      );
      render();
      document.dispatchEvent(new Event("training-ready"));
    } catch (error) {
      el("training-badge").textContent = "RECORD UNAVAILABLE";
      el("training-status").textContent = error.message;
    }
  }
  el("training-step").addEventListener("input", () => {
    stop();
    render();
  });
  el("training-intent").addEventListener("change", () => {
    if (artifact) render();
  });
  el("training-play").addEventListener("click", () => {
    if (timer) {
      stop();
      return;
    }
    if (Number(el("training-step").value) >= frames.length - 1)
      el("training-step").value = 0;
    el("training-play").textContent = "Pause replay";
    render();
    timer = setInterval(() => {
      const next = Number(el("training-step").value) + 1;
      if (next >= frames.length) {
        stop();
        return;
      }
      el("training-step").value = next;
      render();
    }, 240);
  });
  el("training-download").addEventListener("click", () => {
    const a = document.createElement("a");
    a.href = "/api/training-demo/download";
    a.download = "gym-rl-teaching-demo.json";
    a.click();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stop();
  });
  initTraining();
})();
