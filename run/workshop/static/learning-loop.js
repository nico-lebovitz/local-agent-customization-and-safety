// Presenter walkthrough only: selecting a stage never trains or deploys a model.
(() => {
  const el = (id) => document.getElementById(id);
  const stages = [
    {
      id: "execute",
      kind: "OPERATIONAL TOOLS",
      title: "Do the work inside the governed workflow.",
      copy: "The harness selects perceive, triage, draft or request_review. The target architecture runs it inside OpenShell with explicit access policies.",
      evidence: "Inspect a live or recorded execution in section 3.",
      button: "Open agent execution ↗",
      target: "employ",
    },
    {
      id: "relay",
      kind: "OBSERVABILITY / NEMO RELAY",
      title: "Capture what the agent actually did.",
      copy: "Relay records model calls, tool choices and failures. Engineers use this evidence to decide which behaviors need evaluation or improvement.",
      evidence: "Recorded example: triage was attempted before perception.",
      button: "Open the source trace ↗",
      target: "relay-learning",
    },
    {
      id: "gym",
      kind: "LEARNING SKILL / EVALUATE BEHAVIOR",
      title: "Make the behavior testable.",
      copy: "The proposed skill runs Gym scenarios and returns verifier results. The teaching environment already checks evidence dependencies and the required tool sequence.",
      evidence: "Recorded example: skip_evidence receives reward 0.",
      button: "Inspect the Gym example ↗",
      target: "relay-learning",
    },
    {
      id: "rl",
      kind: "LEARNING SKILL / IMPROVE POLICY",
      title: "Train a candidate from verified rewards.",
      copy: "The proposed skill launches a controlled training job and returns its checkpoint and learning curves. The recorded CPU example uses fresh policy samples, Gym rewards and NeMo RL loss functions.",
      evidence: "Loading recorded training evidence…",
      button: "Inspect training curves ↗",
      target: "training-demo",
    },
    {
      id: "approve",
      kind: "EVALUATION + HUMAN APPROVAL",
      title: "Check the candidate before release.",
      copy: "Compare task success, policy violations and failure recovery on frozen evaluation tasks. A reviewer approves a versioned checkpoint; an improved training score alone is insufficient.",
      evidence:
        "A teaching checkpoint exists. Production evaluation and approval are not recorded.",
      button: "Compare the candidate ↗",
    },
    {
      id: "update",
      kind: "RETURN TO EXECUTION",
      title: "Deploy the approved policy and observe again.",
      copy: "The target deployment step promotes an approved checkpoint with a rollback path. Relay then records the updated agent’s behavior, closing the learning loop.",
      evidence:
        "Target step only: the live agent and Lightning weights are unchanged.",
      button: "Inspect the release gate ↗",
    },
  ];
  let index = 0,
    timer = null;
  const reduced = () =>
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const scroll = (id) =>
    el(id).scrollIntoView({
      behavior: reduced() ? "instant" : "smooth",
      block: "start",
    });
  function stop() {
    clearInterval(timer);
    timer = null;
    el("learning-play").textContent = "Walk through the loop ▶";
  }
  function select(i) {
    index = i;
    const s = stages[i];
    document.querySelectorAll("[data-learning-stage]").forEach((b) => {
      const active = b.dataset.learningStage === s.id;
      b.classList.toggle("active", active);
      b.setAttribute("aria-pressed", String(active));
    });
    el("learning-kind").textContent = s.kind;
    el("learning-title").textContent = s.title;
    el("learning-copy").textContent = s.copy;
    el("learning-evidence").textContent = s.evidence;
    el("learning-open").textContent = s.button;
    el("learning-progress").textContent =
      "Stage " + (i + 1) + " of " + stages.length;
  }
  document.querySelectorAll("[data-learning-stage]").forEach((b) =>
    b.addEventListener("click", () => {
      stop();
      select(stages.findIndex((s) => s.id === b.dataset.learningStage));
    }),
  );
  el("learning-play").onclick = () => {
    if (timer) {
      stop();
      return;
    }
    select(0);
    el("learning-play").textContent = "Pause walkthrough";
    timer = setInterval(() => {
      if (index === stages.length - 1) {
        stop();
        return;
      }
      select(index + 1);
    }, 3500);
  };
  el("learning-open").onclick = () => {
    stop();
    const stage = stages[index];
    if (stage.id === "relay" && !el("relay-source-trace").disabled) {
      el("relay-source-trace").click();
      return;
    }
    if (stage.id === "gym" && !el("relay-training-example").disabled) {
      el("relay-training-example").click();
      return;
    }
    if (stage.target) {
      scroll(stage.target);
      return;
    }
    const d = el("candidate-dialog");
    d.showModal();
    document.body.classList.add("dialog-open");
    d.addEventListener(
      "close",
      () => {
        document.body.classList.remove("dialog-open");
        el("learning-open").focus();
      },
      { once: true },
    );
  };
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stop();
  });
  select(0);
  fetch("/api/training-demo")
    .then((r) => {
      if (!r.ok) throw Error("Training artifact unavailable");
      return r.json();
    })
    .then((data) => {
      stages[3].evidence =
        data.optimizer_steps +
        " recorded updates · " +
        data.rollout_count.toLocaleString() +
        " sampled plans · " +
        data.parameters +
        "-parameter teaching controller.";
      const entries = [
        [data.before.expected_reward.toFixed(3), "Before · expected reward"],
        [data.after.expected_reward.toFixed(3), "After · expected reward"],
        [data.weight_update ? "Saved" : "Unchanged", "Teaching checkpoint"],
      ];
      el("candidate-comparison").replaceChildren(
        ...entries.map(([value, label]) => {
          const div = document.createElement("div");
          div.className = "metric";
          const strong = document.createElement("strong"),
            span = document.createElement("span");
          strong.textContent = value;
          span.textContent = label;
          div.append(strong, span);
          return div;
        }),
      );
      el("candidate-identities").textContent = JSON.stringify(
        {
          before: data.before.checkpoint.sha256,
          after: data.after.checkpoint.sha256,
          production_weights_changed: data.production_weights_changed,
          full_nemo_rl_trainer: data.full_nemo_rl_trainer,
        },
        null,
        2,
      );
      select(index);
    })
    .catch(() => {
      stages[3].evidence =
        "The recorded training artifact could not be loaded.";
      el("candidate-identities").textContent =
        "Checkpoint artifact unavailable.";
      select(index);
    });
})();
