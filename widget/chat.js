/* School chat window. Add to any web page with one tag:
     <script src="https://YOUR-SERVER/widget/chat.js" defer></script>
   Optional attributes on the tag:
     data-api="https://YOUR-SERVER"  where the chatbot backend runs (default: where this file came from)
     data-campus="pilot-campus"      skip the campus question for a campus-specific page
     data-open="true"                open the chat window straight away
     data-theme="light" | "dark"     force a theme (default: follows the visitor's device) */
(function () {
  "use strict";
  var script = document.currentScript;
  var scriptUrl = new URL(script.src, location.href);
  var API = (script.getAttribute("data-api") || scriptUrl.origin).replace(/\/$/, "");
  var FIXED_CAMPUS = script.getAttribute("data-campus") || "";
  var FALLBACK = "I'm having trouble right now. Please call the front office.";
  var GROUPS = [
    { id: "prospective", label: "I'm exploring admissions" },
    { id: "existing", label: "I'm a current parent or student" },
    { id: "vendor", label: "Business or vendor enquiry" }
  ];

  // ---------- Saved state (sessionStorage: kept while the browser tab is open) ----------
  var KEY = "schoolChat:";
  function load(name, fallback) {
    try { var v = sessionStorage.getItem(KEY + name); return v === null ? fallback : JSON.parse(v); }
    catch (e) { return fallback; }
  }
  function save(name, value) { try { sessionStorage.setItem(KEY + name, JSON.stringify(value)); } catch (e) {} }
  function newId() {
    // The session id is the only key to this chat's history, so it must be unguessable.
    // randomUUID only exists on HTTPS pages; getRandomValues works everywhere (never use Math.random here).
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    var bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    return "s-" + Array.prototype.map.call(bytes, function (b) { return ("0" + b.toString(16)).slice(-2); }).join("");
  }
  var state = {
    sessionId: load("session", null) || newId(),
    campus: load("campus", ""),
    group: load("group", ""),
    log: load("log", []),        // messages shown, so a page reload keeps the conversation
    started: load("started", false)
  };
  save("session", state.sessionId);
  var config = { demo: true, school_name: "School", assistant_name: "School Assistant", campuses: [], menus: {} };
  var busy = false;

  // ---------- Build the window ----------
  var css = document.createElement("link");
  css.rel = "stylesheet";
  css.href = new URL("chat.css", scriptUrl).href;
  document.head.appendChild(css);

  var root = document.createElement("div");
  root.className = "sc-root";
  var theme = script.getAttribute("data-theme");
  if (theme === "light" || theme === "dark") root.setAttribute("data-theme", theme);
  root.innerHTML =
    '<button class="sc-launcher" type="button" aria-label="Open chat with the school assistant">' +
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg>' +
    '<span>Ask us</span></button>' +
    '<section class="sc-panel" role="dialog" aria-label="Chat with the school assistant" hidden>' +
    '<div class="sc-head"><div class="sc-avatar" aria-hidden="true"></div>' +
    '<div class="sc-title"><strong></strong><span></span></div>' +
    '<span class="sc-demo" hidden>Demo</span>' +
    '<button class="sc-icon-btn sc-restart" type="button" title="Start a new chat" aria-label="Start a new chat">&#x21bb;</button>' +
    '<button class="sc-icon-btn sc-close" type="button" aria-label="Close chat">&#x2715;</button></div>' +
    '<div class="sc-msgs" aria-live="polite"></div>' +
    '<div class="sc-chips"></div>' +
    '<form class="sc-form" autocomplete="off"><input type="text" maxlength="1000" placeholder="Type your question..." aria-label="Type your message">' +
    '<button type="submit">Send</button></form>' +
    '<div class="sc-foot"></div></section>';
  document.body.appendChild(root);

  var $ = function (sel) { return root.querySelector(sel); };
  var launcher = $(".sc-launcher"), panel = $(".sc-panel"), msgs = $(".sc-msgs"), chips = $(".sc-chips");
  var form = $(".sc-form"), input = $(".sc-form input"), sendBtn = $(".sc-form button");

  // ---------- Showing messages ----------
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  // Turn the bot's plain text into safe HTML: paragraphs, bullet/numbered lists and **bold**.
  function format(text) {
    var html = "", list = null;
    esc(text).split(/\n/).forEach(function (line) {
      var t = line.trim(), m;
      if ((m = t.match(/^[-*•]\s+(.*)$/)) || (m = t.match(/^\d+[.)]\s+(.*)$/))) {
        var type = /^\d/.test(t) ? "ol" : "ul";
        if (list !== type) { if (list) html += "</" + list + ">"; html += "<" + type + ">"; list = type; }
        html += "<li>" + m[1] + "</li>";
        return;
      }
      if (list) { html += "</" + list + ">"; list = null; }
      if (t) html += "<p>" + t + "</p>";
    });
    if (list) html += "</" + list + ">";
    return html.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
  }
  function scrollDown() { msgs.scrollTop = msgs.scrollHeight; }
  function render(entry) {
    var el = document.createElement("div");
    el.className = "sc-msg " + (entry.who === "you" ? "sc-you" : "sc-bot") + (entry.error ? " sc-error" : "");
    if (entry.who === "you") el.textContent = entry.text; else el.innerHTML = format(entry.text);
    msgs.appendChild(el);
    scrollDown();
    return el;
  }
  function add(who, text, extra) {
    var entry = { who: who, text: text };
    if (extra && extra.error) entry.error = true;
    state.log.push(entry);
    state.log = state.log.slice(-60);
    save("log", state.log);
    return render(entry);
  }
  function typing(on) {
    var t = msgs.querySelector(".sc-typing");
    if (on && !t) {
      t = document.createElement("div");
      t.className = "sc-msg sc-bot sc-typing";
      t.setAttribute("aria-label", "Assistant is typing");
      t.innerHTML = "<i></i><i></i><i></i>";
      msgs.appendChild(t);
      scrollDown();
    } else if (!on && t) t.remove();
  }
  // Quick-reply buttons. Each item: {label, onClick} or a plain string (sent as a message).
  function setChips(items) {
    chips.innerHTML = "";
    items.forEach(function (item) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "sc-chip" + (item.alt ? " sc-alt" : "");
      b.textContent = item.label || item;
      b.onclick = function () { if (busy) return; if (item.onClick) item.onClick(); else send(item.label || item); };
      chips.appendChild(b);
    });
  }

  // ---------- Opening flow: greeting -> campus -> group -> menu ----------
  function start() {
    state.started = true; save("started", true);
    add("bot", "Hello! I'm the " + config.assistant_name + " for " + config.school_name +
      ". I answer from the school's approved information and can pass your request to the right person.");
    if (FIXED_CAMPUS || config.campuses.length === 0) { chooseCampus(FIXED_CAMPUS || "pilot-campus", true); return; }
    askCampus();
  }
  function askCampus() {
    add("bot", "Which campus are you asking about?");
    campusChips();
  }
  function campusChips() {
    setChips(config.campuses.map(function (c) {
      return { label: c.name, onClick: function () { add("you", c.name); chooseCampus(c.id); } };
    }));
  }
  function campusName(id) {
    for (var i = 0; i < config.campuses.length; i++) if (config.campuses[i].id === id) return config.campuses[i].name;
    return id;
  }
  function chooseCampus(id, silent) {
    state.campus = id; save("campus", id);
    if (!silent) add("bot", "Thank you. I'll answer for " + campusName(id) + ".");
    askGroup();
  }
  function askGroup() {
    add("bot", "Which of these describes you?");
    groupChips();
  }
  function groupChips() {
    setChips(GROUPS.map(function (g) {
      return { label: g.label, onClick: function () { add("you", g.label); chooseGroup(g.id); } };
    }));
  }
  function chooseGroup(id) {
    state.group = id; save("group", id);
    if (id === "vendor") { send("I have a business or vendor enquiry. Who should I contact?", { silent: true }); return; }
    add("bot", id === "prospective"
      ? "Great. Ask me anything about admissions, or choose a topic below."
      : "Welcome. I can help with the calendar, fees, transport and PTM, or pass a concern to the right person.");
    showMenu();
  }
  function showMenu() {
    var items = (config.menus[state.group] || []).slice();
    setChips(items.concat([{ label: "Talk to a person", alt: true }]));
  }
  function afterReply() {
    setChips([
      { label: "Menu", onClick: showMenu },
      { label: "Talk to a person", alt: true }
    ]);
  }

  // ---------- Talking to the backend ----------
  function send(text, opts) {
    text = String(text || "").trim();
    if (!text || busy) return;
    opts = opts || {};
    if (!state.campus) { state.campus = FIXED_CAMPUS || (config.campuses[0] && config.campuses[0].id) || "pilot-campus"; save("campus", state.campus); }
    if (!opts.silent) add("you", text);
    input.value = "";
    chips.innerHTML = "";
    setBusy(true);
    fetch(API + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.sessionId, campus: state.campus, message: text, group: state.group || null })
    })
      .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
      .then(function (res) {
        var body = res.body || {};
        setDemo(body.demo);
        add("bot", body.reply || FALLBACK, { error: !res.ok });
        if (body.action && actions[body.action]) actions[body.action](body); else afterReply();
      })
      .catch(function () { add("bot", FALLBACK, { error: true }); afterReply(); })
      .then(function () { setBusy(false); });
  }
  // Extra steps the backend can ask for.
  var actions = {
    // Privacy notice with "I agree" / "No thanks", shown before any personal details are collected.
    consent: function (body) {
      var card = document.createElement("div");
      card.className = "sc-msg sc-bot sc-card sc-consent";
      card.innerHTML = "<h4>Privacy notice</h4>" + format(body.notice || "We use your details only to answer your request.") +
        '<div class="sc-card-actions"></div>';
      var row = card.querySelector(".sc-card-actions");
      [{ label: "I agree", agree: true }, { label: "No thanks", agree: false, alt: true }].forEach(function (choice) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "sc-chip" + (choice.alt ? " sc-alt" : "");
        b.textContent = choice.label;
        b.onclick = function () { answerConsent(choice.agree, card); };
        row.appendChild(b);
      });
      msgs.appendChild(card);
      scrollDown();
      setChips([{ label: "Menu", onClick: showMenu, alt: true }]);
    }
  };
  function answerConsent(agree, card) {
    if (busy) return;
    card.querySelector(".sc-card-actions").remove();
    fetch(API + "/consent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.sessionId, agree: agree })
    })
      .then(function (r) { if (!r.ok) throw new Error("consent failed"); })
      .then(function () { send(agree ? "I agree to the privacy notice." : "No thanks, I don't want to share my details."); })
      .catch(function () { add("bot", FALLBACK, { error: true }); afterReply(); });
  }

  function setBusy(on) {
    busy = on;
    typing(on);
    sendBtn.disabled = on;
  }
  function setDemo(demo) {
    if (typeof demo !== "boolean") return;
    config.demo = demo;
    $(".sc-demo").hidden = !demo;
    $(".sc-foot").textContent = demo ? "Demo: answers use dummy data for a fictional school." : "Answers come from the school's approved information.";
  }

  form.addEventListener("submit", function (e) { e.preventDefault(); send(input.value); });
  launcher.addEventListener("click", open);
  $(".sc-close").addEventListener("click", function () { panel.hidden = true; launcher.hidden = false; launcher.focus(); });
  $(".sc-restart").addEventListener("click", function () {
    if (busy) return;
    state = { sessionId: newId(), campus: "", group: "", log: [], started: false };
    ["campus", "group", "log", "started"].forEach(function (k) { try { sessionStorage.removeItem(KEY + k); } catch (e) {} });
    save("session", state.sessionId);
    msgs.innerHTML = ""; chips.innerHTML = "";
    start();
  });

  function open() {
    panel.hidden = false;
    launcher.hidden = true;
    if (!state.started) start();
    input.focus();
  }

  // ---------- Start up ----------
  fetch(API + "/config")
    .then(function (r) { return r.json(); })
    .catch(function () { return {}; })
    .then(function (c) {
      for (var k in c) config[k] = c[k];
      $(".sc-avatar").textContent = (config.school_name.match(/\b\w/g) || ["S"]).slice(0, 2).join("").toUpperCase();
      $(".sc-title strong").textContent = config.assistant_name;
      $(".sc-title span").textContent = config.school_name;
      setDemo(config.demo);
      state.log.forEach(render);          // restore the conversation after a page reload
      if (state.started) { if (state.group) afterReply(); else if (state.campus) groupChips(); else campusChips(); }
      if (script.getAttribute("data-open") === "true") open();
    });

  window.SchoolChat = { open: open, actions: actions, send: send };
})();
