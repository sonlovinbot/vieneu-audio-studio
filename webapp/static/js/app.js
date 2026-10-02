/* VieNeu Studio (Coachio Edition) — frontend logic */
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

let VOICES = [];
let LAST_CLONE_FILE = null;   // file mẫu của lần clone thành công gần nhất
let HISTORY_MAX = 50;

// ── Khóa truy cập (lưu localStorage, gắn vào header khi gọi API) ──────
function getApiKey() { return localStorage.getItem("vieneu_api_key") || ""; }
function getAdminKey() { return localStorage.getItem("vieneu_admin_key") || ""; }
function authHeaders(base) {
  const h = Object.assign({}, base || {});
  const k = getApiKey();
  if (k) h["X-API-Key"] = k;
  return h;
}
function adminHeaders(base) {
  const h = Object.assign({}, base || {});
  const k = getAdminKey();
  if (k) h["X-Admin-Key"] = k;
  return h;
}

// ── Toast ──────────────────────────────────────────────
function toast(msg, isError = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast show" + (isError ? " error" : "");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.className = "toast"), 4000);
}

// ── Điều hướng (sidebar) ───────────────────────────────
// Mỗi mục sidebar có data-tab="x" ↔ <section id="tab-x">. Nhớ trang qua #hash
// để F5 / nút Back vẫn đúng chỗ. TAB_HOOKS chạy khi mở trang (nạp dữ liệu lười).
const TAB_HOOKS = {};
let LIBRARY_ON = true;

function showTab(name, { push = true } = {}) {
  const item = document.querySelector(`.nav-item[data-tab="${name}"]`);
  const panel = document.getElementById("tab-" + name);
  if (!item || !panel || item.hidden || item.closest("[hidden]")) name = "synthesize";
  $$(".nav-item").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  $$(".panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + name));
  const active = document.querySelector(`.nav-item[data-tab="${name}"]`);
  $("#page-title").textContent = [...active.childNodes]
    .filter((n) => n.nodeType === Node.TEXT_NODE).map((n) => n.textContent).join("").trim();
  if (push && location.hash !== "#" + name) history.pushState(null, "", "#" + name);
  if (TAB_HOOKS[name]) TAB_HOOKS[name]();
  alignActiveNav();
  window.scrollTo(0, 0);
}
$$(".nav-item").forEach((t) => t.addEventListener("click", () => showTab(t.dataset.tab)));

// Màn hẹp: nav cuộn ngang — giữ mục đang mở trong tầm nhìn. Chỉ chỉnh scrollLeft
// của nav (không bao giờ cuộn trang). Chạy lại mỗi khi nút nav đổi kích thước:
// web font nạp muộn và số đếm (Lịch sử 3, Giọng 1) điền vào sau đều làm nút rộng ra.
function alignActiveNav() {
  const nav = $(".nav");
  const a = $(".nav-item.active");
  if (!nav || !a || nav.scrollWidth <= nav.clientWidth) return;
  const n = nav.getBoundingClientRect();
  const r = a.getBoundingClientRect();
  if (r.left < n.left) nav.scrollLeft += r.left - n.left - 8;
  else if (r.right > n.right) nav.scrollLeft += r.right - n.right + 8;
}
if (window.ResizeObserver) {
  const ro = new ResizeObserver(alignActiveNav);
  $$(".nav-item").forEach((t) => ro.observe(t));
}
document.addEventListener("click", (e) => {
  const g = e.target.closest("[data-goto]");
  if (g) showTab(g.dataset.goto);
});
window.addEventListener("popstate", () => showTab(location.hash.slice(1) || "synthesize", { push: false }));

// ── Giao diện sáng / tối ───────────────────────────────
// Lưu lựa chọn ("light" | "dark" | "system") trong localStorage — tùy chọn
// riêng của từng trình duyệt, không cần lưu phía server.
const THEME_KEY = "vieneu_theme";
const darkMQ = window.matchMedia("(prefers-color-scheme: dark)");
function themePref() {
  try { return localStorage.getItem(THEME_KEY) || "system"; } catch { return "system"; }
}
function applyTheme(pref) {
  const dark = pref === "dark" || (pref === "system" && darkMQ.matches);
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  $$(".theme-switch [data-theme-pref]").forEach((b) => {
    const on = b.dataset.themePref === pref;
    b.classList.toggle("active", on);
    b.setAttribute("aria-checked", on ? "true" : "false");
  });
}
$$(".theme-switch [data-theme-pref]").forEach((b) => b.addEventListener("click", () => {
  try { localStorage.setItem(THEME_KEY, b.dataset.themePref); } catch {}
  applyTheme(b.dataset.themePref);
}));
darkMQ.addEventListener("change", () => { if (themePref() === "system") applyTheme("system"); });
applyTheme(themePref());

// ── Status ─────────────────────────────────────────────
function setStatus(status) {
  const dot = $("#status-dot");
  const text = $("#status-text");
  if (!status) return;
  if (status.error) { dot.className = "dot red"; text.textContent = "Lỗi model"; }
  else if (status.loading) { dot.className = "dot orange"; text.textContent = "Đang tải model..."; }
  else if (status.loaded) { dot.className = "dot green"; text.textContent = "Sẵn sàng"; }
  else { dot.className = "dot gray"; text.textContent = "Chưa tải model"; }
  $("#set-backbone").textContent = status.backbone_repo || "—";
  $("#set-device").textContent = status.device || "—";
  $("#set-sr").textContent = status.sample_rate ? status.sample_rate + " Hz" : "—";
}

// ── Init: branding + voices ────────────────────────────
async function init() {
  try {
    const info = await (await fetch("/api/info")).json();
    AUTH_REQUIRED = !!info.auth_required;
    LIBRARY_ON = info.library !== false;
    HISTORY_MAX = info.history_max || HISTORY_MAX;
    MAX_CHARS = info.max_text_chars || MAX_CHARS;
    $("#nav-library").hidden = !LIBRARY_ON;
    $$("[data-recent-card]").forEach((c) => (c.hidden = !LIBRARY_ON));
    const b = info.branding;
    $("#app-title").textContent = b.app.name;
    $("#app-edition").textContent = (b.app.edition || "").toUpperCase();
    $("#app-tagline").textContent = b.app.tagline || "";
    document.title = `${b.app.name} — ${b.app.edition || ""}`;
    // Author / about
    $("#author-name").textContent = b.author.name;
    $("#author-role").textContent = b.author.role || "";
    $("#author-note").textContent = b.author.note || "";
    $("#credits").textContent = b.credits || "";
    const links = $("#author-links");
    const L = b.links || {};
    const dev = b.developer || {};
    const items = [
      ["GitHub VieNeu-TTS", L.github], ["Hugging Face", L.huggingface], ["Discord", L.discord],
    ].filter(([, u]) => u);
    links.innerHTML = items.map(([n, u]) => `<li><a href="${u}" target="_blank" rel="noopener">${n}</a></li>`).join("");
    // Người phát triển phần mềm (khác tác giả model)
    if (dev.name) { $("#dev-name").textContent = dev.name; $("#side-dev .dev-who").textContent = dev.name + " ↗"; }
    if (dev.role) $("#dev-role").textContent = dev.role;
    if (dev.title) { $("#dev-title").textContent = dev.title; $("#side-dev .dev-title").textContent = dev.title; }
    if (dev.intro) $("#dev-intro").textContent = dev.intro;
    if (dev.url) { $("#dev-link").href = dev.url; $("#side-dev").href = dev.url; }
    if (dev.link_label) $("#dev-link").textContent = dev.link_label + " →";
    setStatus(info.status);
  } catch (e) { console.error(e); }
  loadVoices();
  buildConversation();
  updateCounts();
  loadPreviews();
  showTab(location.hash.slice(1) || "synthesize", { push: false });
  if (LIBRARY_ON) refreshCounts();
}

async function loadVoices() {
  try {
    const data = await (await fetch("/api/voices")).json();
    VOICES = data.voices || [];
    fillVoiceSelects();
    const h = await (await fetch("/api/health")).json();
    setStatus(h.status);
  } catch (e) {
    toast("Không tải được danh sách giọng: " + e.message, true);
  }
}

function voiceOptions(selected) {
  const opt = (v) => `<option value="${escapeHtml(v.id)}" ${v.id === selected ? "selected" : ""}>${escapeHtml(v.label)}</option>`;
  const mine = VOICES.filter((v) => v.custom);
  const builtin = VOICES.filter((v) => !v.custom);
  if (!mine.length) return builtin.map(opt).join("");
  return `<optgroup label="⭐ Giọng của tôi">${mine.map(opt).join("")}</optgroup>`
       + `<optgroup label="Giọng có sẵn">${builtin.map(opt).join("")}</optgroup>`;
}
function fillVoiceSelects() {
  const sel = $("#syn-voice");
  if (sel) { const cur = sel.value; sel.innerHTML = voiceOptions(cur); }
  $$(".turn-voice").forEach((s) => { const cur = s.value; s.innerHTML = voiceOptions(cur); });
  setCount("voices", VOICES.filter((v) => v.custom).length);
  renderEmoChips();
}

// ── Giọng cảm xúc: giọng tự clone, lưu kèm nhãn "Tên · Cảm xúc" ──
function renderEmoChips() {
  const box = $("#emo-chips");
  if (!box) return;
  const emo = VOICES.filter((v) => v.custom && v.id.includes(" · "));
  const cur = $("#syn-voice").value;
  box.innerHTML = emo.length
    ? emo.map((v) => `<button type="button" class="emo-chip ${v.id === cur ? "active" : ""}" data-voice="${escapeHtml(v.id)}">${escapeHtml(v.id)}</button>`).join("")
    : `<span class="hint" style="margin:0">Chưa có. Bấm <b>➕ Tạo giọng cảm xúc</b> để thêm giọng vui, buồn, thì thầm... của riêng bạn.</span>`;
}
document.addEventListener("click", (e) => {
  const chip = e.target.closest(".emo-chip");
  if (chip) { $("#syn-voice").value = chip.dataset.voice; renderEmoChips(); toast(`Đã chọn giọng "${chip.dataset.voice}".`); }
});
$("#syn-voice").addEventListener("change", renderEmoChips);
$("#emo-new").addEventListener("click", () => {
  showTab("clone");
  toast("Tải lên 3–5 giây nói đúng cảm xúc bạn muốn → Clone → chọn nhãn cảm xúc → Lưu giọng.");
  $("#clone-ref").focus();
});

// ── Đếm ký tự + cảnh báo văn bản dài / thẻ cảm xúc lạ ──
let MAX_CHARS = 5000;
const SOFT_CHARS = 1500;   // trên mức này sinh lâu hơn rõ rệt
const HEAVY_CHARS = 3000;  // trên mức này máy yếu dễ lag
const KNOWN_TAGS = ["cười", "cuoi", "thở dài", "tho dai", "hắng giọng", "hang giong", "chuckle", "sigh", "clear throat"];
const COUNTERS = {
  "syn-text": { text: () => $("#syn-text").value, btn: "#syn-go" },
  "clone-text": { text: () => $("#clone-text").value, btn: "#clone-go" },
  conv: { text: () => [...$$("#conv-turns .turn-text")].map((t) => t.value).join(""), btn: "#conv-go" },
};
function unknownTags(text) {
  const bad = new Set();
  for (const m of text.matchAll(/\[([^\]]+)\]/g)) {
    if (!KNOWN_TAGS.includes(m[1].trim().toLowerCase())) bad.add(m[0]);
  }
  return [...bad];
}
function updateCounts() {
  for (const [key, c] of Object.entries(COUNTERS)) {
    const box = document.querySelector(`[data-count-for="${key}"]`);
    if (!box) continue;
    const text = c.text();
    const n = text.length;
    const words = (text.trim().match(/\S+/g) || []).length;
    let level = "", msg = "";
    if (n > MAX_CHARS) { level = "over"; msg = `Vượt giới hạn ${MAX_CHARS.toLocaleString("vi-VN")} ký tự — hãy cắt bớt hoặc chia thành nhiều lần.`; }
    else if (n > HEAVY_CHARS) { level = "heavy"; msg = "Văn bản rất dài — máy có thể bị lag, sinh mất vài phút. Nên chia thành đoạn ≤ 1.500 ký tự."; }
    else if (n > SOFT_CHARS) { level = "soft"; msg = "Văn bản khá dài — sinh lâu hơn. Chia nhỏ sẽ nhanh và mượt hơn."; }
    const bad = unknownTags(text);
    if (bad.length) msg += `${msg ? " " : ""}⚠️ Thẻ ${bad.slice(0, 3).join(", ")} không được hỗ trợ — sẽ bị đọc thành chữ. Chỉ dùng [cười], [thở dài], [hắng giọng].`;
    box.className = "text-meta" + (level ? " " + level : "") + (bad.length && !level ? " soft" : "");
    box.querySelector(".count-num").textContent = `${n.toLocaleString("vi-VN")} / ${MAX_CHARS.toLocaleString("vi-VN")} ký tự · ~${words.toLocaleString("vi-VN")} từ`;
    box.querySelector(".count-msg").textContent = msg;
    const btn = $(c.btn);
    if (btn && !btn.querySelector(".spinner")) btn.disabled = n > MAX_CHARS;
  }
}
document.addEventListener("input", (e) => {
  if (e.target.matches("#syn-text, #clone-text, .turn-text")) updateCounts();
});

// ── Audio result rendering ─────────────────────────────
function showAudio(containerSel, blob, filename) {
  const url = URL.createObjectURL(blob);
  const c = $(containerSel);
  c.innerHTML = `
    <audio controls src="${url}"></audio>
    <div class="actions">
      <a class="btn btn-secondary" href="${url}" download="${filename}">⬇ Tải xuống</a>
    </div>`;
}

function busy(btn, on, label) {
  if (on) { btn.dataset.label = btn.textContent; btn.disabled = true; btn.innerHTML = `<span class="spinner"></span> ${label || "Đang xử lý..."}`; }
  else { btn.disabled = false; btn.textContent = btn.dataset.label || "Xong"; updateCounts(); }
}

// ── Synthesize ─────────────────────────────────────────
// Emotion tags are inline in v3.8.3: insert the cue at the caret instead of
// sending a whole-utterance emotion parameter.
document.querySelectorAll(".emotion-tags [data-tag]").forEach((b) => {
  b.addEventListener("click", () => {
    const ta = document.getElementById(b.closest(".emotion-tags").dataset.target || "syn-text");
    const tag = b.dataset.tag;
    const start = ta.selectionStart ?? ta.value.length;
    const end = ta.selectionEnd ?? ta.value.length;
    const before = ta.value.slice(0, start);
    const needsSpace = before.length > 0 && !/\s$/.test(before);
    const ins = (needsSpace ? " " : "") + tag + " ";
    ta.value = before + ins + ta.value.slice(end);
    ta.focus();
    ta.selectionStart = ta.selectionEnd = start + ins.length;
    updateCounts();
  });
});

$("#syn-go").addEventListener("click", async () => {
  const btn = $("#syn-go");
  const text = $("#syn-text").value.trim();
  if (!text) return toast("Nhập nội dung đã!", true);
  busy(btn, true, "Đang sinh...");
  try {
    const res = await fetch("/api/tts", {
      method: "POST", headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        text, voice: $("#syn-voice").value,
        temperature: parseFloat($("#syn-temp").value) || 0.8,
        top_k: parseInt($("#syn-topk").value) || 25,
      }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    showAudio("#syn-result", await res.blob(), "vieneu.wav");
    loadVoices();
    refreshCounts();
  } catch (e) { toast(e.message, true); }
  finally { busy(btn, false); }
});

// ── Clone ──────────────────────────────────────────────
$("#clone-go").addEventListener("click", async () => {
  const btn = $("#clone-go");
  const file = $("#clone-ref").files[0];
  const text = $("#clone-text").value.trim();
  if (!file) return toast("Chọn file audio mẫu đã!", true);
  if (!text) return toast("Nhập nội dung cần đọc!", true);
  busy(btn, true, "Đang clone...");
  try {
    const fd = new FormData();
    fd.append("text", text);
    fd.append("ref_audio", file);
    const res = await fetch("/api/clone", { method: "POST", headers: authHeaders(), body: fd });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    showAudio("#clone-result", await res.blob(), "vieneu-clone.wav");
    // Chỉ giọng clone THÀNH CÔNG mới được mời lưu lại.
    LAST_CLONE_FILE = file;
    if (LIBRARY_ON) {
      $("#clone-save").hidden = false;
      const nameInput = $("#clone-save-name");
      if (!nameInput.value) nameInput.value = file.name.replace(/\.[^.]+$/, "").slice(0, 40);
    }
    refreshCounts();
  } catch (e) { toast(e.message, true); }
  finally { busy(btn, false); }
});

// Đổi file mẫu → form "lưu" cũ không còn khớp giọng vừa nghe.
$("#clone-ref").addEventListener("change", () => { $("#clone-save").hidden = true; LAST_CLONE_FILE = null; });

$("#clone-save-emo").addEventListener("change", (e) => {
  const custom = $("#clone-save-emo-custom");
  custom.hidden = e.target.value !== "__custom";
  if (!custom.hidden) custom.focus();
});
$("#clone-save-go").addEventListener("click", async () => {
  const btn = $("#clone-save-go");
  let name = $("#clone-save-name").value.trim();
  if (!LAST_CLONE_FILE) return toast("Hãy clone thử trước khi lưu.", true);
  if (!name) return toast("Đặt tên cho giọng đã!", true);
  const emoSel = $("#clone-save-emo").value;
  const emo = (emoSel === "__custom" ? $("#clone-save-emo-custom").value : emoSel).trim();
  if (emoSel === "__custom" && !emo) return toast("Nhập tên cảm xúc tự đặt!", true);
  if (emo) name = `${name.replace(/ · .*$/, "").slice(0, 37 - emo.length)} · ${emo}`;
  busy(btn, true, "Đang lưu...");
  try {
    const fd = new FormData();
    fd.append("name", name);
    fd.append("ref_audio", LAST_CLONE_FILE);
    const res = await fetch("/api/voices/custom", { method: "POST", headers: authHeaders(), body: fd });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || res.statusText);
    toast(`Đã lưu "${data.name}" vào Giọng của tôi.`);
    $("#clone-save").hidden = true;
    $("#clone-save-name").value = "";
    $("#clone-save-emo").value = "";
    $("#clone-save-emo-custom").hidden = true;
    await loadVoices();
    const sel = $("#syn-voice");
    if (sel) sel.value = data.name;
    refreshCounts();
  } catch (e) { toast(e.message, true); }
  finally { busy(btn, false); }
});

// ── Conversation ───────────────────────────────────────
function turnRow(text = "", voice = "") {
  const div = document.createElement("div");
  div.className = "turn";
  div.innerHTML = `
    <select class="turn-voice">${voiceOptions(voice)}</select>
    <textarea class="turn-text" placeholder="Lời thoại...">${escapeHtml(text)}</textarea>
    <button class="btn btn-ghost turn-del" title="Xóa">✕</button>`;
  div.querySelector(".turn-del").addEventListener("click", () => { div.remove(); updateCounts(); });
  return div;
}
function buildConversation(turns) {
  const c = $("#conv-turns");
  c.innerHTML = "";
  (turns && turns.length ? turns : [
    { text: "Chào bạn, hôm nay chúng ta nói về gì?" },
    { text: "Mình sẽ giới thiệu về VieNeu Studio nhé!" },
  ]).forEach((t) => c.appendChild(turnRow(t.text || "", t.voice || "")));
  updateCounts();
}
$("#conv-add").addEventListener("click", () => $("#conv-turns").appendChild(turnRow()));
$("#conv-go").addEventListener("click", async () => {
  const btn = $("#conv-go");
  const turns = [...$$("#conv-turns .turn")].map((t) => ({
    voice: t.querySelector(".turn-voice").value,
    text: t.querySelector(".turn-text").value.trim(),
  })).filter((t) => t.text);
  if (!turns.length) return toast("Thêm ít nhất một lượt thoại!", true);
  busy(btn, true, "Đang sinh hội thoại...");
  try {
    const res = await fetch("/api/conversation", {
      method: "POST", headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ turns }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    showAudio("#conv-result", await res.blob(), "vieneu-conversation.wav");
    refreshCounts();
  } catch (e) { toast(e.message, true); }
  finally { busy(btn, false); }
});

// ── Load model (advanced) ──────────────────────────────
// ── API tab ────────────────────────────────────────────
const ORIGIN = window.location.origin;
let API_LANG = "curl";
let AUTH_REQUIRED = false;  // server có bật API key không (lấy từ /api/info)

const ENDPOINTS = [
  { method: "POST", path: "/api/tts", desc: "Sinh giọng từ văn bản → WAV",
    body: { text: "Xin chào lớp học", voice: "Hải Đăng" } },
  { method: "POST", path: "/api/conversation", desc: "Hội thoại đa nhân vật → WAV",
    body: { turns: [{ voice: "Hải Đăng", text: "Chào bạn." }, { voice: "Trúc Ly", text: "Chào nhé!" }] } },
  { method: "GET", path: "/api/voices", desc: "Danh sách giọng mặc định", body: null },
  { method: "GET", path: "/api/stream?text=Xin%20chào&voice=H%E1%BA%A3i%20%C4%90%C4%83ng", desc: "Streaming WAV (phát ngay)", body: null },
  { method: "GET", path: "/api/health", desc: "Trạng thái server/model", body: null },
];

function snippet(ep) {
  const url = ORIGIN + ep.path;
  const isAudio = ep.path.startsWith("/api/tts") || ep.path.startsWith("/api/conversation") || ep.path.startsWith("/api/stream");
  const out = isAudio ? "output.wav" : null;
  // Chỉ endpoint sinh audio mới cần key, và chỉ khi server bật bảo mật.
  const needsKey = AUTH_REQUIRED && isAudio;
  const KEY = getApiKey() || "<API_KEY>";
  if (API_LANG === "curl") {
    const kh = needsKey ? ` \\\n  -H "X-API-Key: ${KEY}"` : "";
    if (ep.method === "GET") return `curl "${url}"${kh}${out ? ` \\\n  --output ${out}` : ""}`;
    return `curl -X POST "${url}" \\\n  -H "Content-Type: application/json"${kh} \\\n  -d '${JSON.stringify(ep.body)}'${out ? ` \\\n  --output ${out}` : ""}`;
  }
  if (API_LANG === "fetch") {
    if (ep.method === "GET") {
      const opt = needsKey ? `, {\n  headers: { "X-API-Key": "${KEY}" }\n}` : "";
      return `const res = await fetch("${url}"${opt});\n${out ? "const blob = await res.blob(); // audio/wav" : "const data = await res.json();\nconsole.log(data);"}`;
    }
    const hdr = needsKey
      ? `{ "Content-Type": "application/json", "X-API-Key": "${KEY}" }`
      : `{ "Content-Type": "application/json" }`;
    return `const res = await fetch("${url}", {\n  method: "POST",\n  headers: ${hdr},\n  body: JSON.stringify(${JSON.stringify(ep.body)})\n});\nconst blob = await res.blob(); // audio/wav`;
  }
  // python
  const pyHdr = needsKey ? `,\n    headers={"X-API-Key": "${KEY}"}` : "";
  if (ep.method === "GET") return `import requests\nr = requests.get("${url}"${needsKey ? `, headers={"X-API-Key": "${KEY}"}` : ""})\n${out ? `open("${out}", "wb").write(r.content)` : "print(r.json())"}`;
  return `import requests\nr = requests.post(\n    "${url}",\n    json=${JSON.stringify(ep.body).replace(/true/g, "True").replace(/false/g, "False")}${pyHdr},\n)\nopen("${out}", "wb").write(r.content)`;
}

// Câu lệnh tổng hợp mọi endpoint trong 1 prompt — dán sang agent AI khác
// (ChatGPT, Claude, Gemini, n8n AI node...) để nó tự gọi API VieNeu.
function aiPrompt() {
  const KEY = getApiKey() || "<API_KEY>";
  const authBlock = AUTH_REQUIRED
    ? `
XÁC THỰC (server NÀY có bật bảo mật — BẮT BUỘC):
Mọi endpoint tạo giọng phải thêm header  X-API-Key: ${KEY}
(riêng /api/stream có thể truyền ?key=${KEY}). Thiếu/sai key sẽ bị lỗi 401.
Giới hạn: text tối đa ~5000 ký tự, file clone tối đa ~5MB.
`
    : "";
  const curlKeyLine = AUTH_REQUIRED ? `\n    -H "X-API-Key: ${KEY}" \\` : "";
  return `Bạn là trợ lý có khả năng gọi API để tạo giọng nói tiếng Việt (text-to-speech).
Server VieNeu Studio đang chạy tại: ${ORIGIN}
Tất cả endpoint đều dùng base URL này. Các endpoint sinh audio trả về dữ liệu nhị phân
định dạng WAV (Content-Type: audio/wav) — hãy lưu thẳng ra file .wav, KHÔNG parse JSON.
Nếu mã trả về khác 200, thân phản hồi là JSON dạng {"detail": "..."} mô tả lỗi.
${authBlock}
QUY TRÌNH CHUẨN khi người dùng muốn đọc/tạo giọng:
1) Kiểm tra server: GET ${ORIGIN}/api/health → {"status": {"loaded": true/false, ...}}.
   Nếu loaded=false thì model chưa sẵn sàng, báo người dùng chờ.
2) Lấy danh sách giọng: GET ${ORIGIN}/api/voices
   → {"voices": [{"id": "...", "label": "Tên hiển thị"}, ...]}.
   Chọn một "id" phù hợp (hoặc để người dùng chọn theo "label").
3) Tạo giọng: POST ${ORIGIN}/api/tts  (Content-Type: application/json)
   Body: {
     "text": "<nội dung tiếng Việt cần đọc>",   // bắt buộc
     "voice": "<id giọng từ bước 2>",            // tùy chọn, bỏ trống = giọng mặc định
     // Cảm xúc: chèn thẳng thẻ vào "text" — [cười] / [thở dài] / [hắng giọng]
     "temperature": 0.8,                          // tùy chọn 0.1–1.5, càng cao càng ngẫu hứng
     "top_k": 25                                  // tùy chọn
   }
   → trả về file WAV. Lưu lại và trả đường dẫn/âm thanh cho người dùng.

ENDPOINT KHÁC khi cần:
- Hội thoại nhiều nhân vật: POST ${ORIGIN}/api/conversation (JSON)
  Body: { "turns": [ {"voice": "<id>", "text": "Lời thoại 1"},
                     {"voice": "<id>", "text": "Lời thoại 2"} ],
          "gap_seconds": 0.4, "temperature": 0.8 } → WAV ghép liền các lượt.
- Phát ngay (streaming): GET ${ORIGIN}/api/stream?text=<urlencoded>&voice=<id> → WAV.
- Nhân bản giọng từ mẫu (clone): POST ${ORIGIN}/api/clone  (multipart/form-data)
  Fields: text=<nội dung>, ref_audio=<file audio mẫu 3–5 giây>,
          temperature=0.8 → WAV đọc theo giọng trong file mẫu.

VÍ DỤ (curl) tạo giọng rồi lưu ra file:
  curl -X POST "${ORIGIN}/api/tts" \\
    -H "Content-Type: application/json" \\${curlKeyLine}
    -d '{"text":"Xin chào lớp học","voice":"<id giọng>"}' \\
    --output ket-qua.wav

NGUYÊN TẮC:
- Luôn lấy "voice" id thật từ /api/voices, đừng bịa id.
- Nội dung "text" nên là tiếng Việt có dấu để phát âm chuẩn.
- Sau khi gọi /api/tts hoặc /api/conversation, kết quả là âm thanh WAV — hãy lưu file
  và trả về cho người dùng (đường dẫn file hoặc trình phát), không in dữ liệu nhị phân ra màn hình.`;
}

function renderAiPrompt(c) {
  c.innerHTML = `
    <div class="endpoint">
      <div class="endpoint-head">
        <span class="method method-post">PROMPT</span>
        <code>Câu lệnh AI tổng hợp</code>
        <button class="btn btn-ghost copy-btn" data-copy="ai-prompt">Sao chép</button>
      </div>
      <div class="hint">Copy đoạn dưới rồi dán vào ChatGPT / Claude / Gemini / n8n (AI node)... để agent tự hiểu cách lấy danh sách giọng, chọn giọng, tạo TTS và trả kết quả.</div>
      <pre class="code" id="ai-prompt">${escapeHtml(aiPrompt())}</pre>
    </div>`;
  bindCopy();
}

function renderApiEndpoints() {
  const base = $("#api-base");
  if (base) base.textContent = ORIGIN;
  const c = $("#api-endpoints");
  if (!c) return;
  if (API_LANG === "ai") return renderAiPrompt(c);
  let notice = "";
  if (AUTH_REQUIRED) {
    notice = getApiKey()
      ? `<div class="hint" style="margin-bottom:12px">🔑 Server có bật API key — các ví dụ dưới đã tự điền key của bạn (từ tab Cài đặt).</div>`
      : `<div class="hint" style="margin-bottom:12px">🔑 Server có bật API key. Nhập key ở tab <b>Cài đặt</b> để các ví dụ tự điền, hoặc thay <code>&lt;API_KEY&gt;</code> bằng key được cấp.</div>`;
  }
  c.innerHTML = notice + ENDPOINTS.map((ep, i) => `
    <div class="endpoint">
      <div class="endpoint-head">
        <span class="method method-${ep.method.toLowerCase()}">${ep.method}</span>
        <code>${ep.path}</code>
        <button class="btn btn-ghost copy-btn" data-copy="ep-${i}">Sao chép</button>
      </div>
      <div class="hint">${ep.desc}</div>
      <pre class="code" id="ep-${i}">${escapeHtml(snippet(ep))}</pre>
    </div>`).join("");
  bindCopy();
}

function renderApiTable() {
  const t = $("#api-table");
  if (!t) return;
  t.innerHTML = ENDPOINTS.concat([
    { method: "POST", path: "/api/clone", desc: "Clone giọng: multipart text + ref_audio (file 3–5s)" },
    { method: "POST", path: "/api/load", desc: "(nâng cao) đổi model: {mode, backbone_repo, device}" },
    { method: "GET", path: "/api/version", desc: "Phiên bản app/SDK/python" },
    { method: "GET", path: "/api/changelog", desc: "Nhật ký cập nhật" },
    { method: "GET", path: "/api/logs?lines=200", desc: "Logs server gần đây" },
  ]).map((ep) => `<div class="api-row"><span class="method method-${ep.method.toLowerCase()}">${ep.method}</span><code>${ep.path.split("?")[0]}</code><span>${ep.desc}</span></div>`).join("");
}

$$("#api-lang-tabs .tab").forEach((t) => t.addEventListener("click", () => {
  $$("#api-lang-tabs .tab").forEach((x) => x.classList.remove("active"));
  t.classList.add("active");
  API_LANG = t.dataset.lang;
  renderApiEndpoints();
}));

function escapeHtml(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function bindCopy() {
  $$(".copy-btn").forEach((b) => b.addEventListener("click", async () => {
    const el = document.getElementById(b.dataset.copy);
    if (!el) return;
    try { await navigator.clipboard.writeText(el.textContent); toast("Đã sao chép!"); }
    catch { toast("Không sao chép được (trình duyệt chặn).", true); }
  }));
}

// ── Version & changelog ────────────────────────────────
async function loadVersion() {
  try {
    const v = await (await fetch("/api/version")).json();
    $("#ver-app").textContent = `${v.app} ${v.edition || ""}`.trim();
    $("#ver-num").textContent = "v" + v.version;
    $("#ver-sdk").textContent = v.vieneu_sdk;
    $("#ver-py").textContent = v.python;
    $("#ver-os").textContent = v.platform;
  } catch (e) { console.error(e); }
  try {
    const info = await (await fetch("/api/info")).json();
    const L = info.branding.links || {};
    const gh = L.app_github || L.github;
    if (gh) $("#ver-github").href = gh + "/releases";
  } catch {}
  try {
    const cl = await (await fetch("/api/changelog")).json();
    $("#changelog").innerHTML = (cl.entries || []).map((e) => `
      <div class="cl-entry">
        <div class="cl-head"><span class="badge badge-blue">v${e.version}</span> <span class="cl-date">${e.date || ""}</span></div>
        <div class="cl-title">${e.title || ""}</div>
        <ul class="cl-list">${(e.changes || []).map((c) => `<li>${c}</li>`).join("")}</ul>
      </div>`).join("");
  } catch (e) { console.error(e); }
}

// ── Logs ───────────────────────────────────────────────
let LOG_TIMER = null;
async function loadLogs() {
  const viewer = $("#log-viewer");
  if (!viewer) return;
  try {
    const level = $("#log-level").value;
    const res = await fetch(`/api/logs?lines=300&level=${level}`, { headers: adminHeaders() });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      viewer.textContent = "Logs cần Admin key (vào tab Cài đặt để nhập). " + (d.detail || "");
      return;
    }
    const data = await res.json();
    const lines = (data.lines || []).map((l) => `${l.time}  ${l.level.padEnd(7)} ${l.name}  ${l.msg}`);
    viewer.textContent = lines.length ? lines.join("\n") : "(chưa có log)";
    viewer.scrollTop = viewer.scrollHeight;
  } catch (e) { viewer.textContent = "Lỗi tải logs: " + e.message; }
}
$("#log-refresh").addEventListener("click", loadLogs);
$("#log-level").addEventListener("change", loadLogs);
$("#log-copy").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText($("#log-viewer").textContent); toast("Đã sao chép logs!"); }
  catch { toast("Không sao chép được.", true); }
});
$("#log-auto").addEventListener("change", (e) => {
  if (e.target.checked) { loadLogs(); LOG_TIMER = setInterval(loadLogs, 3000); }
  else { clearInterval(LOG_TIMER); LOG_TIMER = null; }
});

// Nạp nội dung khi mở trang
TAB_HOOKS.api = () => { renderApiEndpoints(); renderApiTable(); };
TAB_HOOKS.version = () => { loadVersion(); loadLogs(); };
TAB_HOOKS.voices = () => loadMyVoices();
TAB_HOOKS.history = () => loadHistory();

$("#set-load").addEventListener("click", async () => {
  const btn = $("#set-load");
  busy(btn, true, "Đang tải...");
  try {
    const res = await fetch("/api/load", {
      method: "POST", headers: adminHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        mode: $("#set-mode").value,
        backbone_repo: $("#set-repo").value.trim() || null,
        device: $("#set-device-sel").value,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    setStatus(data.status);
    toast("Đã tải model.");
    loadVoices();
  } catch (e) { toast(e.message, true); }
  finally { busy(btn, false); }
});

// ── Thư viện: tiện ích chung ───────────────────────────
function setCount(name, n) {
  const el = $("#count-" + name);
  if (el) el.textContent = n ? String(n) : "";
}
// <audio src> / <a href> không gửi được header → truyền key qua ?key= (nếu có).
function withKey(url) {
  const k = getApiKey();
  return k ? url + (url.includes("?") ? "&" : "?") + "key=" + encodeURIComponent(k) : url;
}
function fmtTime(sec) {
  if (!sec) return "";
  return new Date(sec * 1000).toLocaleString("vi-VN", {
    hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit", year: "numeric",
  });
}
function fmtDur(sec) {
  const s = Math.max(0, Math.round(sec || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
// "v3turbo · pnnbao-ump/VieNeu-TTS-v3-Turbo" → "v3turbo · VieNeu-TTS-v3-Turbo"
function shortModel(m) { return String(m || "").replace(/[\w.-]+\//, ""); }
async function apiJson(url, opts = {}) {
  const res = await fetch(url, Object.assign({}, opts, { headers: authHeaders(opts.headers) }));
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}
async function refreshCounts() {
  if (!LIBRARY_ON) return;
  try {
    HISTORY = (await apiJson("/api/history")).runs || [];
    setCount("history", HISTORY.length);
    renderRecent();
  } catch {}
}

// Cột phải các trang Tạo: 3 lượt gần nhất cùng loại.
function renderRecent() {
  $$("[data-recent]").forEach((box) => {
    const runs = HISTORY.filter((r) => r.kind === box.dataset.recent).slice(0, 3);
    if (!runs.length) { box.innerHTML = `<div class="recent-empty">Chưa có lượt nào.</div>`; return; }
    box.innerHTML = runs.map((r) => `<div class="recent-item" data-id="${escapeHtml(r.id)}">
      <div class="recent-head"><b>🎤 ${escapeHtml(r.voice)}</b><span class="meta">${fmtDur(r.duration)}</span></div>
      <div class="recent-text" title="Bấm để dùng lại">${escapeHtml(r.text)}</div>
      <audio controls preload="none" src="${withKey(`/api/history/${r.id}/audio`)}"></audio>
    </div>`).join("");
  });
}
document.addEventListener("click", (e) => {
  const t = e.target.closest(".recent-text");
  if (!t) return;
  const run = HISTORY.find((r) => r.id === t.closest(".recent-item").dataset.id);
  if (run) reuseRun(run);
});

// ── Lịch sử ────────────────────────────────────────────
const KINDS = {
  tts: ["Sinh giọng", "badge-orange"],
  clone: ["Clone", "badge-blue"],
  conversation: ["Hội thoại", "badge-green"],
};
let HISTORY = [];

async function loadHistory() {
  const box = $("#history-list");
  if (!HISTORY.length) box.innerHTML = `<div class="empty">Đang tải lịch sử...</div>`;
  try {
    const data = await apiJson("/api/history");
    HISTORY = data.runs || [];
    HISTORY_MAX = data.max || HISTORY_MAX;
    setCount("history", HISTORY.length);
    renderHistory();
    renderRecent();
  } catch (e) {
    box.innerHTML = `<div class="empty">Không tải được lịch sử: ${escapeHtml(e.message)}</div>`;
  }
}

function renderHistory() {
  const box = $("#history-list");
  const kind = $("#history-filter").value;
  const runs = kind ? HISTORY.filter((r) => r.kind === kind) : HISTORY;
  $("#history-summary").textContent =
    `${HISTORY.length}/${HISTORY_MAX} lượt gần nhất — vượt ${HISTORY_MAX} thì lượt cũ nhất tự xóa.`;
  $("#history-clear").disabled = !HISTORY.length;
  if (!runs.length) {
    box.innerHTML = `<div class="empty"><div class="big">🕘</div>
      <b>${HISTORY.length ? "Không có lượt nào thuộc loại này." : "Chưa có lượt sinh audio nào."}</b>
      <p class="hint">Mỗi lần sinh giọng, clone hay hội thoại đều được lưu ở đây để nghe lại và tải xuống.</p></div>`;
    return;
  }
  box.innerHTML = runs.map((r) => {
    const [label, cls] = KINDS[r.kind] || [r.kind, "badge-gray"];
    return `<article class="run" data-id="${escapeHtml(r.id)}">
      <div class="run-head">
        <span class="badge ${cls}">${label}</span>
        <b>🎤 ${escapeHtml(r.voice)}</b>
        <span class="meta">· ${fmtDur(r.duration)} · ${escapeHtml(shortModel(r.model))}</span>
        <span class="meta when">${fmtTime(r.created)}</span>
      </div>
      <div class="run-text" title="Bấm để xem đầy đủ">${escapeHtml(r.text)}</div>
      <audio controls preload="none" src="${withKey(`/api/history/${r.id}/audio`)}"></audio>
      <div class="actions">
        <a class="btn btn-ghost btn-sm" href="${withKey(`/api/history/${r.id}/audio?download=1`)}" download>⬇ Tải xuống</a>
        <button class="btn btn-ghost btn-sm" data-act="reuse">↺ Dùng lại</button>
        <button class="btn btn-ghost btn-sm btn-danger" data-act="del">🗑 Xóa</button>
      </div>
    </article>`;
  }).join("");
}

function reuseRun(r) {
  if (r.kind === "conversation") {
    showTab("conversation");
    buildConversation(r.turns);
  } else if (r.kind === "clone") {
    showTab("clone");
    $("#clone-text").value = r.text;
    toast("Đã điền lại nội dung — chọn lại file audio mẫu để clone.");
  } else {
    showTab("synthesize");
    $("#syn-text").value = r.text;
    if (VOICES.some((v) => v.id === r.voice)) $("#syn-voice").value = r.voice;
    else toast(`Giọng "${r.voice}" không còn trong danh sách — hãy chọn giọng khác.`, true);
  }
}

$("#history-list").addEventListener("click", async (e) => {
  const card = e.target.closest(".run");
  if (!card) return;
  const run = HISTORY.find((r) => r.id === card.dataset.id);
  if (e.target.closest(".run-text")) { e.target.closest(".run-text").classList.toggle("open"); return; }
  const act = e.target.closest("[data-act]")?.dataset.act;
  if (!act || !run) return;
  if (act === "reuse") return reuseRun(run);
  if (act === "del") {
    try {
      await apiJson(`/api/history/${run.id}`, { method: "DELETE" });
      HISTORY = HISTORY.filter((r) => r.id !== run.id);
      setCount("history", HISTORY.length);
      renderHistory();
      renderRecent();
    } catch (err) { toast(err.message, true); }
  }
});
$("#history-filter").addEventListener("change", renderHistory);
$("#history-refresh").addEventListener("click", loadHistory);
$("#history-clear").addEventListener("click", async () => {
  if (!confirm(`Xóa toàn bộ ${HISTORY.length} lượt trong lịch sử? Không hoàn tác được.`)) return;
  try {
    await apiJson("/api/history", { method: "DELETE" });
    HISTORY = [];
    setCount("history", 0);
    renderHistory();
    renderRecent();
    toast("Đã xóa lịch sử.");
  } catch (err) { toast(err.message, true); }
});

// ── Giọng của tôi ──────────────────────────────────────
const TRY_TEXT = "Xin chào, đây là giọng của tôi được tạo bằng VieNeu Studio.";
let MY_VOICES = [];

async function loadMyVoices() {
  const box = $("#voices-list");
  if (!MY_VOICES.length) box.innerHTML = `<div class="empty">Đang tải... (lần đầu sẽ tải model)</div>`;
  try {
    MY_VOICES = (await apiJson("/api/voices/custom")).voices || [];
    setCount("voices", MY_VOICES.length);
    renderMyVoices();
  } catch (e) {
    box.innerHTML = `<div class="empty">Không tải được giọng: ${escapeHtml(e.message)}</div>`;
  }
}

function renderMyVoices() {
  const box = $("#voices-list");
  if (!MY_VOICES.length) {
    box.innerHTML = `<div class="empty"><div class="big">🎙️</div>
      <b>Chưa có giọng nào.</b>
      <p class="hint">Vào <b>Clone giọng</b>, tải 3–5 giây audio mẫu và nghe thử — hài lòng thì bấm <b>Lưu giọng</b>.</p>
      <div class="actions" style="justify-content:center"><button class="btn btn-primary" data-goto="clone">Clone giọng đầu tiên</button></div></div>`;
    return;
  }
  box.innerHTML = MY_VOICES.map((v) => `
    <div class="card voice-card" data-name="${escapeHtml(v.name)}">
      <div class="card-title">⭐ ${escapeHtml(v.name)}</div>
      <div class="meta">${v.created ? "Lưu lúc " + fmtTime(v.created) : "Lưu từ ứng dụng VieNeu khác"}${v.model ? " · " + escapeHtml(shortModel(v.model)) : ""}</div>
      ${v.has_clip ? `<div class="meta">Audio mẫu gốc</div>
      <audio controls preload="none" src="${withKey("/api/voices/custom/clip?name=" + encodeURIComponent(v.name))}"></audio>` : ""}
      <div class="try-result"></div>
      <div class="actions">
        <button class="btn btn-primary btn-sm" data-act="use">Dùng giọng này</button>
        <button class="btn btn-ghost btn-sm" data-act="try">▶ Nghe thử</button>
        <button class="btn btn-ghost btn-sm" data-act="rename">✎ Đổi tên</button>
        <button class="btn btn-ghost btn-sm btn-danger" data-act="del" title="Xóa giọng">🗑</button>
      </div>
    </div>`).join("");
}

async function afterVoicesChanged() {
  await Promise.all([loadMyVoices(), loadVoices()]);
}

$("#voices-list").addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-act]");
  const card = e.target.closest(".voice-card");
  if (!btn || !card) return;
  const name = card.dataset.name;
  const act = btn.dataset.act;

  if (act === "use") {
    showTab("synthesize");
    $("#syn-voice").value = name;
    toast(`Đã chọn giọng "${name}".`);
  } else if (act === "try") {
    busy(btn, true, "Đang sinh...");
    try {
      const res = await fetch("/api/tts", {
        method: "POST", headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ text: TRY_TEXT, voice: name }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
      const url = URL.createObjectURL(await res.blob());
      card.querySelector(".try-result").innerHTML = `<div class="meta">Nghe thử</div><audio controls autoplay src="${url}"></audio>`;
      refreshCounts();
    } catch (err) { toast(err.message, true); }
    finally { busy(btn, false); }
  } else if (act === "rename") {
    const next = (prompt(`Đổi tên giọng "${name}" thành:`, name) || "").trim();
    if (!next || next === name) return;
    try {
      await apiJson("/api/voices/custom", {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ old: name, new: next }),
      });
      toast(`Đã đổi tên thành "${next}".`);
      await afterVoicesChanged();
    } catch (err) { toast(err.message, true); }
  } else if (act === "del") {
    if (!confirm(`Xóa giọng "${name}"? Không hoàn tác được.`)) return;
    try {
      await apiJson("/api/voices/custom?name=" + encodeURIComponent(name), { method: "DELETE" });
      toast(`Đã xóa giọng "${name}".`);
      await afterVoicesChanged();
    } catch (err) { toast(err.message, true); }
  }
});

// ── Lưu/nạp khóa truy cập ──────────────────────────────
function initKeys() {
  const a = $("#set-apikey"), b = $("#set-adminkey");
  if (a) a.value = getApiKey();
  if (b) b.value = getAdminKey();
}
const _saveKeysBtn = $("#set-savekeys");
if (_saveKeysBtn) _saveKeysBtn.addEventListener("click", () => {
  localStorage.setItem("vieneu_api_key", ($("#set-apikey").value || "").trim());
  localStorage.setItem("vieneu_admin_key", ($("#set-adminkey").value || "").trim());
  toast("Đã lưu khóa truy cập.");
  renderApiEndpoints();  // cập nhật lại ví dụ API để điền key mới
});
initKeys();

// ── Kho giọng: nghe thử các giọng có sẵn (file tĩnh trong /previews) ──
let PREVIEWS = null;          // { text, voices: { id: {file, duration, gender, region, style, featured} } }
let GALLERY_FILTER = "";
const PREVIEW_AUDIO = new Audio();
let PREVIEW_ID = null;        // giọng đang phát

async function loadPreviews() {
  if (PREVIEWS) return PREVIEWS;
  try { PREVIEWS = await (await fetch("/previews/voices.json")).json(); }
  catch { PREVIEWS = { text: "", voices: {} }; }
  setCount("gallery", Object.keys(PREVIEWS.voices).length);
  return PREVIEWS;
}
function previewUrl(id) {
  const v = PREVIEWS && PREVIEWS.voices[id];
  if (v) return "/previews/" + encodeURIComponent(v.file);
  const mine = VOICES.find((x) => x.id === id && x.custom);
  return mine ? withKey("/api/voices/custom/clip?name=" + encodeURIComponent(id)) : null;
}
function togglePreview(id) {
  if (PREVIEW_ID === id && !PREVIEW_AUDIO.paused) { PREVIEW_AUDIO.pause(); return; }
  const url = previewUrl(id);
  if (!url) return toast("Giọng này chưa có audio nghe thử.", true);
  PREVIEW_ID = id;
  PREVIEW_AUDIO.src = url;
  PREVIEW_AUDIO.play().catch((e) => toast("Không phát được: " + e.message, true));
}
function syncPreviewUi() {
  const playing = !PREVIEW_AUDIO.paused;
  $$("[data-preview]").forEach((b) => {
    const on = playing && b.dataset.preview === PREVIEW_ID;
    b.classList.toggle("playing", on);
    b.innerHTML = on ? "❚❚" : "▶";
    b.closest(".gv-card")?.classList.toggle("playing", on);
  });
  const sb = $("#syn-preview");
  const on = playing && PREVIEW_ID === $("#syn-voice").value;
  sb.textContent = on ? "❚❚ Dừng" : "▶ Nghe thử";
  sb.classList.toggle("playing", on);
}
["play", "pause", "ended"].forEach((ev) => PREVIEW_AUDIO.addEventListener(ev, syncPreviewUi));
PREVIEW_AUDIO.addEventListener("timeupdate", () => {
  const bar = document.querySelector(`.gv-card[data-id="${CSS.escape(PREVIEW_ID || "")}"] .gv-progress span`);
  if (bar && PREVIEW_AUDIO.duration) bar.style.width = (100 * PREVIEW_AUDIO.currentTime / PREVIEW_AUDIO.duration) + "%";
});
PREVIEW_AUDIO.addEventListener("ended", () => { $$(".gv-progress span").forEach((s) => (s.style.width = "0")); });

$("#syn-preview").addEventListener("click", async () => { await loadPreviews(); togglePreview($("#syn-voice").value); });
$("#syn-voice").addEventListener("change", () => { if (!PREVIEW_AUDIO.paused) PREVIEW_AUDIO.pause(); syncPreviewUi(); });

function renderGallery() {
  const grid = $("#gallery-grid");
  const all = Object.entries(PREVIEWS.voices);
  $("#gallery-text").textContent = (PREVIEWS.display_text || PREVIEWS.text || "").replace("{name}", "<tên giọng>");
  const f = GALLERY_FILTER;
  const list = all.filter(([, v]) =>
    !f || (f === "star" ? v.featured : f.startsWith("g:") ? v.gender === f.slice(2) : v.region === f.slice(2)));
  if (!list.length) { grid.innerHTML = `<div class="empty">Không có giọng nào khớp bộ lọc.</div>`; return; }
  grid.innerHTML = list.map(([id, v]) => `
    <article class="gv-card" data-id="${escapeHtml(id)}">
      <div class="gv-top">
        <button class="gv-play" data-preview="${escapeHtml(id)}" title="Nghe thử">▶</button>
        <div class="gv-info">
          <div class="gv-name">${escapeHtml(id)}${v.featured ? ' <span title="Nổi bật">⭐</span>' : ""}</div>
          <div class="gv-tags"><span>${v.gender === "Nữ" ? "👩" : "👨"} ${escapeHtml(v.gender)}</span><span>Miền ${escapeHtml(v.region)}</span><span>${fmtDur(v.duration)}</span></div>
        </div>
      </div>
      <div class="gv-style">${escapeHtml(v.style)}</div>
      <div class="gv-progress"><span></span></div>
      <button class="btn btn-ghost btn-sm" data-use="${escapeHtml(id)}">Dùng giọng này →</button>
    </article>`).join("");
  syncPreviewUi();
}
TAB_HOOKS.gallery = async () => { await loadPreviews(); renderGallery(); };
$("#gallery-filters").addEventListener("click", (e) => {
  const c = e.target.closest(".chip");
  if (!c) return;
  GALLERY_FILTER = c.dataset.f;
  $$("#gallery-filters .chip").forEach((x) => x.classList.toggle("active", x === c));
  renderGallery();
});
document.addEventListener("click", (e) => {
  const p = e.target.closest("[data-preview]");
  if (p) return togglePreview(p.dataset.preview);
  const u = e.target.closest("[data-use]");
  if (u) {
    PREVIEW_AUDIO.pause();
    showTab("synthesize");
    if (VOICES.some((v) => v.id === u.dataset.use)) $("#syn-voice").value = u.dataset.use;
    renderEmoChips();
    toast(`Đã chọn giọng "${u.dataset.use}".`);
  }
});

init();
