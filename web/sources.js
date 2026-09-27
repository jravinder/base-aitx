/* Data sources strip: where this page's data comes from (web/data/sources.json).
   Loaded by shell.js on every page; placed above the story bar. */
(() => {
  "use strict";
  const file = location.pathname.split("/").pop() || "start.html";
  const KIND = {public: "Public data", measured: "Measured by us", simulation: "Simulation"};

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  async function render() {
    if (document.querySelector(".sh-sources")) return;
    let data;
    try {
      const r = await fetch(new URL("data/sources.json", document.currentScript ? document.currentScript.src : location.href));
      if (!r.ok) return;
      data = await r.json();
    } catch { return; }
    const keys = (data.pages || {})[file];
    if (!keys || !keys.length) return;
    const box = el("details", "sh-sources");
    const sum = el("summary");
    sum.append(el("span", "sh-src-title", "Data sources"), el("span", "sh-src-count", `${keys.length} on this page`));
    box.append(sum);
    const list = el("ul", "sh-src-list");
    for (const k of keys) {
      const d = (data.datasets || {})[k];
      if (!d) continue;
      const li = el("li");
      const head = el("div", "sh-src-head");
      const name = d.url ? el("a", "sh-src-name", d.name) : el("span", "sh-src-name", d.name);
      if (d.url) { name.href = d.url; name.target = "_blank"; name.rel = "noopener"; }
      head.append(name, el("span", `sh-src-kind sh-src-${d.kind || "public"}`, KIND[d.kind] || "Public data"));
      const meta = [d.publisher, d.id, d.refresh ? `refreshed ${d.refresh}` : ""].filter(Boolean).join(" · ");
      li.append(head, el("p", "sh-src-meta", meta));
      list.append(li);
    }
    box.append(list);
    const story = document.querySelector(".sh-story");
    if (story) story.before(box); else document.body.append(box);
    // Open by default on wide screens so judges see it; collapsed on phones.
    if (window.matchMedia("(min-width: 900px)").matches) box.open = true;
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => setTimeout(render, 0));
  else setTimeout(render, 0);
})();
