"""Sinh docs/index.html (GitHub Pages): video YouTube nhúng + nghe thử 25 giọng + cài đặt.

Chạy lại khi đổi giọng nghe thử:  python3 scripts/build_pages.py
"""
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "sonlovinbot/vieneu-audio-studio"
RAW = f"https://raw.githubusercontent.com/{REPO}/main"
YT = "rsjhXh7OSHg"
data = json.loads((ROOT / "webapp/static/previews/voices.json").read_text("utf-8"))
sample = data["text"].replace("{name}", "…")

cards = []
for vid, v in data["voices"].items():
    region = v["region"]
    cards.append(f'''      <article class="voice" data-g="{html.escape(v["gender"])}" data-r="{html.escape(region)}"{' data-star="1"' if v["featured"] else ""}>
        <div class="voice-head"><h3>{html.escape(vid)}{' <span title="Nổi bật">⭐</span>' if v["featured"] else ""}</h3>
          <span class="meta">{html.escape(v["gender"])} · Miền {html.escape(region)} · {html.escape(v["style"])}</span></div>
        <audio controls preload="none" src="{RAW}/webapp/static/previews/{v["file"]}"></audio>
      </article>''')

page = f'''<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Audio Studio — Giọng nói AI tiếng Việt chạy trên máy tính</title>
<meta name="description" content="Biến văn bản tiếng Việt thành giọng nói tự nhiên, clone giọng từ 3–5 giây, hội thoại nhiều nhân vật, xuất API. Chạy 100% trên máy. Phát triển bởi Đặng Hữu Sơn, dựa trên model VieNeu-TTS.">
<meta property="og:title" content="AI Audio Studio — Giọng nói AI tiếng Việt">
<meta property="og:description" content="Nghe thử 25 giọng, xem video giới thiệu và cài bằng 1 lệnh.">
<meta property="og:image" content="{RAW}/assets/readme/banner.png">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;700&family=VT323&display=swap" rel="stylesheet">
<style>
:root {{
  --bg: #F7F7F8; --surface: #FFFFFF; --border: #E6E7EA; --text: #1F2937; --muted: #5B6472;
  --brand: #F67D1C; --brand-ink: #C2410C; --brand-soft: #FFF3E8; --code: #111318;
}}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg: #0F1115; --surface: #171A20; --border: #2A2F38; --text: #E8EAED; --muted: #A3AAB5;
           --brand-ink: #FB923C; --brand-soft: #2A2017; --code: #0A0C0F; }}
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font: 16px/1.6 "Be Vietnam Pro", system-ui, sans-serif; color: var(--text); background: var(--bg); }}
a {{ color: var(--brand-ink); font-weight: 700; }}
.wrap {{ max-width: 1080px; margin: 0 auto; padding: 0 16px; }}
header {{ padding: 32px 0 8px; display: flex; align-items: center; gap: 12px; }}
.logo {{ width: 44px; height: 44px; border-radius: 12px; background: var(--brand); display: grid; place-items: center; font-size: 22px; }}
.brand {{ font: 34px/1 "VT323", monospace; }}
h1 {{ font-size: clamp(28px, 5vw, 44px); line-height: 1.15; margin: 24px 0 12px; }}
h1 em {{ font-style: normal; color: var(--brand-ink); }}
h2 {{ font-size: 24px; margin: 48px 0 8px; }}
.lead {{ color: var(--muted); max-width: 720px; margin: 0 0 20px; }}
.cta {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }}
.btn {{ display: inline-flex; align-items: center; gap: 8px; padding: 12px 20px; border-radius: 10px; text-decoration: none;
        font-weight: 700; border: 1px solid var(--border); color: var(--text); background: var(--surface); }}
.btn.primary {{ background: var(--brand-ink); border-color: var(--brand-ink); color: #fff; }}
.video {{ position: relative; aspect-ratio: 16 / 9; border-radius: 16px; overflow: hidden; border: 1px solid var(--border); background: #000; margin-top: 24px; }}
.video iframe {{ position: absolute; inset: 0; width: 100%; height: 100%; border: 0; }}
.sample {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 12px 16px; color: var(--muted); font-style: italic; }}
.filters {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 16px 0; }}
.chip {{ font: 700 14px "Be Vietnam Pro", sans-serif; padding: 6px 14px; border-radius: 999px; cursor: pointer;
         border: 1px solid var(--border); background: var(--surface); color: var(--text); }}
.chip[aria-pressed="true"] {{ background: var(--text); color: var(--bg); border-color: var(--text); }}
.grid {{ display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); }}
.voice {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; }}
.voice[hidden] {{ display: none; }}
.voice h3 {{ margin: 0; font-size: 17px; }}
.meta {{ font-size: 13px; color: var(--muted); }}
.voice audio {{ width: 100%; margin-top: 10px; height: 40px; }}
.steps {{ display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }}
.step {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }}
.step h3 {{ margin: 0 0 6px; font-size: 17px; }}
.cmd {{ display: flex; gap: 8px; margin-top: 8px; }}
.cmd code {{ flex: 1; min-width: 0; overflow-x: auto; white-space: nowrap; background: var(--code); color: #F3F4F6;
             font: 13px/1.5 ui-monospace, Menlo, monospace; padding: 10px 12px; border-radius: 8px; }}
.cmd button {{ flex: none; font: 700 13px "Be Vietnam Pro", sans-serif; border-radius: 8px; border: 1px solid var(--border);
               background: var(--surface); color: var(--text); padding: 0 12px; cursor: pointer; }}
.note {{ background: var(--brand-soft); border-radius: 12px; padding: 14px 16px; margin-top: 16px; }}
footer {{ margin: 64px 0 32px; padding-top: 24px; border-top: 1px solid var(--border); color: var(--muted); font-size: 14px; }}
</style>
</head>
<body>
<div class="wrap">
  <header><div class="logo" aria-hidden="true">⚡</div><span class="brand">AI Audio Studio</span></header>

  <h1>Giọng nói AI tiếng Việt,<br><em>chạy ngay trên máy tính của bạn</em></h1>
  <p class="lead">Biến văn bản thành giọng đọc tự nhiên, clone giọng từ 3–5 giây audio, tạo hội thoại nhiều nhân vật và xuất API cho phần mềm khác. Không cần card đồ họa, chạy offline sau lần cài đầu.</p>
  <div class="cta">
    <a class="btn primary" href="#cai-dat">⬇ Cài đặt miễn phí</a>
    <a class="btn" href="#nghe-thu">🎧 Nghe thử 25 giọng</a>
    <a class="btn" href="https://github.com/{REPO}">GitHub</a>
  </div>

  <div class="video">
    <iframe src="https://www.youtube.com/embed/{YT}?rel=0" title="Giới thiệu AI Audio Studio" loading="lazy"
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
      referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>
  </div>

  <h2 id="nghe-thu">🎧 Nghe thử 25 giọng có sẵn</h2>
  <p class="sample">“{html.escape(sample)}”</p>
  <div class="filters" role="group" aria-label="Lọc giọng">
    <button class="chip" data-f="" aria-pressed="true">Tất cả</button>
    <button class="chip" data-f="g:Nữ" aria-pressed="false">Nữ</button>
    <button class="chip" data-f="g:Nam" aria-pressed="false">Nam</button>
    <button class="chip" data-f="r:Bắc" aria-pressed="false">Miền Bắc</button>
    <button class="chip" data-f="r:Trung" aria-pressed="false">Miền Trung</button>
    <button class="chip" data-f="r:Nam" aria-pressed="false">Miền Nam</button>
    <button class="chip" data-f="star" aria-pressed="false">⭐ Nổi bật</button>
  </div>
  <div class="grid" id="voices">
{chr(10).join(cards)}
  </div>

  <h2 id="cai-dat">⬇ Cài đặt bằng 1 lệnh</h2>
  <p class="lead">Tải bằng lệnh nên không bị macOS hay Windows chặn. Chạy lại đúng lệnh = cập nhật bản mới nhất.</p>
  <div class="steps">
    <div class="step"><h3>🍎 macOS · 🐧 Linux</h3><span class="meta">Mở Terminal (⌘ + Space, gõ Terminal), dán lệnh rồi Enter</span>
      <div class="cmd"><code>/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/{REPO}/main/install-online.sh)"</code><button type="button">Sao chép</button></div></div>
    <div class="step"><h3>🪟 Windows 10/11</h3><span class="meta">Mở PowerShell từ menu Start, dán lệnh rồi Enter</span>
      <div class="cmd"><code>irm https://raw.githubusercontent.com/{REPO}/main/install-online.ps1 | iex</code><button type="button">Sao chép</button></div></div>
  </div>
  <p class="note"><b>💻 Phần mềm chạy trên máy tính của bạn.</b> Máy bật và app đang chạy thì dùng được giao diện và API tại <code style="background:none;color:inherit">http://127.0.0.1:8001</code>; tắt máy hoặc máy ngủ thì không dùng được. Yêu cầu: RAM 8 GB, ổ trống ~5 GB, Internet ở lần cài đầu. Hoặc <a href="https://github.com/{REPO}/releases/latest">tải file .zip thủ công</a>.</p>

  <footer>
    Phát triển bởi <a href="https://www.facebook.com/danghuuson.182/">Đặng Hữu Sơn</a> — CEO &amp; Co-Founder LovinBot AI ·
    Dựa trên model AI <a href="https://github.com/pnnbao97/VieNeu-TTS">VieNeu-TTS</a> của Phạm Nguyễn Ngọc Bảo (Apache 2.0)
  </footer>
</div>
<script>
// Lọc giọng
document.querySelector(".filters").addEventListener("click", (e) => {{
  const c = e.target.closest(".chip"); if (!c) return;
  document.querySelectorAll(".chip").forEach((x) => x.setAttribute("aria-pressed", x === c));
  const f = c.dataset.f;
  document.querySelectorAll(".voice").forEach((v) => {{
    v.hidden = !(!f || (f === "star" ? v.dataset.star : f.startsWith("g:") ? v.dataset.g === f.slice(2) : v.dataset.r === f.slice(2)));
  }});
}});
// Chỉ phát một giọng một lúc
document.addEventListener("play", (e) => {{
  document.querySelectorAll("audio").forEach((a) => {{ if (a !== e.target) a.pause(); }});
}}, true);
// Sao chép lệnh
document.querySelectorAll(".cmd button").forEach((b) => b.addEventListener("click", async () => {{
  try {{ await navigator.clipboard.writeText(b.previousElementSibling.textContent); b.textContent = "Đã chép ✓"; }}
  catch {{ b.textContent = "Bôi đen để chép"; }}
  setTimeout(() => (b.textContent = "Sao chép"), 2000);
}}));
</script>
</body>
</html>
'''
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs/index.html").write_text(page, "utf-8")
print("docs/index.html", len(page) // 1024, "KB,", len(cards), "giọng")
