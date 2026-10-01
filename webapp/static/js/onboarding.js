/* AI Audio Studio — onboarding cho người mới (modal nhiều bước).
   Hai chế độ, theo /api/info.hosted:
   - Bản web (HF Space): trình duyệt tự đo máy → tải bộ cài đúng HĐH → hướng dẫn cài
     → dò xem app đã chạy trên máy (127.0.0.1) chưa.
   - Bản đã cài trên máy: server đo cấu hình thật → tải model lần đầu → thử tạo giọng.
   Dùng chung $, $$, showTab, toast, escapeHtml từ app.js. */
(function () {
  const SEEN_KEY = "vieneu_onboarded";
  const LOCAL_URL = "http://127.0.0.1:8001";
  const OS_LABEL = { macos: "macOS", windows: "Windows", linux: "Linux" };

  const S = {
    step: 0, hosted: false, facts: null, checks: null, verdict: null,
    os: null, installers: null, devUrl: "", localFound: null,
    model: null, modelErr: null, startedAt: 0, poll: null,
  };

  const STEPS = () => [
    { key: "intro", label: "Giới thiệu" },
    { key: "check", label: "Kiểm tra máy" },
    S.hosted ? { key: "install", label: "Tải & cài đặt" } : { key: "model", label: "Tải model" },
    { key: "done", label: "Hoàn tất" },
  ];

  // ── Đo cấu hình ───────────────────────────────────────
  const GB = 1024 ** 3;

  async function factsFromServer() {
    const d = await (await fetch("/api/system")).json();
    if (d.hosted) return null;
    return {
      source: "server", platform: d.platform, mobile: false,
      osLabel: d.os_version && d.platform === "macos" ? `macOS ${d.os_version}` : d.os,
      osVersion: d.os_version, arch: d.arch, cpu: d.cpu, cores: d.cores,
      ramGB: d.ram_bytes ? d.ram_bytes / GB : null, ramLowerBound: false,
      diskGB: d.disk_free_bytes != null ? d.disk_free_bytes / GB : null,
      online: navigator.onLine,
    };
  }

  async function factsFromBrowser() {
    const ua = navigator.userAgent;
    const uad = navigator.userAgentData;
    let platform = "unknown";
    if (/Windows/.test(ua)) platform = "windows";
    else if (/Macintosh|Mac OS X/.test(ua)) platform = "macos";
    else if (/Linux|X11|CrOS/.test(ua) && !/Android/.test(ua)) platform = "linux";
    let mobile = /Android|iPhone|iPad|iPod|Mobile/i.test(ua) || !!(uad && uad.mobile);
    if (platform === "macos" && navigator.maxTouchPoints > 1) mobile = true; // iPadOS giả làm Mac
    let osLabel = OS_LABEL[platform] || "Không rõ", osVersion = null, arch = null, bitness = null;
    if (uad && uad.getHighEntropyValues) {
      try {
        const h = await uad.getHighEntropyValues(["platformVersion", "architecture", "bitness"]);
        arch = h.architecture || null; bitness = h.bitness || null;
        const major = parseInt(h.platformVersion, 10);
        if (platform === "windows" && !isNaN(major)) osLabel = major >= 13 ? "Windows 11" : major > 0 ? "Windows 10" : "Windows 7/8";
        if (platform === "macos" && h.platformVersion) { osVersion = h.platformVersion; osLabel = `macOS ${osVersion}`; }
      } catch {}
    }
    let gpu = "";
    try {
      const gl = document.createElement("canvas").getContext("webgl");
      const ext = gl && gl.getExtension("WEBGL_debug_renderer_info");
      gpu = gl ? String(gl.getParameter(ext ? ext.UNMASKED_RENDERER_WEBGL : gl.RENDERER)) : "";
    } catch {}
    if (platform === "macos" && !arch) {
      if (/Apple (M\d|GPU)/i.test(gpu)) arch = "arm";
      else if (/Intel|AMD|Radeon|NVIDIA/i.test(gpu)) arch = "x86";
    }
    if (bitness === "32") arch = "x86-32";
    const mem = navigator.deviceMemory; // Chrome/Edge, làm tròn và tối đa 8
    return {
      source: "browser", platform, mobile, osLabel, osVersion, arch,
      cpu: /Apple M\d/i.test(gpu) ? gpu.replace(/^.*?(Apple M\d[^,)]*).*$/i, "$1") : "",
      cores: navigator.hardwareConcurrency || null,
      ramGB: mem || null, ramLowerBound: mem >= 8,
      diskGB: null, online: navigator.onLine,
    };
  }

  // Mỗi dòng: [trạng thái ok|warn|fail|info, tiêu đề, giá trị, ghi chú]
  function evaluate(f) {
    const rows = [];
    const isArm = /arm|aarch64/i.test(f.arch || "");
    const is32 = /32|i[3-6]86/.test(f.arch || "") && !/64/.test(f.arch || "");

    if (f.mobile) {
      rows.push(["fail", "Thiết bị", "Điện thoại / máy tính bảng", "Phần mềm chỉ cài được trên máy tính macOS, Windows hoặc Linux."]);
    } else if (f.platform === "macos") {
      const major = parseInt(f.osVersion, 10);
      if (!f.osVersion) rows.push(["ok", "Hệ điều hành", "macOS", "Cần macOS 12 (Monterey) trở lên."]);
      else if (major >= 12) rows.push(["ok", "Hệ điều hành", f.osLabel, "Được hỗ trợ."]);
      else if (major === 11) rows.push(["warn", "Hệ điều hành", f.osLabel, "Có thể chạy, nhưng nên cập nhật lên macOS 12 trở lên."]);
      else rows.push(["fail", "Hệ điều hành", f.osLabel, "Quá cũ — cần macOS 12 (Monterey) trở lên."]);
    } else if (f.platform === "windows") {
      const old = /7\/8/.test(f.osLabel);
      rows.push([old ? "fail" : "ok", "Hệ điều hành", f.osLabel, old ? "Cần Windows 10 hoặc 11 (64-bit)." : "Được hỗ trợ (Windows 10/11 64-bit)."]);
    } else if (f.platform === "linux") {
      rows.push(["ok", "Hệ điều hành", f.osVersion && f.source === "server" ? f.osVersion : "Linux", "Được hỗ trợ (64-bit)."]);
    } else {
      rows.push(["warn", "Hệ điều hành", "Không nhận diện được", "Phần mềm chạy trên macOS 12+, Windows 10/11, Linux 64-bit."]);
    }

    if (!f.mobile) {
      const cpu = f.cpu ? ` · ${f.cpu}` : "";
      if (is32) rows.push(["fail", "Chip / kiến trúc", "32-bit", "Cần máy 64-bit."]);
      else if (f.platform === "macos" && isArm) rows.push(["ok", "Chip", "Apple Silicon" + cpu, "Chip M-series — chạy nhanh."]);
      else if (f.platform === "macos" && f.arch) rows.push(["ok", "Chip", "Intel" + cpu, "Chạy được, chậm hơn chip Apple M-series."]);
      else if (f.platform === "windows" && isArm) rows.push(["warn", "Chip", "ARM" + cpu, "Windows trên chip ARM chưa được kiểm thử đầy đủ."]);
      else if (f.arch) rows.push(["ok", "Chip", "64-bit" + cpu, "Được hỗ trợ — không cần card đồ họa."]);
      else rows.push(["info", "Chip", "Không đo được", "Cần máy 64-bit; không cần card đồ họa."]);
    }

    if (f.ramGB == null) {
      rows.push(["warn", "RAM", "Trình duyệt không cho đo", "Cần tối thiểu 8 GB. Xem: 🍎 → Giới thiệu về máy này (Mac) hoặc Cài đặt → Hệ thống → Giới thiệu (Windows)."]);
    } else {
      const v = f.ramLowerBound ? "≥ 8 GB" : `${Math.round(f.ramGB)} GB`;
      if (f.ramGB >= 7.5) rows.push(["ok", "RAM", v, "Đủ để chạy mượt."]);
      else if (f.ramGB >= 4) rows.push(["warn", "RAM", v, "Chạy được nhưng có thể chậm — nên đóng bớt ứng dụng khác."]);
      else rows.push(["fail", "RAM", v, "Không đủ — cần tối thiểu 4 GB, khuyến nghị 8 GB."]);
    }

    if (f.cores != null) {
      if (f.cores >= 4) rows.push(["ok", "CPU", `${f.cores} luồng`, "Đủ mạnh."]);
      else rows.push(["warn", "CPU", `${f.cores} luồng`, "Sinh giọng sẽ chậm — khuyến nghị từ 4 luồng."]);
    }

    if (f.diskGB == null) rows.push(["info", "Ổ đĩa trống", "Cần khoảng 5 GB", "Cho thư viện và model giọng nói."]);
    else if (f.diskGB >= 5) rows.push(["ok", "Ổ đĩa trống", `${Math.round(f.diskGB)} GB`, "Đủ chỗ cho thư viện và model."]);
    else if (f.diskGB >= 2) rows.push(["warn", "Ổ đĩa trống", `${f.diskGB.toFixed(1)} GB`, "Hơi ít — nên dọn để còn khoảng 5 GB."]);
    else rows.push(["fail", "Ổ đĩa trống", `${f.diskGB.toFixed(1)} GB`, "Không đủ — cần khoảng 5 GB."]);

    rows.push(f.online
      ? ["ok", "Internet", "Đang kết nối", "Lần đầu cần mạng để tải; sau đó chạy offline."]
      : ["fail", "Internet", "Mất kết nối", "Lần đầu cần Internet để tải thư viện và model."]);

    const verdict = rows.some((r) => r[0] === "fail") ? "fail" : rows.some((r) => r[0] === "warn") ? "warn" : "ok";
    return { rows, verdict };
  }

  // ── Khung hiển thị ───────────────────────────────────
  const ICON = { ok: "✅", warn: "⚠️", fail: "❌", info: "ℹ️" };

  function powerNote(compact) {
    return `<div class="onb-note">
      <div class="onb-note-title">💻 Đây là phần mềm chạy trên máy tính của bạn</div>
      <ul>
        <li><b>Máy bật + app đang chạy</b> → dùng được giao diện, và các phần mềm khác (n8n, Make, script, OBS...) gọi được <b>API</b> tại <code>${LOCAL_URL}</code>.</li>
        <li><b>Tắt máy, máy ngủ hoặc thoát app</b> → giao diện và API ngừng hoạt động. Mở lại icon <b>AI Audio Studio</b> trên Desktop (hoặc bật “tự chạy khi mở máy”) là dùng tiếp.</li>
        ${compact ? "" : `<li>Giọng nói được xử lý ngay trên máy bạn, không gửi lên mạng. Sau lần đầu có thể chạy offline.</li>
        <li>API mặc định chỉ dành cho phần mềm <b>trên cùng máy này</b>.</li>`}
      </ul>
    </div>`;
  }

  function renderIntro() {
    return `<h2 class="onb-h" id="onb-title">Chào mừng đến AI Audio Studio 👋</h2>
      <p class="onb-lead">Biến văn bản tiếng Việt thành giọng nói tự nhiên, clone giọng từ 3–5 giây audio, tạo hội thoại nhiều nhân vật — và xuất API cho phần mềm khác dùng.</p>
      ${powerNote(false)}
      <p class="onb-sub">${S.hosted
        ? "Chỉ 3 bước: kiểm tra máy → tải bộ cài → cài và thử tạo giọng."
        : "Chỉ 3 bước: kiểm tra máy → tải model giọng nói (lần đầu) → thử tạo giọng."}</p>`;
  }

  function renderCheck() {
    let html = `<h2 class="onb-h" id="onb-title">Kiểm tra cấu hình máy</h2>
      <p class="onb-lead">${S.hosted
        ? "Kiểm tra nhanh máy bạn đang dùng có đủ điều kiện cài phần mềm không. Hãy mở trang này <b>trên chính máy tính sẽ cài</b>."
        : "Đo cấu hình thật của máy đang chạy phần mềm."}</p>`;
    if (!S.checks) {
      return html + `<div class="onb-center"><button class="btn btn-primary" id="onb-run-check" type="button">🔍 Kiểm tra cấu hình</button>
        <p class="hint">Yêu cầu: macOS 12+ (chip Apple M hoặc Intel) · Windows 10/11 64-bit · Linux 64-bit · RAM 8 GB · ổ trống ~5 GB · không cần card đồ họa.</p></div>`;
    }
    const V = {
      ok: ["ok", "🎉 Máy bạn đủ điều kiện chạy AI Audio Studio."],
      warn: ["warn", "👍 Máy chạy được, xem lưu ý ⚠️ bên dưới."],
      fail: ["fail", "Máy này chưa đủ điều kiện — xem mục ❌ bên dưới."],
    }[S.checks.verdict];
    html += `<div class="onb-verdict ${V[0]}">${V[1]}</div>
      <div class="onb-checks">${S.checks.rows.map(([st, t, v, n]) => `
        <div class="onb-row ${st}"><span class="onb-ico">${ICON[st]}</span>
          <div><div class="onb-row-head"><b>${t}</b><span>${escapeHtml(String(v))}</span></div>
          <div class="onb-row-note">${n}</div></div></div>`).join("")}
      </div>
      <div class="onb-center"><button class="btn btn-ghost btn-sm" id="onb-run-check" type="button">↻ Kiểm tra lại</button></div>`;
    return html;
  }

  const INSTALL_STEPS = {
    macos: [
      "Bấm <b>Tải bộ cài</b> → nhấp đúp file <code>AI-Audio-Studio-macOS.zip</code> trong thư mục Downloads để giải nén.",
      "Chuyển thư mục vừa giải nén sang chỗ cố định (vd: <b>Documents</b>) — đừng xóa thư mục này sau khi cài.",
      "Nhấp đúp <code>install.command</code>. Nếu macOS chặn “nhà phát triển không xác định”: <b>chuột phải → Open → Open</b> (hoặc Cài đặt hệ thống → Quyền riêng tư & Bảo mật → <b>Vẫn mở</b>).",
      "Cửa sổ Terminal tự cài (5–10 phút lần đầu). Khi hỏi <i>tự chạy khi mở máy?</i> nên gõ <b>y</b> để máy bật là API sẵn sàng.",
      "Trình duyệt tự mở <code>" + LOCAL_URL + "</code> — xong! Lần sau mở icon <b>AI Audio Studio</b> trên Desktop.",
    ],
    windows: [
      "Bấm <b>Tải bộ cài</b> → chuột phải file <code>AI-Audio-Studio-Windows.zip</code> → <b>Extract All</b> (Giải nén tất cả). Đừng chạy thẳng trong file zip.",
      "Chuyển thư mục vừa giải nén sang chỗ cố định (vd: <b>Documents</b>).",
      "Nhấp đúp <code>install.bat</code>. Nếu hiện “Windows protected your PC”: bấm <b>More info → Run anyway</b>.",
      "Cửa sổ đen tự cài (5–10 phút lần đầu). Khi hỏi <i>TU CHAY khi mo may?</i> gõ <b>y</b> rồi Enter; hỏi <i>Khoi chay ngay?</i> bấm Enter.",
      "Trình duyệt mở <code>" + LOCAL_URL + "</code> — xong! Lần sau mở icon <b>AI Audio Studio</b> trên Desktop.",
    ],
    linux: [
      "Bấm <b>Tải bộ cài</b> rồi giải nén <code>AI-Audio-Studio-Linux.zip</code> vào chỗ cố định.",
      "Mở Terminal trong thư mục đó, chạy <code>bash install.sh</code>.",
      "Chờ cài xong (5–10 phút lần đầu), chọn có tự chạy khi mở máy nếu muốn.",
      "Mở <code>" + LOCAL_URL + "</code>. Icon trên Desktop lần đầu có thể cần chuột phải → <b>Allow Launching</b>.",
    ],
  };

  function fmtSize(b) { return b ? ` (${(b / 1024 / 1024).toFixed(1)} MB)` : ""; }

  function renderInstall() {
    const os = S.os || "macos";
    const inst = S.installers && S.installers[os];
    const tabs = Object.keys(OS_LABEL).map((k) =>
      `<button class="tab ${k === os ? "active" : ""}" data-onb-os="${k}" type="button">${k === "macos" ? "🍎" : k === "windows" ? "🪟" : "🐧"} ${OS_LABEL[k]}</button>`).join("");
    let dl;
    if (!S.installers) dl = `<span class="hint"><span class="spinner"></span> Đang kiểm tra bộ cài...</span>`;
    else if (inst && inst.available) dl = `<a class="btn btn-primary" id="onb-dl" href="${escapeHtml(inst.url)}" download>⬇ Tải bộ cài ${OS_LABEL[os]}${fmtSize(inst.size)}</a>`;
    else dl = `<button class="btn btn-primary" disabled>⬇ Tải bộ cài ${OS_LABEL[os]}</button>
      <span class="hint">Bộ cài ${OS_LABEL[os]} đang được cập nhật${S.devUrl ? ` — nhắn <a href="${escapeHtml(S.devUrl)}" target="_blank" rel="noopener">Đặng Hữu Sơn</a> để nhận link` : ""}.</span>`;
    return `<h2 class="onb-h" id="onb-title">Tải bộ cài &amp; cài đặt</h2>
      <p class="onb-lead">${S.facts && S.facts.platform === os ? `Đã chọn sẵn theo máy bạn (${escapeHtml(S.facts.osLabel)}).` : "Chọn hệ điều hành của máy sẽ cài."}</p>
      <div class="tabs sub-tabs">${tabs}</div>
      <div class="actions onb-dl-row">${dl}</div>
      <ol class="onb-install">${INSTALL_STEPS[os].map((s) => `<li>${s}</li>`).join("")}</ol>`;
  }

  function renderModel() {
    const st = S.model || {};
    let box;
    if (st.loaded) box = `<div class="onb-verdict ok">✅ Model giọng nói đã sẵn sàng trên máy bạn.</div>`;
    else if (S.modelErr || st.error) box = `<div class="onb-verdict fail">❌ Tải model lỗi: ${escapeHtml(S.modelErr || st.error)}</div>
      <div class="onb-center"><button class="btn btn-primary" id="onb-load" type="button">↻ Thử lại</button>
      <p class="hint">Kiểm tra Internet rồi thử lại. Chi tiết xem ở <b>Phiên bản &amp; Logs</b>.</p></div>`;
    else if (st.loading || S.poll) {
      const sec = S.startedAt ? Math.round((Date.now() - S.startedAt) / 1000) : 0;
      box = `<div class="onb-progress"><span class="spinner"></span>
        <div><b>Đang tải và khởi động model...</b> <span class="meta" id="onb-elapsed">${sec}s</span>
        <div class="hint">Lần đầu cần tải model từ Internet, mất vài phút tùy tốc độ mạng. Có thể để cửa sổ này chạy.</div></div></div>
        <div class="onb-bar"><span></span></div>`;
    } else box = `<div class="onb-center"><button class="btn btn-primary" id="onb-load" type="button">⬇ Tải model giọng nói</button>
      <p class="hint">Chỉ cần làm một lần. Model lưu trên máy, các lần sau mở app là dùng được ngay, kể cả khi không có mạng.</p></div>`;
    return `<h2 class="onb-h" id="onb-title">Tải model giọng nói</h2>
      <p class="onb-lead">Phần mềm đã được cài trên máy bạn 🎉. Bước cuối: tải model AI VieNeu-TTS về máy để sinh giọng offline.</p>
      ${box}`;
  }

  function renderDone() {
    if (S.hosted) {
      let found = "";
      if (S.localFound === true) found = `<div class="onb-verdict ok">✅ Đã thấy AI Audio Studio đang chạy trên máy bạn!</div>`;
      else if (S.localFound === false) found = `<div class="onb-verdict warn">Chưa thấy app chạy trên máy. Hãy chắc chắn đã cài xong và mở icon <b>AI Audio Studio</b> trên Desktop, rồi kiểm tra lại.</div>`;
      return `<h2 class="onb-h" id="onb-title">Cài xong? Mở app trên máy bạn</h2>
        <p class="onb-lead">Sau khi cài, app chạy tại <code>${LOCAL_URL}</code> trên máy của bạn.</p>
        ${found}
        <div class="actions onb-center-row">
          <button class="btn btn-secondary" id="onb-find" type="button">🔎 Kiểm tra app trên máy</button>
          <a class="btn btn-primary" href="${LOCAL_URL}" target="_blank" rel="noopener">Mở AI Audio Studio ↗</a>
        </div>
        ${powerNote(true)}
        <p class="onb-sub">Chưa cài cũng được — bấm <b>Thử bản web</b> để nghe thử ngay trên trang này.</p>`;
    }
    return `<div class="onb-hero">🎉</div>
      <h2 class="onb-h onb-center" id="onb-title">Thành công! Mọi thứ đã sẵn sàng</h2>
      <p class="onb-lead onb-center">Bấm <b>Thử tạo giọng</b> để nghe giọng đọc đầu tiên của bạn.</p>
      <div class="onb-api"><div><b>🔌 API cho phần mềm khác</b><div class="hint">Gửi văn bản tới <code>${location.origin}/api/tts</code> để nhận file giọng nói. Ví dụ có sẵn ở trang API.</div></div>
        <button class="btn btn-ghost btn-sm" id="onb-api" type="button">Xem API →</button></div>
      ${powerNote(true)}`;
  }

  function render() {
    const steps = STEPS();
    const key = steps[S.step].key;
    $("#onb-steps").innerHTML = steps.map((s, i) =>
      `<li class="${i < S.step ? "done" : i === S.step ? "current" : ""}"><span>${i < S.step ? "✓" : i + 1}</span>${s.label}</li>`).join("");
    $("#onb-body").innerHTML = { intro: renderIntro, check: renderCheck, install: renderInstall, model: renderModel, done: renderDone }[key]();
    $("#onb-count").textContent = `Bước ${S.step + 1}/${steps.length}`;
    $("#onb-back").style.visibility = S.step ? "visible" : "hidden";
    const next = $("#onb-next");
    next.disabled = false;
    if (key === "intro") next.textContent = "Bắt đầu →";
    else if (key === "check") { next.textContent = S.checks ? "Tiếp tục →" : "Bỏ qua →"; }
    else if (key === "install") next.textContent = "Tôi đã cài xong →";
    else if (key === "model") { next.textContent = "Tiếp tục →"; next.disabled = !(S.model && S.model.loaded); }
    else next.textContent = S.hosted ? "Thử bản web" : "🎤 Thử tạo giọng";
  }

  // ── Hành động ────────────────────────────────────────
  async function runCheck() {
    const btn = $("#onb-run-check");
    if (btn) busy(btn, true, "Đang kiểm tra...");
    try {
      S.facts = (!S.hosted && (await factsFromServer())) || (await factsFromBrowser());
    } catch {
      S.facts = await factsFromBrowser();
    }
    S.checks = evaluate(S.facts);
    if (OS_LABEL[S.facts.platform]) S.os = S.facts.platform;
    render();
  }

  async function loadInstallers() {
    if (S.installers) return;
    try { S.installers = (await (await fetch("/api/downloads")).json()).installers; }
    catch { S.installers = {}; }
    if (STEPS()[S.step].key === "install") render();
  }

  async function startModel() {
    S.modelErr = null;
    S.startedAt = Date.now();
    try {
      const r = await (await fetch("/api/warmup", { method: "POST" })).json();
      S.model = r.status;
    } catch (e) { S.modelErr = e.message; }
    pollModel();
  }

  function pollModel() {
    clearInterval(S.poll);
    S.poll = null;
    if (S.modelErr || (S.model && (S.model.loaded || S.model.error))) { render(); return; }
    if (!S.startedAt) S.startedAt = Date.now();
    S.poll = setInterval(async () => {
      try {
        const h = await (await fetch("/api/health")).json();
        S.model = h.status;
        if (h.status.loaded || h.status.error) {
          clearInterval(S.poll); S.poll = null;
          if (h.status.loaded) { setStatus(h.status); loadVoices(); }
          render();
          return;
        }
      } catch {}
      const el = $("#onb-elapsed");
      if (el) el.textContent = Math.round((Date.now() - S.startedAt) / 1000) + "s";
    }, 1500);
    render();
  }

  async function findLocal() {
    const btn = $("#onb-find");
    if (btn) busy(btn, true, "Đang dò...");
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 3000);
    try {
      // no-cors: không đọc được nội dung, nhưng resolve = có server đang nghe ở cổng này.
      await fetch(LOCAL_URL + "/api/health", { mode: "no-cors", signal: ctrl.signal });
      S.localFound = true;
    } catch { S.localFound = false; }
    clearTimeout(t);
    render();
  }

  function open() {
    S.step = 0;
    $("#onb").hidden = false;
    document.body.classList.add("onb-lock");
    render();
    $("#onb-next").focus();
  }
  function close() {
    $("#onb").hidden = true;
    document.body.classList.remove("onb-lock");
    try { localStorage.setItem(SEEN_KEY, "1"); } catch {}
  }

  function goTo(i) {
    S.step = Math.max(0, Math.min(i, STEPS().length - 1));
    const key = STEPS()[S.step].key;
    if (key === "install") loadInstallers();
    if (key === "model" && !S.model) {
      fetch("/api/health").then((r) => r.json()).then((h) => { S.model = h.status; if (h.status.loading) pollModel(); else render(); }).catch(() => {});
    }
    render();
    $("#onb-body").scrollTop = 0;
  }

  function finish() {
    close();
    showTab("synthesize");
    if (!S.hosted) setTimeout(() => $("#syn-go").click(), 150);
  }

  $("#onb-next").addEventListener("click", () => {
    if (S.step === STEPS().length - 1) return finish();
    goTo(S.step + 1);
  });
  $("#onb-back").addEventListener("click", () => goTo(S.step - 1));
  $("#onb-close").addEventListener("click", close);
  $("#onb-open").addEventListener("click", open);
  $("#onb").addEventListener("click", (e) => {
    if (e.target.id === "onb") return close();
    if (e.target.closest("#onb-run-check")) return runCheck();
    if (e.target.closest("#onb-load")) return startModel();
    if (e.target.closest("#onb-find")) return findLocal();
    if (e.target.closest("#onb-api")) { close(); return showTab("api"); }
    const os = e.target.closest("[data-onb-os]");
    if (os) { S.os = os.dataset.onbOs; render(); }
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#onb").hidden) close(); });

  // Lần đầu mở app → tự hiện. Sau đó mở lại bằng nút ở sidebar.
  fetch("/api/info").then((r) => r.json()).then((info) => {
    S.hosted = !!info.hosted;
    S.devUrl = (info.branding.developer || {}).url || "";
    let seen = false;
    try { seen = localStorage.getItem(SEEN_KEY) === "1"; } catch {}
    if (!seen || location.hash === "#onboarding") open();
  }).catch(() => {});
})();
