/*
 * walletlogin 前端元件：讓使用者用錢包 App 登入網站。
 *
 * 用法：
 *   <div id="login"></div>
 *   <script src="/walletlogin/walletlogin.js"></script>
 *   <script>
 *     WalletLogin.mount("#login", {
 *       onSuccess: function (token, address) { ... },  // 登入成功，token 為 JWT
 *     });
 *   </script>
 *
 * 兩種登入方式，由元件自動選擇：
 *   電腦：顯示 QR Code，用手機錢包 App 掃描（跨裝置）
 *   手機：顯示「用錢包 App 開啟」按鈕，簽名後 App 帶著兌換碼切回這個網頁（同一裝置）
 *
 * 選項：
 *   basePath      套件 API 的路徑，預設 "/walletlogin"
 *   onSuccess     登入成功時呼叫 (token, address)
 *   mode          "auto"（預設，依裝置自動選擇）、"qr"、"app"
 *   pollInterval  詢問登入狀態的間隔（毫秒），預設 1500
 *   debug         顯示 QR Code 的原始內容（開發測試用），預設 false
 *
 * 外觀可以用 CSS 變數調整，例如：
 *   #login { --wl-accent: #e91e63; --wl-qr-size: 200px; }
 */
(function () {
  "use strict";

  // App 簽名後切回網頁時，會把兌換碼放在網址的 # 之後（不會送到伺服器）
  var CODE_PARAM = "walletlogin_code";

  var STYLE = [
    ".wl{--wl-accent:#2f6fed;--wl-ok:#16a34a;--wl-error:#dc2626;--wl-muted:#6b7280;--wl-border:#e3e5e8;--wl-qr-size:240px;text-align:center}",
    ".wl-qr{width:var(--wl-qr-size);height:var(--wl-qr-size);margin:0 auto;padding:12px;box-sizing:border-box;background:#fff;border:1px solid var(--wl-border);border-radius:12px;display:flex;align-items:center;justify-content:center}",
    ".wl-qr svg{width:100%;height:100%}",
    ".wl-expired{opacity:.15;pointer-events:none}",
    ".wl-app-btn{display:inline-block;font-size:17px;font-weight:600;text-decoration:none;border-radius:10px;padding:14px 28px;background:var(--wl-accent);color:#fff}",
    ".wl-hint{color:var(--wl-muted);font-size:13px;margin:12px 0 0}",
    ".wl-switch{font:inherit;font-size:13px;background:none;border:none;color:var(--wl-accent);cursor:pointer;margin-top:12px;padding:4px}",
    ".wl-status{margin:20px 0 0;font-size:15px;min-height:24px}",
    ".wl-status.wl-ok{color:var(--wl-ok)}",
    ".wl-status.wl-error{color:var(--wl-error)}",
    ".wl-countdown{color:var(--wl-muted);font-size:13px;margin:4px 0 0}",
    ".wl-refresh{font:inherit;border:none;border-radius:8px;padding:10px 18px;cursor:pointer;background:var(--wl-accent);color:#fff;margin-top:8px}",
    ".wl-debug{margin-top:20px;text-align:left;font-size:12px;color:var(--wl-muted)}",
    ".wl-debug textarea{width:100%;height:90px;margin-top:6px;box-sizing:border-box;font:11px ui-monospace,Menlo,monospace}",
  ].join("\n");

  function injectStyle() {
    if (document.getElementById("wl-style")) return;
    var style = document.createElement("style");
    style.id = "wl-style";
    style.textContent = STYLE;
    document.head.appendChild(style);
  }

  function el(tag, className, parent) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (parent) parent.appendChild(node);
    return node;
  }

  function isMobile() {
    if (navigator.userAgentData && typeof navigator.userAgentData.mobile === "boolean") {
      return navigator.userAgentData.mobile;
    }
    return /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
  }

  // 同一裝置登入時，App 會開啟新的分頁，所以 poll_token 要存在同網站分頁共用的 localStorage
  function savePending(key, session) {
    try {
      localStorage.setItem(key, JSON.stringify({
        session_id: session.session_id,
        poll_token: session.poll_token,
        expires_at: Date.now() + session.expires_in * 1000,
      }));
    } catch (e) { /* 無痕模式等情況可能無法使用 */ }
  }

  function loadPending(key) {
    try {
      var pending = JSON.parse(localStorage.getItem(key));
      if (pending && pending.expires_at > Date.now()) return pending;
    } catch (e) { /* 忽略 */ }
    return null;
  }

  function clearPending(key) {
    try { localStorage.removeItem(key); } catch (e) { /* 忽略 */ }
  }

  function readCodeFromUrl() {
    var match = location.hash.match(new RegExp("[#&]" + CODE_PARAM + "=([^&]+)"));
    return match ? decodeURIComponent(match[1]) : null;
  }

  function removeCodeFromUrl() {
    history.replaceState(null, "", location.pathname + location.search);
  }

  function mount(target, options) {
    var root = typeof target === "string" ? document.querySelector(target) : target;
    if (!root) throw new Error("WalletLogin: 找不到元素 " + target);
    var opts = options || {};
    var basePath = (opts.basePath || "/walletlogin").replace(/\/$/, "");
    var pollInterval = opts.pollInterval || 1500;
    var pendingKey = "walletlogin:pending:" + basePath;
    var mode = opts.mode === "qr" || opts.mode === "app" ? opts.mode : isMobile() ? "app" : "qr";

    injectStyle();
    root.innerHTML = "";
    var box = el("div", "wl", root);
    var mainEl = el("div", null, box);
    var statusEl = el("p", "wl-status", box);
    var countdownEl = el("p", "wl-countdown", box);
    var refreshBtn = el("button", "wl-refresh", box);
    refreshBtn.type = "button";
    refreshBtn.textContent = "重新產生";
    refreshBtn.hidden = true;
    var switchBtn = el("button", "wl-switch", box);
    switchBtn.type = "button";
    var payloadEl = null;
    if (opts.debug) {
      var details = el("details", "wl-debug", box);
      el("summary", null, details).textContent = "開發用：QR Code 內容";
      payloadEl = el("textarea", null, details);
      payloadEl.readOnly = true;
    }

    var pollTimer = null;
    var countdownTimer = null;

    function setStatus(text, kind) {
      statusEl.textContent = text;
      statusEl.className = "wl-status" + (kind ? " wl-" + kind : "");
    }

    function stopTimers() {
      clearInterval(pollTimer);
      clearInterval(countdownTimer);
    }

    function post(path, body) {
      return fetch(basePath + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
    }

    function succeed(body) {
      stopTimers();
      clearPending(pendingKey);
      mainEl.innerHTML = "";
      switchBtn.hidden = true;
      countdownEl.textContent = "";
      setStatus("簽名驗證成功，正在登入…", "ok");
      if (opts.onSuccess) opts.onSuccess(body.token, body.address);
    }

    function showExpired() {
      stopTimers();
      clearPending(pendingKey);
      mainEl.classList.add("wl-expired");
      setStatus(mode === "app" ? "登入連結已過期" : "QR Code 已過期", "error");
      countdownEl.textContent = "";
      refreshBtn.hidden = false;
    }

    function startCountdown(expiresIn) {
      var expiresAt = Date.now() + expiresIn * 1000;
      var label = mode === "app" ? "登入連結" : "QR Code";
      var tick = function () {
        var left = Math.max(0, Math.round((expiresAt - Date.now()) / 1000));
        countdownEl.textContent =
          label + " 將在 " + Math.floor(left / 60) + ":" + String(left % 60).padStart(2, "0") + " 後失效";
        if (left === 0) showExpired();
      };
      tick();
      countdownTimer = setInterval(tick, 1000);
    }

    // ---------- 電腦：顯示 QR Code ----------

    function renderQr(session) {
      var qr = qrcode(0, "M");
      qr.addData(session.qr_payload);
      qr.make();
      var qrEl = el("div", "wl-qr", mainEl);
      qrEl.innerHTML = qr.createSvgTag({ cellSize: 4, margin: 0, scalable: true });
      setStatus("請用錢包 App 掃描");
      // 跨裝置：一直詢問狀態，手機簽名後就會變成 ok
      pollTimer = setInterval(function () { poll(session, null); }, pollInterval);
    }

    // ---------- 手機：顯示「用錢包 App 開啟」按鈕 ----------

    function renderAppButton(session) {
      savePending(pendingKey, session);
      var btn = el("a", "wl-app-btn", mainEl);
      btn.href = session.app_link;
      btn.textContent = "用錢包 App 開啟";
      el("p", "wl-hint", mainEl).textContent = "簽名完成後會自動回到這個網頁";
      setStatus("");
      // 同一裝置：不在這裡詢問狀態，等 App 帶著兌換碼切回網頁（見 completeWithCode）
    }

    function start() {
      stopTimers();
      refreshBtn.hidden = true;
      mainEl.innerHTML = "";
      mainEl.classList.remove("wl-expired");
      switchBtn.hidden = false;
      switchBtn.textContent = mode === "app" ? "改用 QR Code（用另一支手機掃描）" : "改用這支手機上的錢包 App";
      setStatus("正在準備登入…");

      var body = mode === "app"
        ? { mode: "same_device", return_url: location.href.split("#")[0] }
        : null;

      post("/session", body)
        .then(function (res) {
          if (!res.ok) throw new Error(res.status);
          return res.json();
        })
        .then(function (session) {
          if (payloadEl) payloadEl.value = session.qr_payload;
          if (mode === "app") renderAppButton(session);
          else renderQr(session);
          startCountdown(session.expires_in);
        })
        .catch(function () {
          setStatus("無法連線到伺服器", "error");
          refreshBtn.hidden = false;
        });
    }

    function poll(session, code) {
      var body = { session_id: session.session_id, poll_token: session.poll_token };
      if (code) body.code = code;
      return post("/status", body)
        .then(function (res) {
          if (res.status === 404) { showExpired(); return; }
          if (!res.ok) throw new Error(res.status);
          return res.json().then(function (result) {
            if (result.status === "ok") succeed(result);
          });
        });
    }

    // App 簽名後切回網頁：用 localStorage 中的 poll_token ＋ 網址中的兌換碼完成登入
    function completeWithCode() {
      var code = readCodeFromUrl();
      if (!code) return false;
      removeCodeFromUrl();
      var pending = loadPending(pendingKey);
      if (!pending) {
        setStatus("找不到登入請求，請在發起登入的瀏覽器重新操作", "error");
        refreshBtn.hidden = false;
        return true;
      }
      stopTimers();
      mainEl.innerHTML = "";
      switchBtn.hidden = true;
      setStatus("正在完成登入…");
      poll(pending, code).catch(function () {
        clearPending(pendingKey);
        setStatus("登入失敗，請重新操作", "error");
        refreshBtn.hidden = false;
      });
      return true;
    }

    refreshBtn.addEventListener("click", start);
    switchBtn.addEventListener("click", function () {
      mode = mode === "app" ? "qr" : "app";
      start();
    });
    // 如果 App 切回的是原本的分頁（只改變 # 之後的內容），也要能完成登入
    window.addEventListener("hashchange", completeWithCode);

    if (!completeWithCode()) start();

    return { restart: start, destroy: function () { stopTimers(); root.innerHTML = ""; } };
  }

  window.WalletLogin = { mount: mount };
})();
