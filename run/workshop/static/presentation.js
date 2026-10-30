// Chapter navigation follows scroll position without snapping or taking over keys.
(() => {
  const sections = [...document.querySelectorAll("main > section")];
  const links = [
    ...document.querySelectorAll('nav[aria-label="Workshop chapters"] a'),
  ];
  let current = 0,
    scheduled = false;
  function update() {
    scheduled = false;
    const top =
      document.querySelector("aside").getBoundingClientRect().bottom + 30;
    current = 0;
    sections.forEach((section, i) => {
      if (section.getBoundingClientRect().top <= top) current = i;
    });
    if (
      window.innerHeight + window.scrollY >=
      document.documentElement.scrollHeight - 4
    )
      current = sections.length - 1;
    links.forEach((link, i) => {
      link.classList.toggle("active", i === current);
      if (i === current) link.setAttribute("aria-current", "step");
      else link.removeAttribute("aria-current");
    });
    document.getElementById("chapter-position").textContent =
      String(current + 1).padStart(2, "0") +
      " / " +
      links[current].querySelector("span").textContent;
    document.getElementById("chapter-progress").value = current + 1;
    document.getElementById("chapter-prev").disabled = current === 0;
    document.getElementById("chapter-next").disabled =
      current === sections.length - 1;
  }
  const move = (delta) => {
    const target =
      sections[Math.max(0, Math.min(sections.length - 1, current + delta))];
    target.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth",
      block: "start",
    });
  };
  document.getElementById("chapter-prev").onclick = () => move(-1);
  document.getElementById("chapter-next").onclick = () => move(1);
  window.addEventListener(
    "scroll",
    () => {
      if (!scheduled) {
        scheduled = true;
        requestAnimationFrame(update);
      }
    },
    { passive: true },
  );
  window.addEventListener("resize", update);
  update();
})();
function renderCapabilities(run) {
  const counts = {};
  for (const event of run.events)
    if (event.kind === "tool")
      counts[event.data.tool] = (counts[event.data.tool] || 0) + 1;
  document.querySelectorAll("[data-tool-use]").forEach((b) => {
    const count = counts[b.dataset.toolUse] || 0;
    b.textContent = count
      ? "Called " + count + (count === 1 ? " time" : " times")
      : "Not called";
    b.classList.toggle("called", count > 0);
  });
  document.getElementById("capability-context").textContent =
    "Selected execution " +
    run.id.slice(0, 8) +
    " · " +
    run.status +
    " · counts include attempted calls that failed.";
}
