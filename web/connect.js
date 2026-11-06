"use strict";
/* Owner-only subscription sign-in. Tokens, PKCE verifier and refresh tokens
   stay in TradingAgents on the host, never in mobile browser storage. */
(() => {
  const $ = (id) => document.getElementById(id);
  const signIn = $("chatgpt-start");
  if (!signIn) return;
  const notice = $("connect-notice");
  const statusChip = $("connect-status");
  const accountInfo = $("connect-account-info");
  const flowPanel = $("connect-auth-flow");
  const authorize = $("connect-auth-link");
  const callbackForm = $("chatgpt-callback-form");
  const callbackField = $("chatgpt-callback");
  const disconnect = $("chatgpt-disconnect");
  const connectedPanel = $("connect-connected");
  let currentFlow = null;
  let busy = false;
  let lastStatus = null;

  function mark(state, message) {
    statusChip.dataset.state = state;
    statusChip.textContent = message;
  }
  function showMessage(message) {
    notice.textContent = message;
  }
  function allowedAuthorizeURL(value) {
    if (typeof value !== "string") return null;
    try {
      const url = new URL(value);
      if (url.protocol === "https:" && url.hostname === "auth.openai.com"
          && url.pathname === "/api/accounts/authorize") return url.href;
    } catch (_) {}
    return null;
  }
  function render(status) {
    lastStatus = status;
    const enabled = status.enabled === true;
    const installed = status.installed === true;
    const saved = status.session_saved === true;
    const stage = status.flow_status || "unavailable";
    const inProgress = ["starting","awaiting_callback","finishing"].includes(stage);
    currentFlow = inProgress ? status.flow_id : null;
    signIn.disabled = busy || !enabled || !installed || inProgress;
    signIn.textContent = saved ? "Reconnect with ChatGPT ↗" : "Continue with ChatGPT ↗";
    connectedPanel.hidden = !saved;
    disconnect.hidden = !saved || !enabled || inProgress;

    if (!enabled) {
      mark("unavailable","SETUP NEEDED");
      accountInfo.textContent = "This server has not enabled owner-only subscription login.";
      showMessage("Configure TradingAgents and the owner access token on a trusted HTTPS host. See setup instructions below.");
    } else if (!installed) {
      mark("unavailable","INSTALL REQUIRED");
      accountInfo.textContent = "TradingAgents is not installed on this server.";
      showMessage("Install TradingAgents on the host before authorizing your ChatGPT plan.");
    } else if (stage === "starting") {
      mark("awaiting_callback","PREPARING");
      showMessage("Preparing a secure ChatGPT authorization link…");
    } else if (stage === "awaiting_callback") {
      mark("awaiting_callback","SIGN-IN OPEN");
      showMessage("Open the official sign-in link. On mobile, paste the final 127.0.0.1 URL below.");
    } else if (stage === "finishing") {
      mark("awaiting_callback","VERIFYING");
      showMessage("TradingAgents is verifying the callback and saving your connection on the server…");
    } else if (stage === "failed") {
      mark("unavailable","NOT CONNECTED");
      showMessage(status.error || "Connection failed. You can try again.");
    } else if (stage === "connected" || saved) {
      mark("connected","SAVED LOGIN");
      showMessage("Authorization is stored on the host. Start a research request to verify that model access is working.");
    } else {
      mark("unavailable","NOT CONNECTED");
      showMessage("Ready for subscription authorization. Sign in through the official OpenAI page.");
    }

    if (saved) {
      accountInfo.textContent = (status.account_email ? "ChatGPT account: " + status.account_email + ". " : "")
        + "Saved credentials are private to this TradingAgents server and have not been validated with a research request.";
    } else if (enabled && installed) {
      accountInfo.textContent = "NOVA will use TradingAgents for analysis only. Your password and subscription tokens are never entered here.";
    }

    const authURL = stage === "awaiting_callback" ? allowedAuthorizeURL(status.authorize_url) : null;
    flowPanel.hidden = !authURL && stage !== "finishing";
    if (authURL) authorize.href = authURL;
    if (stage === "finishing") {
      authorize.removeAttribute("href");
      authorize.textContent = "Verifying your authorization…";
    } else {
      authorize.textContent = "Open official ChatGPT sign-in ↗";
    }
    callbackForm.querySelector("button").disabled = busy || stage !== "awaiting_callback";
    callbackField.disabled = stage !== "awaiting_callback";
  }
  async function loadStatus() {
    try {
      const status = await window.ncodexAPI("/api/chatgpt/status");
      render(status);
    } catch (err) {
      mark("unavailable","OWNER ACCESS");
      signIn.disabled = true;
      flowPanel.hidden = true;
      connectedPanel.hidden = true;
      disconnect.hidden = true;
      currentFlow = null;
      accountInfo.textContent = "Enter your private server access token in Settings before using the ChatGPT connection page.";
      showMessage(err.message || "Connection unavailable");
    }
  }
  signIn.addEventListener("click", async () => {
    if (busy) return;
    busy = true;signIn.disabled=true;
    showMessage("Starting ChatGPT authorization…");
    try {
      await window.ncodexAPI("/api/chatgpt/start", {approved:true});
      await loadStatus();
    } catch (err) {
      showMessage("Could not start sign-in: " + err.message);
    } finally {busy=false;}
  });
  callbackForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy || !currentFlow) return;
    const callbackURL = callbackField.value.trim();
    callbackField.value = ""; // authorization codes must not linger in the DOM
    busy=true;
    showMessage("Validating the callback…");
    try {
      await window.ncodexAPI("/api/chatgpt/complete", {
        flow_id: currentFlow, callback_url: callbackURL
      });
      await loadStatus();
    } catch (err) {
      showMessage("Callback rejected: " + err.message);
    } finally {busy=false;}
  });
  disconnect.addEventListener("click", async () => {
    if (busy) return;
    if (!window.confirm("Disconnect this ChatGPT account from TradingAgents on this server?")) return;
    busy=true;
    try {
      await window.ncodexAPI("/api/chatgpt/disconnect", {approved:true});
      await loadStatus();
      showMessage("TradingAgents sign-in removed from the host.");
    } catch (err) {
      showMessage("Unable to disconnect: " + err.message);
    } finally {busy=false;}
  });
  window.addEventListener("ncodex:access-changed",loadStatus);
  window.addEventListener("hashchange",() => {
    if (location.hash === "#connect") loadStatus();
  });
  document.querySelectorAll('[data-goto="connect"]').forEach(b => b.addEventListener("click",loadStatus));
  // Poll while on the sign-in screen, but never continue an OAuth flow by itself.
  setInterval(() => {
    if (location.hash === "#connect" && !busy &&
        (currentFlow || (lastStatus && lastStatus.flow_status === "finishing"))) loadStatus();
  }, 1800);
  if (location.hash === "#connect") loadStatus();
})();

