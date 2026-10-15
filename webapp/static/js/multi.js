// ── Đa ngôn ngữ (OmniVoice) ───────────────────────────
// Gói cài thêm (~4 GB). Trang này: cài đặt có tiến độ → chọn ngôn ngữ, giọng → sinh audio.
const MULTI_SAMPLES = {
  English: "Welcome to AI Audio Studio. This voice was created by artificial intelligence, running entirely on your own computer.",
  Korean: "안녕하세요. AI 오디오 스튜디오에 오신 것을 환영합니다. 이 목소리는 인공지능으로 만들어졌습니다.",
  Japanese: "こんにちは。AIオーディオスタジオへようこそ。この声は人工知能で作られました。",
  Chinese: "欢迎使用 AI Audio Studio。这个声音由人工智能生成，完全在你的电脑上运行。",
  Cantonese: "歡迎使用 AI Audio Studio。呢把聲係由人工智能生成嘅。",
  Filipino: "Magandang araw! Maligayang pagdating sa AI Audio Studio. Ang boses na ito ay ginawa ng artificial intelligence.",
  Thai: "ยินดีต้อนรับสู่ AI Audio Studio เสียงนี้สร้างขึ้นด้วยปัญญาประดิษฐ์",
  Indonesian: "Selamat datang di AI Audio Studio. Suara ini dibuat oleh kecerdasan buatan di komputer Anda.",
  Malay: "Selamat datang ke AI Audio Studio. Suara ini dihasilkan oleh kecerdasan buatan.",
  French: "Bienvenue dans AI Audio Studio. Cette voix a été créée par une intelligence artificielle, directement sur votre ordinateur.",
  Spanish: "Bienvenido a AI Audio Studio. Esta voz fue creada por inteligencia artificial, directamente en tu computadora.",
  German: "Willkommen bei AI Audio Studio. Diese Stimme wurde von künstlicher Intelligenz erzeugt.",
  Russian: "Добро пожаловать в AI Audio Studio. Этот голос создан искусственным интеллектом.",
  Portuguese: "Bem-vindo ao AI Audio Studio. Esta voz foi criada por inteligência artificial.",
  Italian: "Benvenuto in AI Audio Studio. Questa voce è stata creata dall'intelligenza artificiale.",
  Hindi: "AI Audio Studio में आपका स्वागत है। यह आवाज़ कृत्रिम बुद्धिमत्ता से बनाई गई है।",
  "Standard Arabic": "مرحبًا بك في AI Audio Studio. تم إنشاء هذا الصوت بواسطة الذكاء الاصطناعي.",
  Vietnamese: "Xin chào, mình là trợ lý giọng nói. Hôm nay trời đẹp quá, bạn có muốn cùng mình đi uống một ly cà phê sữa đá không?",
};
let MULTI = null;          // trạng thái từ /api/multi/status
let MULTI_POLL = null;
let MULTI_MAX = 2000;
let MULTI_TOUCHED = false; // người dùng đã tự gõ nội dung → đổi ngôn ngữ không ghi đè

const gb = (b) => (b / 1e9).toLocaleString("vi-VN", { maximumFractionDigits: 1 }) + " GB";

async function loadMulti() {
  try {
    MULTI = await apiJson("/api/multi/status");
  } catch (e) {
    $("#multi-setup").hidden = true; $("#multi-form").hidden = true;
    return toast("Không tải được trạng thái Đa ngôn ngữ: " + e.message, true);
  }
  MULTI_MAX = MULTI.max_chars || 2000;
  renderMulti();
  const running = MULTI.install && MULTI.install.state === "running";
  if (running && !MULTI_POLL) MULTI_POLL = setInterval(loadMulti, 2000);
  if (!running && MULTI_POLL) { clearInterval(MULTI_POLL); MULTI_POLL = null; }
}

function renderMulti() {
  const m = MULTI, ins = m.install || {};
  $("#multi-hosted").hidden = !m.hosted;
  $("#multi-setup").hidden = m.hosted || m.installed;
  $("#multi-form").hidden = m.hosted || !m.installed;
  $("#multi-manage").hidden = m.hosted || !m.installed;
  $("#multi-hw-note").textContent = m.hardware.speed_note;
  $("#multi-speed-note").textContent = m.hardware.accel === "cpu" ? "⚠️ Máy chạy bằng CPU — sinh chậm, nên dùng đoạn ngắn." : "";
  $("#multi-attr").textContent = m.attribution || "";

  // Tiến độ cài
  const btn = $("#multi-install");
  if (!m.hardware.supported) {
    btn.disabled = true; $("#multi-install-hint").textContent = m.hardware.reason;
  } else {
    btn.disabled = ins.state === "running";
    btn.textContent = ins.state === "error" ? "↻ Cài lại" : ins.state === "running" ? "Đang cài..." : "⬇ Cài gói Đa ngôn ngữ";
  }
  $("#multi-progress").hidden = !(ins.state === "running" || ins.state === "error");
  $("#multi-bar").style.width = Math.round((ins.progress || 0) * 100) + "%";
  $("#multi-step").textContent = ins.state === "error"
    ? "❌ " + (ins.error || "Cài không thành công") + " — kiểm tra mạng rồi bấm Cài lại."
    : `${ins.step || "Đang chuẩn bị..."} · ${Math.round((ins.progress || 0) * 100)}%`;
  $("#multi-log").textContent = (ins.log || []).slice(-4).join("\n");

  if (!m.installed) return;
  // Trạng thái model
  const disk = (m.disk.engine_bytes || 0) + (m.disk.model_bytes || 0);
  $("#multi-state").textContent = (m.loaded ? `Model đang chạy trên ${m.device.toUpperCase()}.` : "Model chưa nạp (tự nạp ở lần sinh đầu).")
    + ` Dung lượng: ${gb(disk)}.`;
  $("#multi-unload").disabled = !m.loaded;

  // Ô chọn (chỉ dựng một lần)
  const lang = $("#multi-lang");
  if (!lang.options.length) {
    lang.innerHTML = m.languages.map((l) => `<option value="${escapeHtml(l.id)}">${escapeHtml(l.label)}</option>`).join("");
    const v = m.voices;
    $("#multi-voice").innerHTML =
      `<optgroup label="Giọng có sẵn (nhanh)">${v.designed.map((d) => `<option value="${escapeHtml(d.id)}">${escapeHtml(d.label)}</option>`).join("")}</optgroup>` +
      `<optgroup label="Giọng Việt (VieNeu) nói tiếng nước ngoài — chậm hơn">${v.vieneu.map((d) => `<option value="${escapeHtml(d.id)}">${escapeHtml(d.label)}</option>`).join("")}</optgroup>` +
      `<optgroup label="Giọng của bạn"><option value="__clone__">🎙️ Clone từ file mẫu của bạn…</option></optgroup>`;
    $("#multi-accent").innerHTML = v.accents.map((a) => `<option value="${escapeHtml(a.id)}">${escapeHtml(a.label)}</option>`).join("");
    if (!$("#multi-text").value) $("#multi-text").value = MULTI_SAMPLES.English;
    syncMultiFields();
  }
}

function syncMultiFields() {
  const isEn = $("#multi-lang").value === "English";
  const v = $("#multi-voice").value;
  const isClone = v === "__clone__";
  $("#multi-accent-field").hidden = !isEn || v.startsWith("vn:") || isClone;
  $("#multi-clone").hidden = !isClone;
  multiCount();
}

function multiCount() {
  const t = $("#multi-text").value, n = t.length, box = $("#multi-count");
  box.className = "text-meta" + (n > MULTI_MAX ? " over" : n > 800 ? " soft" : "");
  box.querySelector(".count-num").textContent = `${n.toLocaleString("vi-VN")} / ${MULTI_MAX.toLocaleString("vi-VN")} ký tự`;
  box.querySelector(".count-msg").textContent = n > MULTI_MAX ? "Quá dài — hãy chia nhỏ." : n > 800 ? "Đoạn dài — sinh sẽ lâu, nên chia nhỏ." : "";
  if (!$("#multi-go").querySelector(".spinner")) $("#multi-go").disabled = n > MULTI_MAX;
}

$("#multi-lang").addEventListener("change", () => {
  const s = MULTI_SAMPLES[$("#multi-lang").value];
  if (s && !MULTI_TOUCHED) $("#multi-text").value = s;
  syncMultiFields();
});
$("#multi-voice").addEventListener("change", syncMultiFields);
$("#multi-text").addEventListener("input", () => { MULTI_TOUCHED = true; multiCount(); });

$("#multi-install").addEventListener("click", async () => {
  if (!confirm("Cài gói Đa ngôn ngữ (~4 GB)? Cần mạng ổn định, mất khoảng 5–20 phút. Bạn vẫn dùng app bình thường trong lúc cài.")) return;
  try {
    await apiJson("/api/multi/install", { method: "POST" });
    toast("Bắt đầu cài gói Đa ngôn ngữ…");
    loadMulti();
  } catch (e) { toast(e.message, true); }
});

$("#multi-unload").addEventListener("click", async () => {
  try { await apiJson("/api/multi/unload", { method: "POST" }); toast("Đã tắt model, trả lại RAM."); loadMulti(); }
  catch (e) { toast(e.message, true); }
});

$("#multi-remove").addEventListener("click", async () => {
  if (!confirm("Gỡ gói Đa ngôn ngữ? Xoá PyTorch, OmniVoice và model (~4 GB). Muốn dùng lại phải tải lại.")) return;
  try {
    const r = await apiJson("/api/multi/uninstall", { method: "POST" });
    toast(`Đã gỡ, giải phóng ${gb(r.freed_bytes || 0)}.`);
    $("#multi-lang").innerHTML = "";
    loadMulti();
  } catch (e) { toast(e.message, true); }
});

$("#multi-go").addEventListener("click", async () => {
  const btn = $("#multi-go");
  const text = $("#multi-text").value.trim();
  if (!text) return toast("Nhập nội dung đã!", true);
  const isClone = $("#multi-voice").value === "__clone__";
  if (isClone && !$("#multi-ref").files[0]) return toast("Chọn file giọng mẫu đã!", true);
  if (isClone && !$("#multi-ref-text").value.trim()) return toast("Gõ câu nói trong file mẫu (bắt buộc).", true);
  busy(btn, true, MULTI && MULTI.loaded ? "Đang sinh..." : "Đang nạp model + sinh...");
  const t0 = performance.now();
  try {
    let res;
    if (isClone) {
      const fd = new FormData();
      fd.append("text", text);
      fd.append("ref_text", $("#multi-ref-text").value.trim());
      fd.append("ref_audio", $("#multi-ref").files[0]);
      fd.append("language", $("#multi-lang").value);
      fd.append("fast", $("#multi-fast").checked ? "true" : "false");
      fd.append("speed", $("#multi-speed").value || "1");
      res = await fetch("/api/multi/clone", { method: "POST", headers: authHeaders(), body: fd });
    } else {
      res = await fetch("/api/multi/tts", {
        method: "POST", headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          text, language: $("#multi-lang").value, voice: $("#multi-voice").value,
          accent: $("#multi-accent-field").hidden ? "" : $("#multi-accent").value,
          fast: $("#multi-fast").checked, speed: parseFloat($("#multi-speed").value) || 1,
        }),
      });
    }
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const lang = ($("#multi-lang").value || "audio").toLowerCase().replace(/\s+/g, "-");
    showAudio("#multi-result", await res.blob(), `ai-audio-studio-${lang}.wav`);
    toast(`Xong sau ${((performance.now() - t0) / 1000).toFixed(1)} giây.`);
    refreshCounts();
    loadMulti();
  } catch (e) { toast(e.message, true); }
  finally { busy(btn, false); multiCount(); }
});

// Dùng lại một lượt trong Lịch sử
window.multiReuse = (r) => {
  showTab("multi");
  const fill = () => {
    if (r.language && [...$("#multi-lang").options].some((o) => o.value === r.language)) $("#multi-lang").value = r.language;
    $("#multi-text").value = r.text; MULTI_TOUCHED = true; syncMultiFields();
  };
  $("#multi-lang").options.length ? fill() : setTimeout(fill, 800);
};

TAB_HOOKS.multi = loadMulti;
if (location.hash === "#multi") loadMulti();

// Dữ liệu đa ngôn ngữ cho trang Hội thoại + API (đọc một lần lúc mở app, không chặn giao diện)
window.MULTI_CACHE = null;
(async () => {
  try { window.MULTI_CACHE = await apiJson("/api/multi/status"); } catch { return; }
  window.dispatchEvent(new Event("multi-ready"));
})();
