/* AI Audio Studio — tin tức từ xa (docs/news.json trên GitHub Pages, qua /api/news).
   Hai vị trí: thanh thông báo trên đầu trang (#news-top) và thẻ quảng cáo ở sidebar
   (#news-side). Tự thêm thanh "Đã có bản mới" khi latest_version > bản đang chạy.
   Mọi nội dung gắn bằng textContent / thuộc tính — không chèn HTML từ xa. */
(function () {
  const DISMISS_KEY = "vieneu_news_dismissed";
  const ICON = { info: "ℹ️", warning: "⚠️", promo: "🎉", update: "🚀" };

  function dismissed() {
    try { return JSON.parse(localStorage.getItem(DISMISS_KEY) || "[]"); } catch { return []; }
  }
  function dismiss(id) {
    const list = dismissed().filter((x) => x !== id).concat(id).slice(-50);
    try { localStorage.setItem(DISMISS_KEY, JSON.stringify(list)); } catch {}
  }
  // "1.10.0" > "1.9.2"
  function cmpVer(a, b) {
    const pa = String(a).split(".").map((n) => parseInt(n, 10) || 0);
    const pb = String(b).split(".").map((n) => parseInt(n, 10) || 0);
    for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
      if ((pa[i] || 0) !== (pb[i] || 0)) return (pa[i] || 0) > (pb[i] || 0) ? 1 : -1;
    }
    return 0;
  }
  // Ngày theo giờ máy người dùng (không dùng UTC: ở VN lệch 7 tiếng, QC hết hạn vẫn hiện tới 7h sáng).
  function localToday() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }
  // Quảng cáo (thẻ sidebar, tông promo) bắt buộc có ngày kết thúc — thiếu thì không hiện.
  function isAd(a) { return a.placement === "sidebar" || a.tone === "promo"; }
  function active(a, version) {
    const today = localToday();
    if (isAd(a) && !a.end) return false;
    if (a.start && today < a.start) return false;
    if (a.end && today > a.end) return false;
    if (a.min_version && cmpVer(version, a.min_version) < 0) return false;
    if (a.max_version && cmpVer(version, a.max_version) > 0) return false;
    return !(a.dismissible && dismissed().includes(a.id));
  }
  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    return e;
  }
  function link(href, cls, text) {
    const a = el("a", cls, text);
    a.href = href; a.target = "_blank"; a.rel = "noopener";
    return a;
  }
  function closeBtn(id, node) {
    const b = el("button", "news-close", "✕");
    b.type = "button";
    b.setAttribute("aria-label", "Đóng thông báo");
    b.addEventListener("click", () => { dismiss(id); node.remove(); });
    return b;
  }

  function topBanner(a) {
    const box = el("div", "news-banner tone-" + a.tone);
    box.setAttribute("role", "status");
    box.append(el("span", "news-ico", ICON[a.tone] || ICON.info));
    const body = el("div", "news-body");
    if (a.tone === "promo") body.append(el("span", "news-ad-label", a.label || "Ad · Sponsor"));
    if (a.title) body.append(el("p", "news-title", a.title));
    if (a.text) body.append(el("p", "news-text", a.text));
    box.append(body);
    const act = el("div", "news-actions");
    if (a.link) act.append(link(a.link, "btn btn-ghost btn-sm", a.cta || "Xem chi tiết"));
    if (a.dismissible) act.append(closeBtn(a.id, box));
    box.append(act);
    return box;
  }

  function sideCard(a) {
    const card = el("div", "news-side-card");
    card.setAttribute("aria-label", "Quảng cáo");
    card.append(el("span", "news-ad-label", a.label || "Ad · Sponsor"));
    if (a.dismissible) card.append(closeBtn(a.id, card));
    if (a.image) {
      const img = el("img", "news-img");
      img.src = a.image; img.alt = a.title || ""; img.loading = "lazy";
      img.addEventListener("error", () => img.remove());
      card.append(img);
    }
    if (a.title) card.append(el("p", "news-title", a.title));
    if (a.text) card.append(el("p", "news-text", a.text));
    if (a.link) card.append(link(a.link, "news-cta", (a.cta || "Xem ngay") + " →"));
    return card;
  }

  async function load() {
    let d;
    try { d = await (await fetch("/api/news")).json(); } catch { return; }
    if (!d || !d.enabled) return;
    const items = (d.announcements || []).filter((a) => active(a, d.version));
    if (d.latest_version && cmpVer(d.latest_version, d.version) > 0) {
      const upd = {
        id: "update-" + d.latest_version, tone: "update", placement: "top", dismissible: true,
        title: `Đã có AI Audio Studio ${d.latest_version} (bạn đang dùng ${d.version})`,
        text: d.update_note || "Chạy lại lệnh cài 1 dòng để cập nhật — giữ nguyên giọng đã lưu và lịch sử.",
        link: d.release_url, cta: "Xem bản mới",
      };
      if (!dismissed().includes(upd.id)) items.unshift(upd);
    }
    const top = document.getElementById("news-top");
    const side = document.getElementById("news-side");
    items.filter((a) => a.placement === "top").slice(0, 2).forEach((a) => top && top.append(topBanner(a)));
    const s = items.find((a) => a.placement === "sidebar");
    if (s && side) side.append(sideCard(s));
  }
  load();
})();
