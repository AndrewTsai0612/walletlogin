/*
 * walletlogin 前端元件：顯示登入 QR Code，並在使用者用錢包 App 簽名後通知網站。
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
 * 選項：
 *   basePath      套件 API 的路徑，預設 "/walletlogin"
 *   onSuccess     登入成功時呼叫 (token, address)
 *   pollInterval  詢問登入狀態的間隔（毫秒），預設 1500
 *   debug         顯示 QR Code 的原始內容（開發測試用），預設 false
 *
 * 外觀可以用 CSS 變數調整，例如：
 *   #login { --wl-accent: #e91e63; --wl-qr-size: 200px; }
 */
(function () {
  "use strict";

  var STYLE = [
    ".wl{--wl-accent:#2f6fed;--wl-ok:#16a34a;--wl-error:#dc2626;--wl-muted:#6b7280;--wl-border:#e3e5e8;--wl-qr-size:240px;text-align:center}",
    ".wl-qr{width:var(--wl-qr-size);height:var(--wl-qr-size);margin:0 auto;padding:12px;box-sizing:border-box;background:#fff;border:1px solid var(--wl-border);border-radius:12px;display:flex;align-items:center;justify-content:center}",
    ".wl-qr svg{width:100%;height:100%}",
    ".wl-qr.wl-expired{opacity:.15}",
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

  function mount(target, options) {
    var root = typeof target === "string" ? document.querySelector(target) : target;
    if (!root) throw new Error("WalletLogin: 找不到元素 " + target);
    var opts = options || {};
    var basePath = (opts.basePath || "/walletlogin").replace(/\/$/, "");
    var pollInterval = opts.pollInterval || 1500;

    injectStyle();
    root.innerHTML = "";
    var box = el("div", "wl", root);
    var qrEl = el("div", "wl-qr", box);
    var statusEl = el("p", "wl-status", box);
    var countdownEl = el("p", "wl-countdown", box);
    var refreshBtn = el("button", "wl-refresh", box);
    refreshBtn.type = "button";
    refreshBtn.textContent = "重新產生 QR Code";
    refreshBtn.hidden = true;
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

    function renderQr(text) {
      var qr = qrcode(0, "M");
      qr.addData(text);
      qr.make();
      qrEl.innerHTML = qr.createSvgTag({ cellSize: 4, margin: 0, scalable: true });
      qrEl.classList.remove("wl-expired");
    }

    function showExpired() {
      stopTimers();
      qrEl.classList.add("wl-expired");
      setStatus("QR Code 已過期", "error");
      countdownEl.textContent = "";
      refreshBtn.hidden = false;
    }

    function post(path, body) {
      return fetch(basePath + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
    }

    function start() {
      stopTimers();
      refreshBtn.hidden = true;
      setStatus("正在產生登入 QR Code…");

      post("/session")
        .then(function (res) {
          if (!res.ok) throw new Error(res.status);
          return res.json();
        })
        .then(function (session) {
          renderQr(session.qr_payload);
          if (payloadEl) payloadEl.value = session.qr_payload;
          setStatus("請用錢包 App 掃描");

          var expiresAt = Date.now() + session.expires_in * 1000;
          var tick = function () {
            var left = Math.max(0, Math.round((expiresAt - Date.now()) / 1000));
            countdownEl.textContent =
              "QR Code 將在 " + Math.floor(left / 60) + ":" + String(left % 60).padStart(2, "0") + " 後失效";
            if (left === 0) showExpired();
          };
          tick();
          countdownTimer = setInterval(tick, 1000);
          pollTimer = setInterval(function () { poll(session); }, pollInterval);
        })
        .catch(function () {
          setStatus("無法連線到伺服器", "error");
          refreshBtn.hidden = false;
        });
    }

    function poll(session) {
      post("/status", { session_id: session.session_id, poll_token: session.poll_token })
        .then(function (res) {
          if (res.status === 404) return showExpired();
          if (!res.ok) return;
          return res.json().then(function (body) {
            if (body.status !== "ok") return;
            stopTimers();
            setStatus("簽名驗證成功，正在登入…", "ok");
            if (opts.onSuccess) opts.onSuccess(body.token, body.address);
          });
        })
        .catch(function () { /* 網路暫時不通，下次再試 */ });
    }

    refreshBtn.addEventListener("click", start);
    start();

    return { restart: start, destroy: function () { stopTimers(); root.innerHTML = ""; } };
  }

  window.WalletLogin = { mount: mount };
})();
