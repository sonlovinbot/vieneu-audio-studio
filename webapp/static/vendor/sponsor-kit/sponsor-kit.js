/*! Sponsor Kit v1.0 — góc quảng cáo + thư ngỏ + "Phát triển bởi" cho phần mềm miễn phí.
 *  Không phụ thuộc thư viện. Dùng cho cả app chạy local (đọc tin qua proxy /api/news của app)
 *  lẫn website (đọc thẳng news.json trên GitHub Pages / CDN).
 *
 *  SponsorKit.init({
 *    appName: "AI Audio Studio",            // tên phần mềm (hiện trong thư ngỏ)
 *    appVersion: "1.7.3",                   // bỏ trống nếu feed trả về { version }
 *    feedUrl: "/api/news",                  // local: proxy của app · web: https://…/news.json
 *    slots: { top: "#news-top", side: "#news-side" },
 *    utm: { source: "ai_audio_studio", medium: "local_app" },
 *    sponsorName: "Coachio Academy",
 *    developer: { name: "Đặng Hữu Sơn", title: "CEO & Co-Founder LovinBot AI", url: "https://…" },
 *    appId: "ai_audio_studio",              // lọc mục có "apps": [...] trong feed dùng chung
 *    storagePrefix: "aias",                 // khoá localStorage riêng cho từng app
 *    slots.credit: "#credit",               // (tuỳ chọn) khung "Phát triển bởi", basedOn: "Dựa trên …"
 *  })
 *
 *  An toàn: mọi nội dung từ xa gắn bằng textContent / thuộc tính — không chèn HTML, không chạy
 *  mã từ xa; link và ảnh chỉ nhận https. Quảng cáo (placement "side" hoặc tone "promo") bắt buộc
 *  có ngày kết thúc `end`; ngày tính theo giờ máy người dùng.
 */
(function (global) {
  "use strict";
  const ICON = { info: "ℹ️", warning: "⚠️", promo: "🎉", update: "🚀" };
  let CFG = null;

  // ── tiện ích ─────────────────────────────────────────
  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    return e;
  };
  const https = (u) => (typeof u === "string" && /^https:\/\//.test(u.trim()) ? u.trim() : "");
  const key = (k) => `${CFG.storagePrefix || "sk"}_${k}`;
  const store = {
    get(k, d) { try { return JSON.parse(localStorage.getItem(key(k)) ?? "null") ?? d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(key(k), JSON.stringify(v)); } catch {} },
  };
  function localToday() { // giờ máy người dùng, không dùng UTC (VN lệch 7 tiếng)
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }
  function cmpVer(a, b) {
    const pa = String(a).split(".").map((n) => parseInt(n, 10) || 0);
    const pb = String(b).split(".").map((n) => parseInt(n, 10) || 0);
    for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
      if ((pa[i] || 0) !== (pb[i] || 0)) return (pa[i] || 0) > (pb[i] || 0) ? 1 : -1;
    }
    return 0;
  }
  const isAd = (a) => a.placement === "side" || a.placement === "sidebar" || a.tone === "promo";
  const dismissed = () => store.get("dismissed", []);
  function dismiss(id) { store.set("dismissed", dismissed().filter((x) => x !== id).concat(id).slice(-50)); }

  function active(a, version) {
    const today = localToday();
    if (isAd(a) && !a.end) return false;
    // Một feed dùng chung nhiều app: mục có "apps" chỉ hiện ở app có appId nằm trong danh sách.
    const appId = CFG.appId || CFG.utm?.source;
    if (Array.isArray(a.apps) && a.apps.length && !a.apps.includes(appId)) return false;
    if (a.start && today < a.start) return false;
    if (a.end && today > a.end) return false;
    if (a.min_version && version && cmpVer(version, a.min_version) < 0) return false;
    if (a.max_version && version && cmpVer(version, a.max_version) > 0) return false;
    return !(a.dismissible !== false && dismissed().includes(a.id));
  }

  // Gắn UTM để đơn vị quảng cáo biết lượt bấm đến từ app nào, vị trí nào, bản nào.
  function withUtm(link, a, version) {
    const url = https(link);
    if (!url) return "";
    try {
      const u = new URL(url);
      if (a.utm === false || [...u.searchParams.keys()].some((k) => k.startsWith("utm_"))) return u.toString();
      const slot = a.placement === "top" ? "top-banner" : a.id && a.id.startsWith("update-") ? "update-banner" : "sidebar-card";
      u.searchParams.set("utm_source", CFG.utm?.source || "free_app");
      u.searchParams.set("utm_medium", CFG.utm?.medium || "app");
      u.searchParams.set("utm_campaign", a.campaign || a.id || "sponsor");
      u.searchParams.set("utm_content", `${slot}${version ? "_v" + version : ""}`);
      return u.toString();
    } catch { return url; }
  }

  function link(href, cls, text) {
    const a = el("a", cls, text);
    a.href = href; a.target = "_blank"; a.rel = "noopener sponsored";
    return a;
  }
  function closeBtn(id, node) {
    const b = el("button", "sk-close", "✕");
    b.type = "button";
    b.setAttribute("aria-label", "Đóng");
    b.addEventListener("click", () => { dismiss(id); node.remove(); });
    return b;
  }
  function adTag(a) {
    const wrap = el("span", "sk-adtag");
    wrap.append(el("span", "sk-adlabel", a.label || "Ad · Sponsor"));
    const info = el("button", "sk-info", "i");
    info.type = "button";
    info.title = "Vì sao bạn thấy quảng cáo này?";
    info.setAttribute("aria-label", "Vì sao bạn thấy quảng cáo này?");
    info.addEventListener("click", (e) => { e.preventDefault(); openLetter(); });
    wrap.append(info);
    return wrap;
  }

  // ── thư ngỏ (envelope) ───────────────────────────────
  let letterEl = null, lastFocus = null;
  function buildLetter() {
    const dev = CFG.developer || {};
    const app = CFG.appName || "Phần mềm này";
    const sponsor = CFG.sponsorName || "nhà tài trợ";
    const L = CFG.letter || {};
    const back = el("div", "sk-letter-backdrop");
    back.hidden = true;
    const env = el("div", "sk-envelope");
    env.setAttribute("role", "dialog");
    env.setAttribute("aria-modal", "true");
    env.setAttribute("aria-labelledby", "sk-letter-title");
    env.append(el("div", "sk-flap"), el("div", "sk-seal", "♥"));
    const paper = el("div", "sk-paper");
    const stamp = el("div", "sk-stamp");
    stamp.append(el("span", "", "FREE"), el("small", "", "miễn phí"));
    paper.append(stamp);
    const h = el("h2", "sk-letter-title", L.title || `Gửi bạn — người đang dùng ${app} 💌`);
    h.id = "sk-letter-title";
    paper.append(h);
    const paras = L.paragraphs || [
      [["", `${app} và trang web đi kèm `], ["b", "hoàn toàn miễn phí"], ["", " — không giới hạn số lần dùng, không cần tài khoản, không thu phí ẩn."]],
      [["", "Để có thêm kinh phí phát triển những phiên bản tốt hơn, mình dành "], ["b", "một góc nhỏ"], ["", " trong app để giới thiệu chương trình của "], ["b", sponsor], ["", " — đơn vị đồng hành cùng dự án."]],
      [["", "Quảng cáo được chọn chung cho mọi người, "], ["b", "không dựa trên dữ liệu của bạn"], ["", ". App không theo dõi bạn, không gửi nội dung hay tệp của bạn đi đâu. Không muốn thấy thì bấm ✕ để đóng bất cứ lúc nào."]],
      [["", "Cảm ơn bạn đã sử dụng và ủng hộ. Chúc bạn làm việc thật vui!"]],
    ];
    paras.forEach((parts) => {
      const p = el("p", "sk-letter-p");
      (Array.isArray(parts) ? parts : [["", parts]]).forEach(([tag, text]) => p.append(tag ? el(tag, "", text) : document.createTextNode(text)));
      paper.append(p);
    });
    const sign = el("div", "sk-sign");
    sign.append(el("span", "sk-sign-hi", "Thân mến,"));
    if (dev.url && https(dev.url)) sign.append(link(dev.url, "sk-sign-name", dev.name || ""));
    else sign.append(el("span", "sk-sign-name", dev.name || ""));
    if (dev.title) sign.append(el("span", "sk-sign-title", dev.title));
    paper.append(sign);
    const ok = el("button", "sk-letter-ok", L.button || "Đã hiểu, cảm ơn bạn ♥");
    ok.type = "button";
    ok.addEventListener("click", closeLetter);
    paper.append(ok);
    env.append(paper);
    back.append(env);
    back.addEventListener("click", (e) => { if (e.target === back) closeLetter(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !back.hidden) closeLetter(); });
    document.body.append(back);
    return back;
  }
  function openLetter() {
    letterEl = letterEl || buildLetter();
    lastFocus = document.activeElement;
    letterEl.hidden = false;
    requestAnimationFrame(() => letterEl.classList.add("sk-open"));
    letterEl.querySelector(".sk-letter-ok").focus();
  }
  function closeLetter() {
    if (!letterEl) return;
    letterEl.classList.remove("sk-open");
    setTimeout(() => { letterEl.hidden = true; lastFocus && lastFocus.focus && lastFocus.focus(); }, 220);
  }

  // ── hai vị trí hiển thị ─────────────────────────────
  function topBanner(a, version) {
    const box = el("div", "sk-banner sk-tone-" + (a.tone || "info"));
    box.setAttribute("role", "status");
    box.append(el("span", "sk-ico", ICON[a.tone] || ICON.info));
    const body = el("div", "sk-body");
    if (isAd(a)) body.append(adTag(a));
    if (a.title) body.append(el("p", "sk-title", a.title));
    if (a.text) body.append(el("p", "sk-text", a.text));
    box.append(body);
    const act = el("div", "sk-actions");
    const href = withUtm(a.link, a, version);
    if (href) act.append(link(href, "sk-btn", a.cta || "Xem chi tiết"));
    if (a.dismissible !== false) act.append(closeBtn(a.id, box));
    box.append(act);
    return box;
  }
  function sideCard(a, version) {
    const card = el("div", "sk-card");
    card.setAttribute("aria-label", "Quảng cáo");
    card.append(adTag(a));
    if (a.dismissible !== false) card.append(closeBtn(a.id, card));
    const href = withUtm(a.link, a, version);
    const img = https(a.image);
    if (img) {
      const i = el("img", "sk-img");
      i.src = img; i.alt = a.title || ""; i.loading = "lazy";
      i.addEventListener("error", () => i.remove());
      if (href) {
        const wrap = link(href, "sk-img-link", "");
        wrap.append(i);
        card.append(wrap);
      } else {
        card.append(i);
      }
    }
    if (a.title) card.append(el("p", "sk-title", a.title));
    if (a.text) card.append(el("p", "sk-text", a.text));
    if (href) card.append(link(href, "sk-cta", (a.cta || "Xem ngay") + " →"));
    return card;
  }

  async function load() {
    let d;
    try {
      const r = await fetch(CFG.feedUrl, { cache: "no-store" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      d = await r.json();
      store.set("feed", d);              // lưu bản mới nhất — lần sau mất mạng vẫn hiện
    } catch {
      d = store.get("feed", null);       // offline: dùng bản đã lưu (ngày hết hạn vẫn được kiểm)
      if (!d) return;
    }
    if (!d || d.enabled === false) return;
    const version = CFG.appVersion || d.version || "";
    const items = (d.announcements || []).filter((a) => a && a.id && active(a, version));
    if (d.latest_version && version && cmpVer(d.latest_version, version) > 0) {
      const upd = {
        id: "update-" + d.latest_version, tone: "update", placement: "top",
        title: `Đã có ${CFG.appName || "phiên bản mới"} ${d.latest_version} (bạn đang dùng ${version})`,
        text: d.update_note || "", link: d.release_url, cta: "Xem bản mới", utm: false,
      };
      if (!dismissed().includes(upd.id)) items.unshift(upd);
    }
    const top = CFG.slots?.top && document.querySelector(CFG.slots.top);
    const side = CFG.slots?.side && document.querySelector(CFG.slots.side);
    if (top) items.filter((a) => a.placement === "top").slice(0, 2).forEach((a) => top.append(topBanner(a, version)));
    const s = items.find((a) => a.placement === "side" || a.placement === "sidebar");
    if (side && s) side.append(sideCard(s, version));
  }

  // ── Khung "Phát triển bởi" (tĩnh, không cần mạng) ──
  function renderCredit(target) {
    const host = typeof target === "string" ? document.querySelector(target) : target;
    const dev = CFG.developer || {};
    if (!host || !dev.name) return;
    const box = https(dev.url) ? link(dev.url, "sk-credit", "") : el("div", "sk-credit");
    box.append(el("span", "sk-credit-by", CFG.creditLabel || "Phát triển bởi"));
    box.append(el("span", "sk-credit-name", dev.name + (https(dev.url) ? " ↗" : "")));
    if (dev.title) box.append(el("span", "sk-credit-title", dev.title));
    if (CFG.basedOn) box.append(el("span", "sk-credit-base", CFG.basedOn));
    host.replaceChildren(box);
  }

  global.SponsorKit = {
    init(cfg) {
      CFG = cfg || {};
      if (CFG.slots?.credit) renderCredit(CFG.slots.credit);
      if (CFG.feedUrl) load();
      return this;
    },
    renderCredit: (t) => { if (CFG) renderCredit(t); },
    openLetter: () => { if (CFG) openLetter(); },
    _test: { withUtm: (l, a, v) => withUtm(l, a, v), active: (a, v) => active(a, v), localToday },
  };
})(window);
