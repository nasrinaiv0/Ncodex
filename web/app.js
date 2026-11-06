"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  function savedHumanoid() {
    // Only the cosmetic preference is saved; never persist account secrets.
    try { return localStorage.getItem("ncodex.humanoid.v1") === "ej" ? "ej" : "dirk"; }
    catch { return "dirk"; }
  }
  const state = { screen: "home", side: "buy", token: "", paper: null, tts: false, listening: false, busy: false, humanoid: savedHumanoid() };
  const humanoids = {
    dirk: {
      name: "DIRK", title: "Risk & strategy", emblem: "D",
      greeting: "I'm Dirk, your disciplined risk and strategy companion. I can explain market analysis, guide paper trades, and request TradingAgents reports. I never place real orders.",
      switched: "Dirk online. I'll focus on risk, capital protection and clear trade plans. Our trades remain paper-only."
    },
    ej: {
      name: "EJ", title: "Research & signals", emblem: "E",
      greeting: "I'm EJ, your curious market research companion. I help compare signals, explore tokens and request TradingAgents reports. No live quotes or real orders are connected.",
      switched: "EJ online. I'll focus on research, market signals and alternative viewpoints. I'll never invent live prices."
    }
  };
  const money = (v) => {
    const n = Number(v);
    if (!Number.isFinite(n)) return "—";
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n);
  };
  const qtyText = (value) => {
    const text = String(value);
    const n = Number(text);
    if (!Number.isFinite(n)) return text;
    return new Intl.NumberFormat("en-US", { maximumFractionDigits: 8, minimumFractionDigits: 0 }).format(n);
  };
  const amount = (value, name) => {
    const t = String(value).trim();
    if (!/^(?:\d+)(?:\.\d+)?$/.test(t)) throw Error(name + " must be a nonnegative decimal number.");
    if (t.length > 24) throw Error(name + " value is too long.");
    return t;
  };
  const newId = () => (globalThis.crypto && globalThis.crypto.randomUUID ? globalThis.crypto.randomUUID() : String(Date.now()) + "-" + Math.random().toString(16).slice(2));
  let toastTimer = null;
  function toast(text) {
    const el = $("toast");
    el.textContent = text;
    el.classList.add("visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("visible"), 3400);
  }
  function setHumanoid(version, announce = false) {
    if (!Object.prototype.hasOwnProperty.call(humanoids, version)) return;
    const changed = version !== state.humanoid;
    state.humanoid = version;
    const bot = humanoids[version];
    document.body.dataset.humanoid = version;
    for (const button of document.querySelectorAll("[data-humanoid]")) {
      const active = button.dataset.humanoid === version;
      button.classList.toggle("selected", active);
      button.setAttribute("aria-pressed", String(active));
    }
    const texts = {
      "hero-bot-name": bot.name, "chat-bot-name": bot.name,
      "nav-bot-label": bot.name, "action-bot-label": "Ask " + bot.name,
      "hero-talk-label": "Talk to " + bot.name,
      "robot-emblem": bot.emblem, "initial-bot-label": bot.name,
      "initial-bot-message": bot.greeting
    };
    for (const [id, text] of Object.entries(texts)) {
      const node = $(id);
      if (node) node.textContent = text;
    }
    const stage = $("humanoid-stage");
    if (stage) stage.setAttribute("aria-label", "Animated humanoid trading assistant " + bot.name);
    const input = $("chat-input");
    if (input) input.placeholder = "Ask " + bot.name + " about trading…";
    try { localStorage.setItem("ncodex.humanoid.v1", version); } catch {}
    if (announce && changed && state.screen === "chat") chatBubble("bot", bot.switched);
  }
  document.querySelectorAll("button[data-humanoid]").forEach(button => {
    button.addEventListener("click", () => setHumanoid(button.dataset.humanoid, true));
  });
  setHumanoid(state.humanoid);
  function setExpression(expression) {
    const face = $("humanoid-avatar");
    if (face) face.dataset.expression = expression;
  }
  function navigate(page) {
    if (!document.querySelector('[data-screen="' + page + '"]')) return;
    state.screen = page;
    document.querySelectorAll(".screen").forEach(s => s.classList.toggle("active", s.dataset.screen === page));
    document.querySelectorAll(".nav-item").forEach(n => {
      const active = n.dataset.goto === page;
      n.classList.toggle("selected", active);
      if (active) n.setAttribute("aria-current", "page"); else n.removeAttribute("aria-current");
    });
    setExpression("idle");
    if (page === "trade") showOrderPreview();
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    history.replaceState(null, "", "#" + page);
  }
  document.querySelectorAll("[data-goto]").forEach(el => el.addEventListener("click", () => navigate(el.dataset.goto)));
  window.addEventListener("hashchange", () => {
    const name = location.hash.slice(1);
    if (["home", "research", "trade", "chat", "agents", "settings", "connect"].includes(name)) navigate(name);
  });
  const startPage = location.hash.slice(1);
  if (["home", "research", "trade", "chat", "agents", "settings", "connect"].includes(startPage)) navigate(startPage);
  $("open-settings").addEventListener("click", () => navigate("settings"));
  $("save-token").addEventListener("click", () => {
    state.token = $("access-token").value.trim();
    $("access-token").value = "";
    toast("Token held only in this page session.");
    window.dispatchEvent(new Event("ncodex:access-changed"));
    refresh();
  });
  $("check-status").addEventListener("click", refresh);
  $("refresh").addEventListener("click", refresh);
  const headers = () => state.token ? { Authorization: "Bearer " + state.token } : {};
  async function api(path, body) {
    const options = { cache: "no-store", headers: { ...headers() } };
    if (body !== undefined) {
      options.method = "POST";
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    options.signal = controller.signal;
    try {
      const response = await fetch(path, options);
      const raw = await response.text();
      let data;
      try { data = JSON.parse(raw); } catch { throw Error("Server returned invalid JSON"); }
      if (!response.ok) throw Error(data.error || "Request failed (" + response.status + ")");
      return data;
    } finally {
      clearTimeout(timer);
    }
  }
  function renderPaper(data) {
    state.paper = data;
    $("balance").textContent = money(data.cash_usd);
    $("pnl").textContent = money(data.realized_pnl_usd);
    $("trade-cash").textContent = money(data.cash_usd);
    $("trade-pnl").textContent = money(data.realized_pnl_usd);
    const positions = Object.entries(data.positions || {});
    $("position-count").textContent = String(positions.length);
    $("portfolio-position-count").textContent = positions.length + " open";
    $("ledger-status").textContent = data.journal_balanced ? "Balanced" : "Needs review";
    const holder = $("positions");
    holder.replaceChildren();
    if (positions.length === 0) {
      holder.className = "empty-state";
      holder.textContent = "No paper positions yet.";
    } else {
      holder.className = "";
      positions.forEach(([mint, value]) => {
        const entry = document.createElement("div");
        entry.className = "position-item";
        const name = document.createElement("div");
        const title = document.createElement("b");
        title.textContent = "Synthetic SOL test";
        const detail = document.createElement("small");
        detail.textContent = mint.slice(0, 7) + "…" + mint.slice(-5) + " · " + qtyText(value.quantity) + " units";
        name.append(title, detail);
        const cost = document.createElement("strong");
        cost.textContent = money(value.cost_basis_usd);
        entry.append(name, cost);
        holder.append(entry);
      });
    }
    showOrderPreview();
  }
  async function refresh() {
    $("refresh").classList.add("loading");
    $("connection-label").textContent = "Checking";
    try {
      const [paper, integrations] = await Promise.all([api("/api/paper"), api("/api/integrations")]);
      renderPaper(paper);
      const t = integrations.tradingagents || {};
      const f = integrations.freqtrade || {};
      $("ta-status").textContent = t.ready_to_attempt ? "Ready*" : "Setup needed";
      $("settings-ta").textContent = t.ready_to_attempt ? "Ready to attempt*" : "Not connected";
      $("ft-status").textContent = f.connected && f.mode === "read-only dry-run" ? "Dry-run" : "Not connected";
      $("settings-ft").textContent = f.mode || "Not configured";
      $("connection-label").textContent = "Checked";
      $("utc-time").textContent = "LAST CHECK " + new Date().toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"});
    } catch (err) {
      $("connection-label").textContent = "Offline";
      $("utc-time").textContent = "SERVER UNAVAILABLE";
      toast("Connection: " + err.message);
    } finally { $("refresh").classList.remove("loading"); }
  }
  function showOrderPreview() {
    if (!state.paper) { $("order-preview").textContent = "Connect to the paper server to simulate."; return; }
    const text = $("order-amount").value.trim();
    const fee = $("order-fee").value.trim();
    if (state.side === "buy") {
      $("order-preview").textContent = "Synthetic price: $1.25 · Budget " + money(text) + " including " + money(fee) + " fees. No real order.";
    } else {
      $("order-preview").textContent = "Synthetic sale at $1.25 per unit · " + qtyText(text) + " tokens · Fee " + money(fee) + ". No real order.";
    }
  }
  $("order-amount").addEventListener("input", showOrderPreview);
  $("order-fee").addEventListener("input", showOrderPreview);
  function setSide(side) {
    state.side = side;
    $("buy-mode").classList.toggle("selected", side === "buy");
    $("sell-mode").classList.toggle("selected", side === "sell");
    $("buy-mode").setAttribute("aria-selected", String(side === "buy"));
    $("sell-mode").setAttribute("aria-selected", String(side === "sell"));
    $("order-amount-label").textContent = side === "buy" ? "Budget in USD (fees included)" : "Quantity of demo tokens";
    $("order-amount").value = side === "buy" ? "20" : "1";
    $("place-paper").textContent = side === "buy" ? "Simulate paper buy" : "Simulate paper sell";
    $("order-approval").checked = false;
    showOrderPreview();
  }
  $("buy-mode").addEventListener("click", () => setSide("buy"));
  $("sell-mode").addEventListener("click", () => setSide("sell"));
  async function perform(form, fn) {
    if (state.busy) return;
    state.busy = true;
    const button = form.querySelector('[type="submit"]');
    const old = button.textContent;
    button.disabled = true;
    button.textContent = "Processing…";
    try { await fn(); }
    catch(err) { toast(err.message || "Request failed"); }
    finally { button.disabled = false; button.textContent = old; state.busy = false; }
  }
  $("fund-form").addEventListener("submit", e => {
    e.preventDefault();
    perform(e.currentTarget, async () => {
      const usd = amount($("deposit-usd").value, "Paper funds");
      if (Number(usd) <= 0) throw Error("Paper deposit must be positive.");
      const result = await api("/api/paper/fund", { id: newId(), usd, approved: true });
      renderPaper(result.summary);
      toast("Simulated funds added. No actual money moved.");
    });
  });
  $("order-form").addEventListener("submit", e => {
    e.preventDefault();
    perform(e.currentTarget, async () => {
      if (!$("order-approval").checked) throw Error("Please approve the paper-only trade.");
      const value = amount($("order-amount").value, "Trade amount");
      const fee = amount($("order-fee").value, "Fee");
      if (Number(value) <= 0) throw Error("Trade amount must be positive.");
      let body;
      let path;
      if (state.side === "buy") {
        path = "/api/paper/buy";
        body = { id: newId(), candidate_id: "demo-sol", usd: value, fee_usd: fee, approved: true };
      } else {
        path = "/api/paper/sell";
        body = { id: newId(), candidate_id: "demo-sol", qty: value, price_usd: "1.25", fee_usd: fee, approved: true };
      }
      const result = await api(path, body);
      renderPaper(result.summary);
      $("order-approval").checked = false;
      toast("Paper " + state.side + " recorded. No real trade executed.");
    });
  });
  function chatBubble(role, message) {
    const wrap = document.createElement("div");
    wrap.className = "chat-bubble " + (role === "bot" ? "bot-bubble" : "user-bubble");
    const label = document.createElement("b");
    label.textContent = role === "bot" ? humanoids[state.humanoid].name : "YOU";
    const p = document.createElement("p");
    p.textContent = message;
    wrap.append(label,p);
    $("chat-messages").append(wrap);
    $("chat-messages").scrollTop = $("chat-messages").scrollHeight;
  }
  function speak(text) {
    if (!state.tts || !("speechSynthesis" in window)) return;
    speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text.slice(0, 1400));
    utterance.rate = state.humanoid === "dirk" ? 0.94 : 1.08;
    utterance.pitch = state.humanoid === "dirk" ? 0.88 : 1.12;
    utterance.onstart = () => setExpression("speaking");
    utterance.onend = () => setExpression("idle");
    utterance.onerror = () => setExpression("idle");
    speechSynthesis.speak(utterance);
  }
  $("tts-button").addEventListener("click", () => {
    state.tts = !state.tts;
    if (!state.tts && "speechSynthesis" in window) speechSynthesis.cancel();
    $("tts-button").style.color = state.tts ? "var(--accent)" : "";
    toast("Voice replies " + (state.tts ? "enabled" : "disabled"));
  });
  async function research(ticker, assetType = "stock", caller = "research") {
    const body = { ticker, asset_type: assetType, date: new Date().toISOString().slice(0,10) };
    const started = await api("/api/research", body);
    if (caller === "research") {
      $("research-state").textContent = "Running";
      $("research-placeholder").hidden = false;
      $("research-placeholder").textContent = "TradingAgents research is running. You can keep this page open while your humanoid prepares the report.";
      $("research-content").hidden = true;
    }
    setExpression("thinking");
    // Research may take minutes; polling has a bounded duration and never authorizes trading.
    for (let i = 0; i < 160; i++) {
      await new Promise(resolve => setTimeout(resolve, 1600));
      const job = await api("/api/research/" + encodeURIComponent(started.job_id));
      if (job.status === "completed") {
        setExpression("idle");
        if (caller === "research") {
          renderReport(job.result);
        } else {
          const summary = "TradingAgents finished reviewing " + ticker + ". Signal: " + (job.result.signal || "REVIEW") + ". Open Research for the complete report. This is not an order.";
          chatBubble("bot", summary);
          speak(summary);
          renderReport(job.result);
        }
        return job.result;
      }
      if (job.status === "failed") throw Error("TradingAgents run failed. Check the server configuration and secure logs.");
    }
    throw Error("Research timed out while waiting for TradingAgents.");
  }
  function renderReport(result) {
    $("research-state").textContent = "Completed";
    $("research-placeholder").hidden = true;
    const area = $("research-content");
    area.replaceChildren();
    area.hidden = false;
    const summary = document.createElement("div");
    summary.className = "report-entry";
    const heading = document.createElement("strong");
    heading.textContent = result.ticker + " · " + (result.signal || "REVIEW");
    const text = document.createElement("p");
    text.textContent = result.disclaimer || "AI-generated research, not a recommendation.";
    summary.append(heading,text);
    area.append(summary);
    Object.entries(result.reports || {}).forEach(([key,val]) => {
      const entry = document.createElement("div");
      entry.className = "report-entry";
      const h = document.createElement("strong"); h.textContent = key.replaceAll("_", " ").toUpperCase();
      const p = document.createElement("p"); p.textContent = String(val);
      entry.append(h,p); area.append(entry);
    });
  }
  $("research-form").addEventListener("submit", e => {
    e.preventDefault();
    perform(e.currentTarget, async () => {
      const ticker = $("ticker").value.trim().toUpperCase();
      if (!/^[A-Z0-9][A-Z0-9._:/-]{0,23}$/.test(ticker)) throw Error("Invalid ticker.");
      $("research-state").textContent = "Starting";
      await research(ticker, $("asset-type").value);
      toast("Research completed. All orders remain manual and paper-only.");
    });
  });
  function localResponse(question) {
    const q = question.toLowerCase();
    if (/\b(risk|safe|honeypot|rug|security)\b/.test(q)) {
      return (state.humanoid === "dirk"
        ? "Risk first: preserve capital and verify every input. "
        : "Research check: compare security findings across sources before trusting any signal. ")
        + "The Ncodex risk engine blocks missing or stale data, flagged honeypots, enabled mint/freeze authorities, concentrated ownership, low liquidity and excessive trade size. Passing these checks does NOT mean a token is safe or profitable.";
    }
    if (/\b(portfolio|balance|funds|positions|profit|pnl)\b/.test(q)) {
      if (!state.paper) return "I can't read your paper portfolio yet. Check the connection in Settings.";
      return "Your simulated cash is " + money(state.paper.cash_usd) + ", realized P&L is " + money(state.paper.realized_pnl_usd) + ", and you have " + Object.keys(state.paper.positions || {}).length + " open paper position(s). No exchange orders have been placed.";
    }
    if (/\b(buy|sell|trade|order|execute)\b/.test(q)) {
      return "I can guide a paper trade, but I won't execute a real order. Open Trade to fund your simulated wallet and review a synthetic buy or sell. You must approve each paper transaction.";
    }
    if (/\b(chatgpt|login|connect|model|tradingagents)\b/.test(q)) {
      return "TradingAgents supports ChatGPT subscription authorization using 'tradingagents login chatgpt' on your server. Once configured, use Research to run the analyst team. I don't ask for your ChatGPT credentials here.";
    }
    if (/\b(freqtrade|backtest|strategy|machine learning)\b/.test(q)) {
      return "Freqtrade offers dry-run strategies, backtesting and optional FreqAI training. This mobile app only monitors a configured dry-run instance. It does not enable exchange orders.";
    }
    return (state.humanoid === "dirk" ? "My focus is disciplined risk and trade planning. " : "My focus is market research and contrasting viewpoints. ") + "I can help with research, risk checks, your paper portfolio, ChatGPT integration, and strategy testing. For a TradingAgents market report, try 'Analyze AAPL' or open Research. My guided chat doesn't fabricate live market prices.";
  }
  async function sendQuestion(question) {
    const value = question.trim();
    if (!value) return;
    chatBubble("user", value);
    const match = value.match(/\b(?:analyze|research|review|look up|study)\s+([A-Za-z0-9][A-Za-z0-9._:/-]{0,23})\b/i);
    if (match) {
      const ticker = match[1].toUpperCase();
      const ans = "I'll request a TradingAgents report for " + ticker + " with your ChatGPT-linked server. No trade will be executed.";
      chatBubble("bot", ans);
      speak(ans);
      try { await research(ticker, /\b(crypto|btc|eth|sol)\b/i.test(value) ? "crypto" : "stock", "chat"); }
      catch(err) {
        const msg = "I can't run that analysis right now: " + err.message + ". Check Settings → Connectivity.";
        chatBubble("bot", msg); speak(msg);
      }
    } else {
      const ans = localResponse(value);
      chatBubble("bot", ans);
      speak(ans);
    }
  }
  $("chat-form").addEventListener("submit", async e => {
    e.preventDefault();
    const input = $("chat-input");
    const value = input.value;
    input.value = "";
    await sendQuestion(value);
  });
  document.querySelectorAll("[data-prompt]").forEach(b => b.addEventListener("click", () => sendQuestion(b.dataset.prompt)));
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (Recognition) {
    let recognition;
    $("mic").addEventListener("click", () => {
      if (state.listening && recognition) { recognition.stop(); return; }
      recognition = new Recognition();
      recognition.lang = navigator.language || "en-US";
      recognition.interimResults = true;
      recognition.continuous = false;
      recognition.onstart = () => { state.listening = true; $("mic").classList.add("listening"); };
      recognition.onresult = event => {
        const transcript = Array.from(event.results).map(r => r[0].transcript).join(" ");
        $("chat-input").value = transcript;
      };
      recognition.onerror = event => { toast("Microphone: " + event.error + ". You can type instead."); };
      recognition.onend = () => { state.listening = false; $("mic").classList.remove("listening"); $("chat-input").focus(); };
      try { recognition.start(); } catch { toast("Microphone is unavailable. Try typing your question."); }
    });
  } else {
    $("mic").addEventListener("click", () => toast("Speech transcription isn't supported by this browser. Type your question instead."));
  }
  refresh();
  if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost" || location.hostname === "127.0.0.1")) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
  window.ncodexAPI = api;
  window.ncodexNavigate = navigate;
})();