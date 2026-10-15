// ── Trang MCP & API · tab MCP ──────────────────────────
// Hướng dẫn kết nối Claude Desktop / ChatGPT Codex với app qua MCP (webapp/mcp_server.py).
// Dữ liệu (đường dẫn, trạng thái đã kết nối) lấy từ GET /api/mcp; nút "Kết nối tự động" gọi
// POST /api/mcp/connect — server tự sao lưu file cấu hình cũ trước khi sửa.

let MCP = null;
let MCP_APP = (() => { try { return localStorage.getItem("vieneu_mcp_app") || "claude"; } catch { return "claude"; } })();

const MCP_EXAMPLES = [
  "Kiểm tra AI Audio Studio đã sẵn sàng chưa.",
  "Đọc đoạn sau bằng giọng Trúc Ly, đặt tên file là loi-chao: “Xin chào các bạn, chào mừng đến với kênh của mình.”",
  "Liệt kê các giọng tiếng Việt, rồi chọn 1 giọng nam miền Nam đọc thử câu: “Hôm nay trời đẹp quá.”",
  "Viết kịch bản podcast 6 lượt về cách học tiếng Anh, 2 người dẫn (1 nam, 1 nữ), rồi tạo file audio hội thoại.",
  "Đọc câu này bằng tiếng Anh, giọng nữ trẻ, giọng Anh-Anh: “Welcome to our English class.”",
];

function mcpCopyBtn(id, label = "Sao chép") {
  return `<button class="btn btn-ghost btn-sm" type="button" data-mcp-copy="${id}">${label}</button>`;
}

function mcpAppCard(key, ico, name, sub) {
  const t = MCP[key];
  const st = t.connected ? `<span class="mcp-pill ok">✓ Đã kết nối</span>`
    : t.installed ? `<span class="mcp-pill">Đã thấy trên máy · chưa kết nối</span>`
    : `<span class="mcp-pill muted">Chưa thấy trên máy</span>`;
  return `<button class="mcp-app ${MCP_APP === key ? "active" : ""}" type="button" data-mcp-app="${key}" aria-pressed="${MCP_APP === key}">
    <span class="mcp-app-ico">${ico}</span>
    <span class="mcp-app-tx"><b>${name}</b><span>${sub}</span>${st}</span>
  </button>`;
}

function mcpStep(n, title, body, done) {
  return `<li class="mcp-step ${done ? "done" : ""}"><span class="mcp-num">${done ? "✓" : n}</span>
    <div class="mcp-step-body"><h4>${title}</h4>${body}</div></li>`;
}

function mcpConnectBlock(key) {
  const t = MCP[key];
  const btn = t.connected
    ? `<button class="btn btn-ghost" type="button" data-mcp-connect="${key}">↻ Kết nối lại</button>
       <button class="btn btn-ghost" type="button" data-mcp-disconnect="${key}">Gỡ kết nối</button>`
    : `<button class="btn btn-primary" type="button" data-mcp-connect="${key}">⚡ Kết nối tự động</button>`;
  return `<div class="actions" style="margin-top:8px">${btn}</div>
    <p class="hint">App tự thêm AI Audio Studio vào file cấu hình <code>${escapeHtml(t.path)}</code> (file cũ được sao lưu thành <code>….bak-ngày-giờ</code>, các kết nối khác giữ nguyên).</p>`;
}

function mcpStepsClaude() {
  const c = MCP.claude;
  const quit = MCP.os === "macos"
    ? "Bấm chữ <b>Claude</b> trên thanh menu trên cùng → <b>Quit Claude</b> (hoặc <kbd>⌘</kbd> + <kbd>Q</kbd>)"
    : MCP.os === "windows"
    ? "Chuột phải icon Claude ở khay đồng hồ (góc phải dưới) → <b>Quit</b>. Chỉ đóng cửa sổ là chưa đủ"
    : "Thoát hẳn Claude Desktop";
  return [
    mcpStep(1, "Cài Claude Desktop", `<p>Tải tại <a href="https://claude.ai/download" target="_blank" rel="noopener">claude.ai/download</a> và đăng nhập (gói miễn phí cũng dùng được).
      ${c.installed ? `<span class="mcp-pill ok">✓ Đã thấy Claude Desktop trên máy</span>` : ""}</p>
      <p class="hint">${MCP.os === "linux" ? "⚠️ Claude Desktop chưa có bản chính thức cho Linux — dùng ChatGPT Codex hoặc Claude Code (mục Nâng cao)." : "Claude trên trình duyệt (claude.ai) và điện thoại không dùng được — phải là app Claude Desktop trên máy này."}</p>`, c.installed),
    mcpStep(2, "Kết nối với AI Audio Studio", mcpConnectBlock("claude"), c.connected),
    mcpStep(3, "Khởi động lại Claude Desktop", `<p>${quit}, rồi mở Claude lại. Claude chỉ đọc cấu hình mới lúc khởi động.</p>`),
    mcpStep(4, "Dùng thử", `<p>Mở cuộc trò chuyện mới, gõ: <i>“Kiểm tra AI Audio Studio đã sẵn sàng chưa.”</i> Lần đầu Claude hỏi quyền dùng công cụ → bấm <b>Always allow</b> (Luôn cho phép).</p><p>Thử thêm: <i>“Đọc file kịch bản.txt bằng giọng Hải Đăng”</i> (văn bản dài tự chia đoạn rồi ghép), <i>“Clone giọng từ file mau.wav rồi đọc tiếng Anh”</i>, <i>“Liệt kê 5 lượt tạo audio gần nhất”</i>, <i>“Cài gói Đa ngôn ngữ”</i>.</p>
      <p class="hint">Không thấy? Vào <b>Settings → Developer</b> trong Claude Desktop: dòng <code>ai-audio-studio</code> phải ở trạng thái <b>running</b>. Báo lỗi thì bấm <b>🧪 Kiểm tra kết nối</b> bên dưới.</p>`),
  ].join("");
}

function mcpStepsCodex() {
  const c = MCP.codex;
  return [
    mcpStep(1, "Cài ChatGPT Codex trên máy", `<p>Codex dùng tài khoản ChatGPT (Plus, Pro, Business…). Chọn một cách:</p>
      <ul class="mcp-list">
        <li><b>Codex CLI</b> (Terminal): cài Node.js rồi chạy <code>npm install -g @openai/codex</code>, gõ <code>codex</code> và đăng nhập ChatGPT.</li>
        <li><b>Tiện ích Codex</b> trong VS Code / Cursor (tìm “Codex” trong Extensions), hoặc <b>app Codex</b> trên máy tính.</li>
      </ul>
      <p class="hint">Hướng dẫn chính thức: <a href="https://developers.openai.com/codex" target="_blank" rel="noopener">developers.openai.com/codex</a>. Codex trên web (chatgpt.com/codex) và ChatGPT chat thường chạy trên máy chủ OpenAI nên <b>không</b> gọi được app trên máy bạn.</p>
      ${c.installed ? `<span class="mcp-pill ok">✓ Đã thấy Codex trên máy</span>` : ""}`, c.installed),
    mcpStep(2, "Kết nối với AI Audio Studio", mcpConnectBlock("codex") + `
      <details class="mcp-more"><summary>Hoặc dán 1 lệnh vào Terminal</summary>
        <div class="mcp-cmd"><code id="mcp-codex-cli">${escapeHtml(c.cli)}</code>${mcpCopyBtn("mcp-codex-cli")}</div>
        <p class="hint">Lệnh này không đặt thời gian chờ dài — nếu đọc văn bản dài bị ngắt giữa chừng, dùng nút Kết nối tự động (đặt sẵn chờ tối đa 15 phút).</p>
      </details>`, c.connected),
    mcpStep(3, "Mở lại Codex", `<p>Thoát phiên Codex đang chạy rồi mở lại (CLI: gõ <code>/quit</code> rồi <code>codex</code>; VS Code: tải lại cửa sổ). Gõ <code>/mcp</code> trong Codex CLI để thấy <code>ai-audio-studio</code>.</p>`),
    mcpStep(4, "Dùng thử", `<p>Gõ: <i>“Kiểm tra AI Audio Studio đã sẵn sàng chưa.”</i> Codex hỏi quyền chạy công cụ → đồng ý.</p>`),
  ].join("");
}

function renderMcp() {
  const root = $("#mcp-root");
  if (!MCP) return;
  const steps = MCP_APP === "codex" ? mcpStepsCodex() : mcpStepsClaude();
  root.innerHTML = `
  <div class="card mcp-hero">
    <div class="section-title">🧩 Ra lệnh bằng lời — AI tự tạo giọng cho bạn</div>
    <p class="mcp-lead">Kết nối một lần, sau đó chỉ cần nói với <b>Claude Desktop</b> hoặc <b>ChatGPT Codex</b>: <i>“đọc đoạn này bằng giọng Trúc Ly”</i>, <i>“làm podcast 2 người”</i>… AI tự gọi AI Audio Studio và lưu file audio vào máy bạn. Không cần copy prompt dài.</p>
    <div class="mcp-flow" aria-label="Cách hoạt động">
      <span class="mcp-node">💬 Bạn gõ yêu cầu</span><span class="mcp-arrow">→</span>
      <span class="mcp-node">🤖 Claude Desktop / Codex</span><span class="mcp-arrow">→</span>
      <span class="mcp-node hl">🎙️ AI Audio Studio<br><small>trên máy này</small></span><span class="mcp-arrow">→</span>
      <span class="mcp-node">📁 File .wav<br><small>${escapeHtml(MCP.out_dir.split(/[\\/]/).slice(-2).join("/"))}</small></span>
    </div>
    <div class="mcp-warn"><b>💻 Chỉ chạy khi cài trên máy tính.</b> AI Audio Studio và Claude Desktop / Codex phải cùng ở <b>máy tính này</b>. Không dùng được với ChatGPT, Claude trên trình duyệt hay điện thoại (chúng chạy trên máy chủ, không thấy máy bạn). App đang tắt thì MCP tự mở app (chạy ẩn).</div>
  </div>

  <div class="card">
    <div class="section-title">1️⃣ Bạn dùng phần mềm AI nào?</div>
    <div class="mcp-apps">
      ${mcpAppCard("claude", "✳️", "Claude Desktop", "App Claude trên máy tính · macOS, Windows")}
      ${mcpAppCard("codex", "⌘", "ChatGPT Codex", "Codex CLI, VS Code, app Codex · dùng tài khoản ChatGPT")}
    </div>
  </div>

  <div class="card">
    <div class="section-title">2️⃣ Làm theo ${MCP_APP === "codex" ? "4 bước với ChatGPT Codex" : "4 bước với Claude Desktop"}</div>
    <ol class="mcp-steps">${steps}</ol>
    <div class="mcp-test">
      <button class="btn btn-ghost" type="button" id="mcp-test">🧪 Kiểm tra kết nối</button>
      <span class="hint">Chạy thử đúng lệnh MCP mà ${MCP_APP === "codex" ? "Codex" : "Claude"} sẽ chạy.</span>
      <div id="mcp-test-out"></div>
    </div>
  </div>

  <div class="row two">
    <div class="card">
      <div class="section-title">💬 Câu lệnh mẫu — bấm để chép</div>
      <div class="mcp-examples">${MCP_EXAMPLES.map((x, i) => `<button class="mcp-ex" type="button" data-mcp-ex="${i}">${escapeHtml(x)}</button>`).join("")}</div>
      <p class="hint">Văn bản tiếng Việt tối đa 5.000 ký tự/lần, ngôn ngữ khác 2.000 ký tự/lần — dài hơn AI sẽ tự chia.</p>
    </div>
    <div class="card">
      <div class="section-title">🛠 AI làm được gì</div>
      <ul class="mcp-tools">
        <li><b>Đọc văn bản</b> — 25 giọng Việt, giọng bạn đã clone; 17 ngôn ngữ khác nếu đã cài gói 🌏 Đa ngôn ngữ.</li>
        <li><b>Tạo hội thoại</b> — nhiều nhân vật, mỗi lượt một giọng, trộn được nhiều thứ tiếng.</li>
        <li><b>Xem danh sách giọng</b> — AI tự chọn giọng hợp với yêu cầu.</li>
        <li><b>Kiểm tra app</b> — app chạy chưa, model nạp chưa.</li>
      </ul>
      <p class="hint">File lưu tại <code>${escapeHtml(MCP.out_dir)}</code> và trong trang <b>Lịch sử</b> của app.</p>
    </div>
  </div>

  <div class="card">
    <details class="mcp-more">
      <summary><b>⚙️ Nâng cao — Claude Code, Cursor, cấu hình thủ công</b></summary>
      <h4>Claude Code (Terminal)</h4>
      <div class="mcp-cmd"><code id="mcp-cc-cli">${escapeHtml(MCP.claude_code.cli)}</code>${mcpCopyBtn("mcp-cc-cli")}</div>
      <h4>Claude Desktop / Cursor — dán vào file cấu hình</h4>
      <p class="hint">Claude Desktop: <code>${escapeHtml(MCP.claude.path)}</code> · Cursor: <code>~/.cursor/mcp.json</code>. Đã có <code>"mcpServers"</code> thì chỉ thêm mục <code>"${MCP.name}"</code> vào trong.</p>
      <pre class="code" id="mcp-json">${escapeHtml(MCP.claude.snippet)}</pre>${mcpCopyBtn("mcp-json")}
      <h4>ChatGPT Codex — <code>${escapeHtml(MCP.codex.path)}</code></h4>
      <pre class="code" id="mcp-toml">${escapeHtml(MCP.codex.snippet)}</pre>${mcpCopyBtn("mcp-toml")}
      <p class="hint">Đổi thư mục lưu file: thêm biến <code>VIENEU_MCP_OUT</code> vào phần env. Cài lại app sang thư mục khác thì bấm Kết nối lại để cập nhật đường dẫn.</p>
    </details>
  </div>`;
  bindMcp();
}

function bindMcp() {
  $$("[data-mcp-app]").forEach((b) => b.addEventListener("click", () => {
    MCP_APP = b.dataset.mcpApp;
    try { localStorage.setItem("vieneu_mcp_app", MCP_APP); } catch {}
    renderMcp();
  }));
  $$("[data-mcp-copy]").forEach((b) => b.addEventListener("click", async () => {
    const el = document.getElementById(b.dataset.mcpCopy);
    try { await navigator.clipboard.writeText(el.textContent); toast("Đã sao chép!"); } catch { toast("Bôi đen rồi chép thủ công nhé.", true); }
  }));
  $$("[data-mcp-ex]").forEach((b) => b.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(MCP_EXAMPLES[+b.dataset.mcpEx]); toast("Đã chép — dán vào Claude / Codex"); } catch {}
  }));
  $$("[data-mcp-connect]").forEach((b) => b.addEventListener("click", () => mcpAction("connect", b)));
  $$("[data-mcp-disconnect]").forEach((b) => b.addEventListener("click", () => {
    if (confirm("Gỡ AI Audio Studio khỏi " + (b.dataset.mcpDisconnect === "codex" ? "Codex" : "Claude Desktop") + "?")) mcpAction("disconnect", b);
  }));
  const t = $("#mcp-test");
  if (t) t.addEventListener("click", mcpTest);
}

async function mcpAction(kind, btn) {
  const target = btn.dataset.mcpConnect || btn.dataset.mcpDisconnect;
  btn.disabled = true;
  const old = btn.innerHTML;
  btn.innerHTML = `<span class="spinner"></span> Đang ${kind === "connect" ? "kết nối" : "gỡ"}…`;
  try {
    MCP = await apiJson("/api/mcp/" + kind, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ target }) });
    renderMcp();
    const who = target === "codex" ? "Codex" : "Claude Desktop";
    toast(kind === "connect" ? `Đã kết nối! Giờ khởi động lại ${who} (bước 3).` : `Đã gỡ khỏi ${who}.`);
  } catch (e) {
    btn.disabled = false; btn.innerHTML = old;
    toast("Không làm được: " + e.message, true);
  }
}

async function mcpTest() {
  const out = $("#mcp-test-out"), btn = $("#mcp-test");
  btn.disabled = true;
  out.innerHTML = `<p class="hint"><span class="spinner"></span> Đang chạy thử…</p>`;
  try {
    const r = await apiJson("/api/mcp/test", { method: "POST" });
    out.innerHTML = r.ok
      ? `<div class="mcp-result ok"><b>✓ MCP chạy tốt</b> — ${r.tools.length} công cụ: ${r.tools.map((x) => `<code>${escapeHtml(x)}</code>`).join(" ")}<pre>${escapeHtml(r.status)}</pre>
         ${MCP[MCP_APP].connected ? "" : `<p>Còn thiếu: bấm <b>⚡ Kết nối tự động</b> ở bước 2.</p>`}</div>`
      : `<div class="mcp-result err"><b>✗ MCP chưa chạy được</b><pre>${escapeHtml(r.error || "")}</pre><p>Gửi ảnh chụp màn hình này cho người phát triển để được hỗ trợ.</p></div>`;
  } catch (e) {
    out.innerHTML = `<div class="mcp-result err"><b>✗ ${escapeHtml(e.message)}</b></div>`;
  } finally { btn.disabled = false; }
}

async function loadMcp() {
  try {
    MCP = await apiJson("/api/mcp");
    renderMcp();
  } catch (e) {
    $("#mcp-root").innerHTML = `<div class="card"><div class="section-title">🧩 MCP</div>
      <p>MCP chỉ có trên <b>bản cài máy tính</b> — cài AI Audio Studio vào máy rồi mở trang này trong app.</p>
      <p class="hint">${escapeHtml(e.message)}</p></div>`;
  }
}

// Chuyển tab MCP ↔ API
function setApiMode(mode) {
  $$("[data-api-mode]").forEach((b) => {
    const on = b.dataset.apiMode === mode;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", on);
  });
  $("#api-mode-mcp").hidden = mode !== "mcp";
  $("#api-mode-api").hidden = mode !== "api";

}
$$("[data-api-mode]").forEach((b) => b.addEventListener("click", () => setApiMode(b.dataset.apiMode)));

// Mở trang MCP & API: luôn vào tab MCP trước (nạp lại trạng thái kết nối mỗi lần mở)
const _apiHook = TAB_HOOKS.api;
TAB_HOOKS.api = () => {
  if (_apiHook) _apiHook();
  setApiMode("mcp");
  loadMcp();
};
if (location.hash === "#api") TAB_HOOKS.api();   // F5 khi đang ở trang này (app.js chạy trước file này)
