/* Base Fleet shared shell: slim top navigation (brand, track, the flow's pages, role switch), theme toggle, optional tours.
   Load once per page with <script defer src="shell.js">. */
(() => {
  "use strict";
  const TOWER_PORT = "8732", PAGES_ORIGIN = "http://localhost:8741/web/";
  const GROUPS = [
    {title: null, items: [{id: "story", href: "story.html", label: "Story overview", short: "Story"},
      {id: "built", href: "built.html", label: "What we built", short: "What we built"}]},
    {title: "A. Learn the house", items: [
      {id: "home", href: "onboarding.html#home", label: "Home", short: "Home"},
      {id: "voice", href: "voice.html", label: "Installation guidance", short: "Guidance"},
      {id: "status", href: "status.html", label: "Status", short: "Status"},
      {id: "rewards", href: "rewards.html", label: "Rewards", short: "Rewards"},
      {id: "demo", href: "demo.html", label: "Walkthrough", short: "Walkthrough"},
      {id: "house", href: "house.html", label: "The lead", short: "The lead"},
      {id: "wall", href: "wall.html", label: "Will it fit", short: "Will it fit"},
      {id: "recovery", href: "recovery.html", label: "Ready to install", short: "Ready to install"},
      {id: "dataqa", href: "data-qa.html", label: "Answers by zip", short: "Zip answers"}]},
    {title: "Where Base stands", items: [
      {id: "explorer", href: "explorer.html", label: "Permit map", short: "Map"},
      {id: "market", href: "market.html", label: "Where Base installs next", short: "Where next"},
      {id: "grid", href: "grid.html", label: "Energy insights by ERCOT", short: "Energy"},
      {id: "ask", href: "ask.html", label: "Search", short: "Search"},
      {id: "judgments", href: "judgments.html", label: "Permit check", short: "Permits"}]},
    {title: "B. Local AI close to you", items: [
      {id: "computehome", href: "compute-home.html", label: "Home", short: "Home"},
      {id: "copilot", href: "copilot.html", label: "My AI", short: "My AI"},
      {id: "energy", href: "energy.html", label: "Energy", short: "Energy"},
      {id: "overview", href: "overview.html", label: "Overview", short: "Overview"},
      {id: "jobs", href: "jobs.html", label: "Job rules", short: "Job rules"},
      {id: "plans", href: "plans.html", label: "Plans", short: "Plans"},
      {id: "pitch", href: "pitch.html", label: "Track 3 pitch", short: "Pitch"},
      {id: "models", href: "models.html", label: "Local models at work", short: "Models"},
      {id: "network", href: "onboarding.html#network", label: "Compute network", short: "Network", tag: "Sim"},
      {id: "index", href: "index.html", label: "Economics", short: "Economics"},
      {id: "tower", href: "tower.html", label: "Control tower", short: "Control tower"},
      {id: "member", href: "member.html", label: "Your home energy", short: "My energy"},
      {id: "placement", href: "placement.html", label: "Stations", short: "Stations"},
      {id: "block", href: "block.html", label: "Neighborhood network", short: "Neighborhood"}]},
    {title: "Operate", items: [
      {id: "brain", href: "brain.html", label: "Help", short: "Help"},
      {id: "knowledge", href: "knowledge.html", label: "Base Brain", short: "Brain"},
      {id: "gaps", href: "gaps.html", label: "Gaps", short: "Gaps"},
      {id: "dataflow", href: "dataflow.html", label: "Data sources", short: "Data sources"},
      {id: "admin", href: "admin.html", label: "Operations", short: "Operations"}]}
  ];
  const ORDER = GROUPS.flatMap(g => g.items);
  const onTower = location.port === TOWER_PORT;
  const TRACKS = {home: "Home & Installation", compute: "Energy & Compute"};
  const PERSONAS = {
    lead: {track: "home", label: "Customer", start: "home", pages: ["home", "status", "rewards", "brain", "member", "knowledge", "built", "voice"]},
    operations: {track: "home", label: "Base admin", start: "judgments", pages: ["judgments", "house", "wall", "recovery", "market", "grid"]},
    gpu: {track: "compute", label: "Customer", start: "computehome", pages: ["computehome", "copilot", "energy", "plans", "models", "tower", "block", "built"]},
    fleet: {track: "compute", label: "Base admin", start: "overview", pages: ["overview", "tower", "placement", "jobs", "index", "plans", "block", "models", "pitch", "built"]}
  };
  const params = new URLSearchParams(location.search);
  const initialId = currentId();
  function inferPersona(id) {
    return ["network", "block", "copilot", "energy", "models", "computehome"].includes(id) ? "gpu"
      : ["index", "tower", "placement", "overview", "jobs", "pitch"].includes(id) ? "fleet"
      : id === "member" ? "lead"
      : PERSONAS.lead.pages.includes(id) ? "lead" : "operations";
  }
  const inferred = inferPersona(initialId);
  const requestedTrack = Object.hasOwn(TRACKS, params.get("track")) ? params.get("track") : null;
  const personaKey = params.get("persona") === "customer" ? "lead" : params.get("persona");
  const requestedPersona = Object.hasOwn(PERSONAS, personaKey) ? personaKey : null;
  const persona = requestedPersona && (!requestedTrack || PERSONAS[requestedPersona].track === requestedTrack)
    ? requestedPersona : requestedTrack ? (requestedTrack === "home" ? "lead" : "gpu") : inferred;
  const track = PERSONAS[persona].track;
  // Existing judge tours remain intact until a visitor explicitly changes perspective.
  const touring = params.has("tour");
  const visible = PERSONAS[persona].pages.map(id => ORDER.find(item => item.id === id));
  const itemLabel = item => item.id === "tower" && persona === "gpu" ? "My compute" : item.label;
  const itemShort = item => item.id === "tower" && persona === "gpu" ? "My compute" : (item.short || item.label);
  function perspectiveUrl(raw, who = persona) {
    const u = new URL(raw, location.href);
    u.searchParams.set("track", PERSONAS[who].track);
    u.searchParams.set("persona", who);
    const current = new URLSearchParams(location.search);
    const id = currentId(u);
    if (who === persona && track === 'home' && ['home', 'voice', 'status', 'rewards', 'brain'].includes(id)) {
      if (!u.searchParams.has('address') && current.get('address')) u.searchParams.set('address', current.get('address'));
    }
    if (who === persona && persona === 'gpu' && ['copilot', 'models', 'energy', 'tower', 'brain', 'block', 'knowledge'].includes(id)) {
      for (const key of ['node', 'from']) {
        if (!u.searchParams.has(key) && current.get(key)) u.searchParams.set(key, current.get(key));
      }
    }
    return u.href;
  }

  function href(item) {
    const raw = onTower && item.id !== "tower" ? PAGES_ORIGIN + item.href : item.href;
    const target = new URL(perspectiveUrl(raw));
    if (item.id === "tower" && persona === "gpu") target.searchParams.set("node", params.get("node") || "3");
    return target.href;
  }

  // The same thing seen by the other role: a member's home is a property record for Base admin,
  // a member's node is a node in the control tower, and back again.
  const COUNTERPART = {
    operations: {home: "house", voice: "house", status: "house", rewards: "house", member: "house"},
    fleet: {copilot: "tower", models: "overview", energy: "tower", computehome: "overview"},
    lead: {house: "status", wall: "status", recovery: "status", market: "home", star: "home", explorer: "home"},
    gpu: {tower: "copilot", overview: "computehome", jobs: "tower", placement: "block", index: "plans"}};
  function roleHref(who, id) {
    let target;
    const twin = id && COUNTERPART[who] && COUNTERPART[who][id];
    if (id && PERSONAS[who].pages.includes(id)) {
      target = new URL(perspectiveUrl(location.href, who));
    } else if (twin && PERSONAS[who].pages.includes(twin)) {
      const item = ORDER.find(x => x.id === twin);
      target = new URL(perspectiveUrl(item.href, who));
      const live = new URLSearchParams(location.search);
      for (const key of ["address", "node"]) if (live.get(key)) target.searchParams.set(key, live.get(key));
    } else {
      const item = ORDER.find(x => x.id === PERSONAS[who].start);
      target = new URL(perspectiveUrl(onTower && item.id !== "tower" ? PAGES_ORIGIN + item.href : item.href, who));
    }
    target.searchParams.delete("tour");
    if (who === "gpu" && currentId(target) === "tower" && !target.searchParams.has("node")) target.searchParams.set("node", params.get("node") || "3");
    return target.href;
  }

  function currentId(url = location) {
    const file = (url.pathname.split("/").pop() || "story.html").toLowerCase();
    if (file === "onboarding.html") return url.hash === "#network" ? "network" : "home";
    const hit = ORDER.find(i => i.href === file);
    return hit ? hit.id : null;
  }

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  const root = document.documentElement;
  const locked = root.hasAttribute("data-theme-lock");
  const THEMES = ["light", "dark"];
  function readTheme() { try { return localStorage.getItem("bf-theme") === "dark" ? "dark" : "light"; } catch { return "light"; } }
  let theme = readTheme();
  function applyTheme(t) {
    if (locked) return;
    root.setAttribute("data-theme", t);
  }
  applyTheme(theme);
  root.classList.add("sh");

  const ICON = d => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + d + '</svg>';
  const SUN = ICON('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>');
  const MOON = ICON('<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>');
  const MENU = ICON('<path d="M4 7h16M4 12h16M4 17h16"/>');

  // Earned points in the top nav on member pages, live from BaseMilestones (milestones.js).
  const SHELL_SRC = document.currentScript && document.currentScript.src;
  function pointsChip() {
    const a = el("a", "sh-points");
    a.href = persona === "lead" ? href(ORDER.find(item => item.id === "rewards"))
      : new URL("rewards.html?track=home&persona=lead", location.href).href;
    a.hidden = true;
    const update = () => {
      const m = window.BaseMilestones;
      const n = m ? m.state().credit : 0;
      a.hidden = !(n > 0);
      if (a.hidden) return;
      a.innerHTML = m.ICON;
      a.append(el("span", "", `${n} ${m.UNIT}`));
      a.setAttribute("aria-label", `${n} points earned. Open Rewards`);
      a.title = m.LABEL;
    };
    document.addEventListener("base-fleet:points", update);
    if (window.BaseMilestones) update();
    else if (SHELL_SRC && !document.querySelector('script[src$="milestones.js"]')) {
      const sc = document.createElement("script");
      sc.src = new URL("milestones.js", SHELL_SRC).href;
      document.head.append(sc);
    }
    return a;
  }

  function build() {
    const body = document.body;
    if (!body || body.querySelector(".sh-nav")) return;
    const cur = currentId();
    if (!touring && (requestedPersona || requestedTrack) && cur && !["story", "demo", "network"].includes(cur) && !visible.some(item => item.id === cur)) {
      location.replace(href(ORDER.find(item => item.id === PERSONAS[persona].start)));
      return;
    }
    if (!touring) history.replaceState(history.state, "", perspectiveUrl(location.href));
    const nav = el("div", "sh-nav");
    nav.setAttribute("role", "navigation");
    nav.setAttribute("aria-label", "Experience navigation");
    const bar = el("div", "sh-bar");

    const head = el("div", "sh-head");
    const brand = el("a", "sh-brand");
    brand.href = new URL('start.html?track=' + track, href(ORDER.find(item => item.id === PERSONAS[persona].start))).href;
    brand.title = 'Choose a workspace';
    // Entry names and event tracks: one place to rename them.
    const ENTRY = {home: {name: "Base Ready", track: "Track 2"}, compute: {name: "Base Super Local AI", track: "Track 3"}};
    const name = el("span", "sh-name", ENTRY[track].name);
    brand.append(name);
    const pill = el("span", "sh-group");
    pill.append(el("span", "sh-entry-track", ` · ${ENTRY[track].track}`));
    pill.title = `${ENTRY[track].name}, hackathon ${ENTRY[track].track}`;
    const toggle = el("button", "sh-toggle");
    toggle.type = "button";
    toggle.setAttribute("aria-expanded", "false");
    const curItem = ORDER.find(i => i.id === cur);
    toggle.append(el("span", "", curItem ? itemLabel(curItem) : "Pages"));
    toggle.insertAdjacentHTML("beforeend", MENU);
    head.append(brand, pill);
    if (persona === "lead" || persona === "gpu") head.append(pointsChip());
    head.append(toggle);

    const groups = el("div", "sh-groups");
    groups.id = "sh-groups";
    toggle.setAttribute("aria-controls", groups.id);
    const more = el("details", "sh-more");
    more.append(el("summary", "", "More"));
    const moreList = el("div", "sh-more-list");
    more.append(moreList);
    const primaryCount = persona === "lead" ? 4 : persona === "fleet" ? 6 : persona === "operations" ? 6 : 5;
    const MENU_HIDDEN = new Set(["voice"]);
    for (const item of visible) {
        if (MENU_HIDDEN.has(item.id)) continue;
        const a = el("a", "sh-link");
        a.href = href(item);
        a.dataset.shId = item.id;
        if (item.id === "home" || item.id === "network") a.dataset.view = item.id;
        a.append(el("span", "sh-short", itemShort(item)), el("span", "sh-full", itemLabel(item)));
        a.title = itemLabel(item);
        if (item.tag) a.append(el("span", "sh-tag", item.tag));
        if (item.id === cur) a.setAttribute("aria-current", "page");
        if (visible.filter(x => !MENU_HIDDEN.has(x.id)).indexOf(item) < primaryCount) groups.append(a);
        else moreList.append(a);
    }
    if (moreList.children.length) groups.append(more);
    const markMore = () => more.classList.toggle("sh-has-current", !!moreList.querySelector('[aria-current="page"]'));
    markMore();
    document.addEventListener("click", e => { if (more.open && !more.contains(e.target) && !nav.classList.contains("sh-open")) more.open = false; });
    document.addEventListener('home-context-changed', event => {
      if (track !== 'home' || typeof event.detail?.address !== 'string') return;
      for (const a of groups.querySelectorAll('.sh-link')) {
        if (!['home', 'voice', 'brain', 'dataqa', 'knowledge'].includes(a.dataset.shId)) continue;
        const u = new URL(a.href); u.searchParams.set('address', event.detail.address); a.href = u.href;
      }
    });

    const foot = el("div", "sh-foot");
    if (!locked) {
      const tb = el("button", "sh-theme");
      tb.type = "button";
      const label = () => {
        tb.innerHTML = (theme === "dark" ? MOON : SUN) + '<span class="sh-theme-text"></span>';
        tb.lastChild.textContent = "Theme: " + theme;
        tb.setAttribute("aria-label", "Theme: " + theme);
        tb.title = "Theme: " + theme;
      };
      label();
      tb.addEventListener("click", () => {
        const next = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
        theme = next;
        try { localStorage.setItem("bf-theme", next); } catch { /* per-visit only */ }
        applyTheme(next);
        label();
      });
      foot.append(tb, el("span", "sh-sep"));
    }
    // Role switch: the same track, opened as Customer or as Base admin.
    const role = el("div", "sh-role");
    role.setAttribute("role", "group");
    role.setAttribute("aria-label", "Role");
    const roles = track === "home" ? ["lead", "operations"] : ["gpu", "fleet"];
    for (const who of roles) {
      const a = el("a", "sh-role-link", PERSONAS[who].label);
      a.href = roleHref(who, cur);
      a.addEventListener("click", () => { a.href = roleHref(who, cur); }); // onboarding adds ?address after load
      a.dataset.shRole = who;
      if (who === persona) a.setAttribute("aria-current", "true");
      role.append(a);
    }
    foot.append(role);
    bar.append(head, groups, foot);
    nav.append(bar);
    body.prepend(nav);

    const closeNav = () => {
      nav.classList.remove("sh-open");
      toggle.setAttribute("aria-expanded", "false");
    };
    toggle.addEventListener("click", () => {
      const open = nav.classList.toggle("sh-open");
      toggle.setAttribute("aria-expanded", String(open));
    });
    groups.addEventListener("click", e => {
      if (e.target.closest("a")) closeNav();
    });
    nav.addEventListener("focusout", e => { if (!nav.contains(e.relatedTarget)) closeNav(); });
    document.addEventListener("keydown", e => {
      if (e.key === "Escape" && nav.classList.contains("sh-open")) { closeNav(); toggle.focus(); }
      else if (e.key === "Escape" && more.open) { more.open = false; more.querySelector("summary").focus(); }
    });

    const beats = el("div", "sh-beats");
    beats.setAttribute("role", "navigation");
    beats.setAttribute("aria-label", "Story beats");
    // Recording tours are opt-in; product workspaces have no story navigation.
    const fill = () => {
      const id = currentId();
      if (tour) { fillTour(id); return; }
      const item = ORDER.find(x => x.id === id);
      toggle.firstChild.textContent = item ? itemLabel(item) : "Pages";
      for (const a of groups.querySelectorAll(".sh-link")) {
        if (a.dataset.shId === id) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
      }
      markMore();
    };
    /* Persona tours: ?tour=<id> walks an ordered list of stops from data/tours.json. */
    let tour = null, banner = null;
    const stopId = page => { const hit = ORDER.find(x => x.href === page); return hit ? hit.id : null; };
    const stopHref = page => {
      const [file, hash] = page.split("#");
      const base = onTower && file !== 'tower.html' ? PAGES_ORIGIN + file : file;
      const u = new URL(base, location.href);
      u.searchParams.set('tour', tour.id);
      if (PERSONAS[tour.persona]?.track === tour.track) {
        u.searchParams.set('track', tour.track); u.searchParams.set('persona', tour.persona);
        if (tour.persona === 'gpu' && file === 'tower.html') u.searchParams.set('node', params.get('node') || '3');
      }
      if (hash) u.hash = hash;
      return u.href;
    };
    const stopLabel = page => { const hit = ORDER.find(x => x.href === page); return hit ? hit.label : page; };
    const tourIndex = id => tour.stops.findIndex(s => stopId(s.page) === id);
    function exitTour() {
      const u = new URL(location.href);
      u.searchParams.delete("tour");
      history.replaceState(history.state, "", u);
      tour = null;
      beats.remove();
      if (banner) banner.remove();
      banner = null;
      root.classList.remove("sh-touring");
      root.style.removeProperty("--sh-tour");
      fill();
      window.dispatchEvent(new Event("resize"));
    }
    function fillTour(id) {
      const i = tourIndex(id), n = tour.stops.length;
      beats.replaceChildren();
      beats.hidden = false;
      const link = (k, cls, dir) => {
        const a = el("a", cls);
        a.href = stopHref(tour.stops[k].page);
        a.append(el("small", "", dir), el("b", "", dir.startsWith("Prev") ? "← " + stopLabel(tour.stops[k].page) : stopLabel(tour.stops[k].page) + " →"));
        return a;
      };
      if (i > 0) beats.append(link(i - 1, "sh-prev", "Previous stop"));
      beats.append(el("span", "sh-pos", i < 0 ? "Not a tour stop" : `Stop ${i + 1} of ${n}`));
      if (i < 0) beats.append(link(0, "sh-next", "Back to the tour"));
      else if (i < n - 1) beats.append(link(i + 1, "sh-next", "Next stop"));
      if (ORDER.find(x => x.id === id)) toggle.firstChild.textContent = ORDER.find(x => x.id === id).label;
      for (const a of groups.querySelectorAll(".sh-link")) {
        if (a.dataset.shId === id) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
      }
      markMore();
      fillBanner(i);
    }
    function fillBanner(i) {
      const n = tour.stops.length, stop = tour.stops[i];
      banner.replaceChildren();
      const who = el("div", "sh-tour-who");
      who.append(el("b", "", tour.label), el("span", "", i < 0 ? "Not a tour stop" : `Stop ${i + 1} of ${n}`));
      const body = el("div", "sh-tour-body");
      if (stop) {
        body.append(el("p", "sh-tour-head", stop.headline));
        if (stop.number) {
          const num = el("p", "sh-tour-num");
          num.append(el("b", "", stop.number.value), document.createTextNode(" " + stop.number.text + " "),
            el("span", "sh-tour-src", "Source: " + stop.number.source));
          body.append(num);
        }
      } else {
        body.append(el("p", "sh-tour-head", tour.story));
      }
      const btns = el("div", "sh-tour-btns");
      const go = (k, text, cls) => {
        const a = el("a", "sh-tour-btn" + (cls ? " " + cls : ""), text);
        if (k >= 0 && k < n) a.href = stopHref(tour.stops[k].page); else { a.setAttribute("aria-disabled", "true"); a.tabIndex = -1; }
        return a;
      };
      btns.append(go(i < 0 ? -1 : i - 1, "← Previous stop"), go(i < 0 ? 0 : i + 1, i === n - 1 ? "Last stop" : "Next stop →", "sh-tour-go"));
      const x = el("button", "sh-tour-btn sh-tour-exit", "Exit tour");
      x.type = "button";
      x.addEventListener("click", exitTour);
      btns.append(x);
      banner.append(who, body, btns);
    }
    const tourParam = new URLSearchParams(location.search).get("tour");
    if (tourParam) {
      fetch("data/tours.json").then(r => r.ok ? r.json() : null).then(data => {
        const t = data && data.tours.find(x => x.id === tourParam);
        if (!t) return;
        if (PERSONAS[t.persona]?.track === t.track && (params.get('track') !== t.track || params.get('persona') !== t.persona)) {
          const u = new URL(location.href);
          u.searchParams.set('track', t.track); u.searchParams.set('persona', t.persona);
          location.replace(u.href); return;
        }
        tour = t;
        body.append(beats);
        banner = el("div", "sh-tour");
        banner.setAttribute("role", "region");
        banner.setAttribute("aria-label", "Persona tour");
        nav.after(banner);
        root.classList.add("sh-touring");
        const size = () => root.style.setProperty("--sh-tour", banner ? banner.offsetHeight + "px" : "0px");
        if (window.ResizeObserver) new ResizeObserver(size).observe(banner);
        fill();
        size();
        window.dispatchEvent(new Event("resize"));
      }).catch(() => { /* no tour data: the page works without the banner */ });
    }
    // Links to another stop of the active tour keep the tour.
    document.addEventListener("click", e => {
      const pageLink = e.target.closest("a[href]");
      if (!pageLink || pageLink.hasAttribute("download")) return;
      // Parse authored parameters without inheriting the current page's query on #links.
      const authored = new URL(pageLink.getAttribute("href"), location.origin + location.pathname);
      if (authored.searchParams.has("tour") || (!tour && ["track", "persona"].some(key => authored.searchParams.has(key)))) return;
      if (pageLink && !tour) {
        const target = new URL(pageLink.href, location.href);
        const id = currentId(target);
        const localTower = ["localhost", "127.0.0.1"].includes(location.hostname)
          && ["localhost", "127.0.0.1"].includes(target.hostname)
          && [TOWER_PORT, "8741"].includes(target.port);
        if ((target.origin === location.origin || localTower) && id) {
          const who = PERSONAS[persona].pages.includes(id) ? persona : inferPersona(id);
          pageLink.href = perspectiveUrl(target.href, who);
        }
      }
      if (!tour || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = e.target.closest("a[href]");
      if (!a || a.closest(".sh-tour, .sh-beats")) return;
      const u = new URL(a.href, location.href);
      if (u.origin !== location.origin) return;
      const file = (u.pathname.split("/").pop() || "index.html").toLowerCase();
      const page = file === "onboarding.html" ? file + (u.hash || "#home") : file;
      if (!tour.stops.some(s => s.page === page)) return;
      u.searchParams.set("tour", tour.id);
      a.href = u.href;
    }, true);
    fill();
    window.addEventListener("hashchange", () => {
      const id = currentId();
      if (!tour && id && !["story", "demo", "network"].includes(id) && !visible.some(item => item.id === id)) {
        location.replace(perspectiveUrl(location.href, inferPersona(id)));
        return;
      }
      fill();
    });
    const cs = getComputedStyle(body);
    if (cs.overflow === "hidden" || cs.overflowY === "hidden" || root.hasAttribute("data-shell-float")) beats.classList.add("sh-float");
    // Pages that sized canvases or maps before the shell existed re-measure once.
    window.dispatchEvent(new Event("resize"));
  }


  // One story across the pages (docs/GOAL.md, "A story for each page"). Each page shows its place and the next beat.
  const STORY = [
    ["start.html", "Pick your track"],
    ["onboarding.html", "Your home from public records"],
    ["voice.html", "Talk me through it"],
    ["status.html", "Your application"],
    ["rewards.html", "Your credit"],
    ["brain.html", "Ask anything"],
    ["knowledge.html", "The knowledge behind every answer"],
    ["pitch.html", "The station near you answers"],
    ["models.html", "How your home AI thinks"],
    ["copilot.html", "Your own AI, next door"],
    ["energy.html", "Your battery and PC this week"],
    ["overview.html", "Private AI on the battery fleet"],
    ["placement.html", "Where a station could sit"],
    ["block.html", "The homes around a station"],
    ["jobs.html", "Three rules on every job"],
    ["tower.html", "Break it and watch it recover"]];
  // Base admin's own story on the home track (docs/GOAL.md, admin rows), ending at Base Brain.
  const ADMIN_STORY = [
    ["judgments.html", "Every permit, routed"],
    ["house.html", "The lead, as Base sees it"],
    ["wall.html", "Will the battery fit"],
    ["recovery.html", "Ready to install"],
    ["market.html", "Where Base installs next"]];
  function adminStoryBar(file) {
    const i = ADMIN_STORY.findIndex(([f]) => f === file);
    if (i < 0) return false;
    const next = i + 1 === ADMIN_STORY.length ? ["onboarding.html", "See it as the customer"] : ADMIN_STORY[i + 1];
    const bar = document.createElement("nav");
    bar.className = "sh-story";
    bar.setAttribute("aria-label", "The Base admin story");
    const where = document.createElement("span");
    where.textContent = `Base admin story ${i + 1} of ${ADMIN_STORY.length}: ${ADMIN_STORY[i][1]}`;
    const a = document.createElement("a");
    a.href = next[0] === "onboarding.html" ? "onboarding.html?track=home&persona=lead" : `${next[0]}?track=home&persona=operations`;
    a.textContent = `Next: ${next[1]}`;
    bar.append(where, a);
    document.body.append(bar);
    return true;
  }
  function storyBar() {
    const file = location.pathname.split("/").pop() || "start.html";
    if (document.querySelector(".sh-story")) return;
    if (adminStoryBar(file)) return;
    const i = STORY.findIndex(([f]) => f === file);
    if (i < 0) return;
    // The tower is the last beat; it hands back to the pitch's close line.
    // The voice guide is the assisted side path: both it and onboarding lead to status.
    const SKIP = {"onboarding.html": "status.html", "voice.html": "status.html"};
    const next = i + 1 === STORY.length ? ["pitch.html#close", "The close"]
      : SKIP[file] ? STORY.find(([f]) => f === SKIP[file]) : STORY[i + 1];
    const url = new URL(next[0], location.href);
    for (const k of ["address", "node"]) if (params.get(k)) url.searchParams.set(k, params.get(k));
    const bar = document.createElement("nav");
    bar.className = "sh-story";
    bar.setAttribute("aria-label", "The story");
    const where = document.createElement("span");
    where.textContent = `Story ${i + 1} of ${STORY.length}: ${STORY[i][1]}`;
    const a = document.createElement("a");
    a.href = url.pathname.split("/").pop() + url.search + url.hash;
    a.textContent = `Next: ${next[1]}`;
    bar.append(where, a);
    document.body.append(bar);
  }
  // Page analytics, only on the hosted site. Google Analytics loads only when a measurement id is set in ANALYTICS.ga (for example "G-XXXXXXX").
  const ANALYTICS = {ga: "G-9QLRH4GSME"};
  function analytics() {
    if (!/\.vercel\.app$|^basefleet\./.test(location.hostname) || window.__bfAnalytics) return;
    window.__bfAnalytics = true;
    const add = (src, attrs = {}) => {
      const s = document.createElement("script");
      s.defer = true; s.src = src;
      for (const [k, v] of Object.entries(attrs)) s.setAttribute(k, v);
      document.head.append(s);
    };
    if (/^G-[A-Z0-9]+$/.test(ANALYTICS.ga)) {
      add(`https://www.googletagmanager.com/gtag/js?id=${ANALYTICS.ga}`);
      window.dataLayer = window.dataLayer || [];
      window.gtag = function () { window.dataLayer.push(arguments); };
      window.gtag("js", new Date());
      window.gtag("config", ANALYTICS.ga, {anonymize_ip: true});
    }
  }
  function sources() {
    if (document.querySelector('script[src$="sources.js"]')) return;
    const css = document.createElement("link");
    css.rel = "stylesheet"; css.href = new URL("sources.css", document.currentScript ? document.currentScript.src : location.href).href;
    document.head.append(css);
    const js = document.createElement("script");
    js.defer = true; js.src = new URL("sources.js", css.href).href;
    document.head.append(js);
  }
  // Home is onboarding for a new member and becomes "Your home" once Base has installed (tracker step 5 done).
  function homeLink() {
    const s = window.BaseMilestones && window.BaseMilestones.state();
    if (!s || s.status[4] !== "done") return;
    document.querySelectorAll('.sh-link[data-sh-id="home"]').forEach(a => {
      a.href = a.href.replace(/onboarding\.html[^"]*$/, "member.html" + location.search);
      a.querySelectorAll(".sh-short,.sh-full").forEach(n => { n.textContent = "Your home"; });
      a.title = "Your home";
    });
  }
  // Credit line at the bottom of every page; the landing page has its own in the footer.
  function builtBy() {
    if (document.querySelector(".sh-built, [data-built-by]")) return;
    const p = el("p", "sh-built");
    const link = (href, text) => { const a = el("a", "sh-built-link", text); a.href = href; a.target = "_blank"; a.rel = "noopener"; return a; };
    p.append("Built by ", link("https://www.linkedin.com/in/jravinder/", "Ravinder Jilkapally"), " · ", link("https://aisoft.us", "aisoft.us"));
    document.body.append(p);
  }

  function boot() { analytics(); build(); sources(); builtBy(); setTimeout(homeLink, 0); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

  // The admin story follows one lead: carry ?address= to the next step.
  (function carryLead() {
    const addr = new URLSearchParams(location.search).get("address");
    const next = document.getElementById("story-next");
    if (!addr || !next) return;
    const u = new URL(next.getAttribute("href"), location.href);
    u.searchParams.set("address", addr);
    next.href = u.pathname.split("/").pop() + u.search + u.hash;
  })();
})();
