"""Sinh docs/index.html (GitHub Pages): video nhúng, tải trực tiếp, tính năng + ảnh,
nghe thử 25 giọng, có gì mới, xử lý sự cố.

Chạy lại sau mỗi lần phát hành (lấy dung lượng bộ cài mới nhất từ GitHub):
    python3 scripts/build_pages.py
"""
import html
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "sonlovinbot/vieneu-audio-studio"
GH = f"https://github.com/{REPO}"
RAW = f"https://raw.githubusercontent.com/{REPO}/main"
DL = f"{GH}/releases/latest/download"
YT = "rsjhXh7OSHg"
FB = "https://www.facebook.com/danghuuson.182/"
esc = html.escape

voices = json.loads((ROOT / "webapp/static/previews/voices.json").read_text("utf-8"))
sample = (voices.get("display_text") or voices["text"]).replace("{name}", "…")
changelog = json.loads((ROOT / "webapp/config/changelog.json").read_text("utf-8"))["entries"]
version = json.loads((ROOT / "webapp/config/branding.json").read_text("utf-8"))["app"]["version"]

# Dung lượng bộ cài từ bản phát hành mới nhất (không có mạng thì bỏ qua).
sizes, tag = {}, f"v{version}"
try:
    with urllib.request.urlopen(f"https://api.github.com/repos/{REPO}/releases/latest", timeout=10) as r:
        rel = json.load(r)
    tag = rel.get("tag_name", tag)
    sizes = {a["name"]: a["size"] for a in rel.get("assets", [])}
except Exception as e:  # noqa: BLE001
    print("Không lấy được thông tin release:", e)


def mb(name):
    return f"{sizes[name] / 1024 / 1024:.1f} MB" if name in sizes else ""


INSTALL_SH = f"/bin/bash -c \"$(curl -fsSL {RAW}/install-online.sh)\""
INSTALL_PS = f"irm {RAW}/install-online.ps1 | iex"

downloads = [
    ("🍎", "macOS", "macOS 12+ · chip Apple M hoặc Intel", "AI-Audio-Studio-macOS.zip",
     "Giải nén → nhấp đúp <code>install.command</code>. macOS sẽ chặn lần đầu — xem <a href=\"#su-co\">cách mở</a>, hoặc dùng lệnh 1 dòng để không bị chặn."),
    ("🪟", "Windows", "Windows 10 / 11 · 64-bit", "AI-Audio-Studio-Windows.zip",
     "Chuột phải → <b>Extract All</b> → nhấp đúp <code>install.bat</code>. SmartScreen hiện thì bấm <b>More info → Run anyway</b>."),
    ("🐧", "Linux", "64-bit · Ubuntu, Debian, Fedora…", "AI-Audio-Studio-Linux.zip",
     "Giải nén → mở Terminal trong thư mục → <code>bash install.sh</code>."),
]
dl_cards = "\n".join(f'''      <div class="dl">
        <div class="dl-head"><span class="dl-ico">{ico}</span><div><h3>{name}</h3><span class="meta">{esc(req)}</span></div></div>
        <a class="btn primary dl-btn" href="{DL}/{file}" download>⬇ Tải {name} <span class="dl-size">{tag}{" · " + mb(file) if mb(file) else ""}</span></a>
        <p class="meta">{how}</p>
      </div>''' for ico, name, req, file, how in downloads)

features = [
    ("🔊", "Sinh giọng", "25 giọng có sẵn, chèn cảm xúc [cười] [thở dài] [hắng giọng], tối đa 5.000 ký tự/lần."),
    ("🎙️", "Clone giọng", "Nhân bản giọng từ 3–5 giây audio, lưu lại kèm nhãn cảm xúc để dùng lại."),
    ("💬", "Hội thoại", "Nhiều nhân vật, mỗi lượt một giọng — làm podcast, kịch bản, bài giảng."),
    ("🔌", "API cho phần mềm khác", "Gọi từ n8n, Make, script, OBS… có sẵn ví dụ curl, JavaScript, Python và prompt cho AI agent."),
    ("💻", "Chạy trên máy bạn", "Không cần card đồ họa, không gửi dữ liệu lên mạng, chạy offline sau lần cài đầu."),
    ("🚀", "Dễ bắt đầu", "Hướng dẫn lần đầu: kiểm tra cấu hình máy, tải model, thử tạo giọng — vài cú nhấp."),
]
feature_html = "\n".join(f'      <div class="feat"><span class="feat-ico">{i}</span><h3>{t}</h3><p>{d}</p></div>' for i, t, d in features)

shots = [
    ("screenshot-sinh-giong.png", "Sinh giọng — nhập văn bản, chọn giọng, chèn cảm xúc; cột phải là kết quả và lượt gần đây"),
    ("screenshot-kho-giong.png", "Kho giọng — nghe thử và so sánh 25 giọng, lọc theo giới tính và vùng miền"),
    ("screenshot-onboarding.png", "Hướng dẫn lần đầu — tự kiểm tra cấu hình máy trước khi dùng"),
    ("screenshot-api.png", "API — ví dụ sẵn để cắm vào phần mềm khác"),
]
shot_html = "\n".join(f'''      <figure><a href="{RAW}/assets/readme/{f}" target="_blank" rel="noopener"><img src="{RAW}/assets/readme/{f}" alt="{esc(c)}" loading="lazy"></a>
        <figcaption>{esc(c)}</figcaption></figure>''' for f, c in shots)

cards = []
for vid, v in voices["voices"].items():
    cards.append(f'''      <article class="voice" data-g="{esc(v["gender"])}" data-r="{esc(v["region"])}"{' data-star="1"' if v["featured"] else ""}>
        <div><h3>{esc(vid)}{' <span title="Nổi bật">⭐</span>' if v["featured"] else ""}</h3>
          <span class="meta">{esc(v["gender"])} · Miền {esc(v["region"])} · {esc(v["style"])}</span></div>
        <audio controls preload="none" src="{RAW}/webapp/static/previews/{v["file"]}"></audio>
      </article>''')

news_html = "\n".join(f'''      <div class="news-item"><div class="news-head"><span class="ver">v{esc(e["version"])}</span><span class="meta">{esc(e["date"])}</span></div>
        <h3>{esc(e["title"])}</h3><ul>{"".join(f"<li>{esc(c)}</li>" for c in e["changes"][:4])}</ul></div>''' for e in changelog[:3])

trouble = [
    ("🍎 macOS báo “install.command” Not Opened / Apple could not verify…",
     f"""<p>Không phải virus — phần mềm chưa mua chứng chỉ ký số của Apple nên macOS chặn file tải bằng trình duyệt.</p>
     <ol><li><b>Cách dễ nhất:</b> dùng <a href="#cai-dat">lệnh cài 1 dòng</a> — tải qua Terminal nên không bị chặn.</li>
     <li><b>macOS 15 (Sequoia) trở lên:</b> bấm <b>Done</b> → 🍎 <b>System Settings → Privacy &amp; Security</b> → kéo xuống mục Security → bấm <b>Open Anyway</b> → nhập mật khẩu → nhấp đúp <code>install.command</code> lần nữa.</li>
     <li><b>macOS 14 trở về trước:</b> chuột phải <code>install.command</code> → <b>Open</b> → <b>Open</b>.</li>
     <li><b>Bằng Terminal:</b> gõ <code>xattr -cr </code> (có dấu cách), kéo thả thư mục vừa giải nén vào, Enter, rồi nhấp đúp lại.</li></ol>"""),
    ("🪟 Windows hiện “Windows protected your PC” (SmartScreen)",
     "<p>Bấm <b>More info</b> → <b>Run anyway</b>. Hoặc dùng lệnh PowerShell 1 dòng để không hiện cảnh báo. Nếu phần mềm diệt virus chặn <code>install.bat</code>, cho phép thư mục cài rồi chạy lại.</p>"),
    ("⏳ Cài rất lâu hoặc báo lỗi “uv sync that bai” / lỗi tải thư viện",
     """<p>Lần đầu cần tải khoảng vài trăm MB thư viện. Kiểm tra Internet (mạng công ty có thể chặn), rồi <b>chạy lại đúng lệnh cài</b> — các phần đã tải sẽ không tải lại.</p>
     <p>Vẫn lỗi ở bước cài <code>uv</code>: cài tay rồi chạy lại bộ cài —<br>macOS/Linux: <code>curl -LsSf https://astral.sh/uv/install.sh | sh</code><br>Windows (PowerShell): <code>irm https://astral.sh/uv/install.ps1 | iex</code></p>"""),
    ("🌐 Cài xong nhưng trình duyệt không mở / trang không vào được",
     """<p>Mở icon <b>AI Audio Studio</b> trên Desktop, đợi cửa sổ Terminal/đen chạy xong rồi vào <b>http://127.0.0.1:8001</b>. Đóng cửa sổ đó là app tắt.</p>
     <p>Báo cổng 8001 đang bận (có phần mềm khác dùng): tắt phần mềm đó, hoặc chạy với cổng khác — macOS/Linux: <code>VIENEU_PORT=8002 uv run vieneu-studio</code>; Windows: <code>set VIENEU_PORT=8002</code> rồi <code>uv run vieneu-studio</code> trong thư mục cài.</p>"""),
    ("🐢 Bấm “Sinh audio” lần đầu chờ lâu / báo đang tải model",
     "<p>Lần đầu app tải model giọng nói từ Hugging Face (vài phút, tùy mạng). Các lần sau dùng offline. Nếu Hugging Face bị chặn ở mạng của bạn, thử mạng khác rồi bấm lại. Chi tiết lỗi xem ở mục <b>Phiên bản &amp; Logs</b> trong app.</p>"),
    ("💻 Máy chậm, giật khi sinh văn bản dài",
     "<p>Cần RAM 8 GB (tối thiểu 4 GB). Chia văn bản thành đoạn ≤ 1.500 ký tự, đóng bớt ứng dụng khác. Máy Mac chip Intel chạy được nhưng chậm hơn chip Apple M.</p>"),
    ("🗑️ Gỡ cài đặt",
     """<ul><li>Xóa thư mục cài (mặc định <code>AI-Audio-Studio</code> trong thư mục người dùng) và icon trên Desktop.</li>
     <li>Xóa giọng đã lưu và lịch sử: thư mục <code>.vieneu</code> trong thư mục người dùng.</li>
     <li>Tắt tự chạy — macOS: <code>launchctl unload ~/Library/LaunchAgents/com.vieneu.studio.plist</code> rồi xóa file đó; Windows: xóa “AI Audio Studio (autostart).bat” trong thư mục Startup (gõ <code>shell:startup</code> vào ô Run).</li></ul>"""),
]
trouble_html = "\n".join(f'      <details><summary>{t}</summary><div class="ans">{body}</div></details>' for t, body in trouble)

page = f'''<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Audio Studio — Giọng nói AI tiếng Việt chạy trên máy tính</title>
<meta name="description" content="Biến văn bản tiếng Việt thành giọng nói tự nhiên, clone giọng từ 3–5 giây, hội thoại nhiều nhân vật, xuất API. Chạy 100% trên máy. Phát triển bởi Đặng Hữu Sơn, dựa trên model VieNeu-TTS.">
<meta property="og:title" content="AI Audio Studio — Giọng nói AI tiếng Việt">
<meta property="og:description" content="Xem video, nghe thử 25 giọng và tải miễn phí cho macOS, Windows, Linux.">
<meta property="og:image" content="{RAW}/assets/readme/banner.png">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root {{
  --bg: #F7F7F8; --surface: #FFFFFF; --border: #E6E7EA; --text: #1F2937; --muted: #5B6472;
  --brand: #F67D1C; --brand-ink: #C2410C; --brand-soft: #FFF3E8; --code: #111318; --code-inline: #EEF0F3;
}}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg: #0F1115; --surface: #171A20; --border: #2A2F38; --text: #E8EAED; --muted: #A3AAB5;
           --brand-ink: #FB923C; --brand-soft: #2A2017; --code: #0A0C0F; --code-inline: #232831; }}
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font: 16px/1.6 "Be Vietnam Pro", system-ui, sans-serif; color: var(--text); background: var(--bg); }}
a {{ color: var(--brand-ink); font-weight: 700; }}
code {{ font: 13px/1.5 ui-monospace, Menlo, monospace; background: var(--code-inline); padding: 1px 6px; border-radius: 6px; word-break: break-word; }}
.wrap {{ max-width: 1080px; margin: 0 auto; padding: 0 16px; }}
nav.top {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 24px 0 0; flex-wrap: wrap; }}
.brandrow {{ display: flex; align-items: center; gap: 12px; text-decoration: none; color: var(--text); }}
.logo {{ width: 40px; height: 40px; border-radius: 10px; background: var(--brand); display: grid; place-items: center; font-size: 20px; }}
.brand {{ font: 700 22px/1.2 "Be Vietnam Pro", sans-serif; letter-spacing: -0.01em; }}
.navlinks {{ display: flex; gap: 16px; flex-wrap: wrap; font-size: 14px; }}
.navlinks a {{ color: var(--muted); font-weight: 500; text-decoration: none; }}
.navlinks a:hover {{ color: var(--brand-ink); }}
h1 {{ font-size: clamp(30px, 5.2vw, 48px); line-height: 1.12; margin: 32px 0 12px; }}
h1 em {{ font-style: normal; color: var(--brand-ink); }}
h2 {{ font-size: 26px; margin: 64px 0 6px; scroll-margin-top: 16px; }}
h3 {{ margin: 0; font-size: 17px; }}
.lead {{ color: var(--muted); max-width: 760px; margin: 0 0 20px; }}
.meta {{ font-size: 13px; color: var(--muted); }}
.cta {{ display: flex; gap: 12px; flex-wrap: wrap; }}
.btn {{ display: inline-flex; align-items: center; justify-content: center; gap: 8px; padding: 12px 20px; border-radius: 10px;
        text-decoration: none; font-weight: 700; border: 1px solid var(--border); color: var(--text); background: var(--surface); }}
.btn.primary {{ background: var(--brand-ink); border-color: var(--brand-ink); color: #fff; }}
.badges {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 16px; }}
.badge {{ font-size: 13px; padding: 4px 10px; border-radius: 999px; background: var(--surface); border: 1px solid var(--border); color: var(--muted); }}
.video {{ position: relative; aspect-ratio: 16 / 9; border-radius: 16px; overflow: hidden; border: 1px solid var(--border); background: #000; margin-top: 28px; }}
.video iframe {{ position: absolute; inset: 0; width: 100%; height: 100%; border: 0; }}
.cards3 {{ display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr)); }}
.dl, .feat, .step, .voice, .news-item {{ background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 16px; }}
.dl {{ display: flex; flex-direction: column; gap: 12px; }}
.dl-head {{ display: flex; gap: 12px; align-items: center; }}
.dl-ico {{ font-size: 28px; }}
.dl-btn {{ width: 100%; }}
.dl-size {{ font-weight: 500; opacity: .85; font-size: 13px; }}
.dl p {{ margin: 0; }}
.feat-ico {{ font-size: 24px; }}
.feat h3 {{ margin: 6px 0 4px; }}
.feat p {{ margin: 0; color: var(--muted); font-size: 15px; }}
.shots {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); margin-top: 16px; }}
@media (max-width: 480px) {{ .shots {{ grid-template-columns: 1fr; }} }}
figure {{ margin: 0; background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 8px; }}
figure img {{ display: block; width: 100%; height: auto; border-radius: 8px; }}
figcaption {{ padding: 8px 4px 2px; font-size: 14px; color: var(--muted); }}
.sample {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 12px 16px; color: var(--muted); font-style: italic; }}
.filters {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 16px 0; }}
.chip {{ font: 700 14px "Be Vietnam Pro", sans-serif; padding: 6px 14px; border-radius: 999px; cursor: pointer;
         border: 1px solid var(--border); background: var(--surface); color: var(--text); }}
.chip[aria-pressed="true"] {{ background: var(--text); color: var(--bg); border-color: var(--text); }}
.grid {{ display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); }}
.voice[hidden] {{ display: none; }}
.voice audio {{ width: 100%; margin-top: 10px; height: 40px; }}
.cmd {{ display: flex; gap: 8px; margin-top: 8px; }}
.cmd code {{ flex: 1; min-width: 0; overflow-x: auto; white-space: nowrap; background: var(--code); color: #F3F4F6; padding: 10px 12px; border-radius: 8px; word-break: normal; }}
.cmd button {{ flex: none; font: 700 13px "Be Vietnam Pro", sans-serif; border-radius: 8px; border: 1px solid var(--border);
               background: var(--surface); color: var(--text); padding: 0 12px; cursor: pointer; }}
.note {{ background: var(--brand-soft); border-radius: 14px; padding: 14px 16px; margin-top: 16px; }}
.news-head {{ display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }}
.ver {{ font-weight: 700; font-size: 13px; color: var(--brand-ink); background: var(--brand-soft); padding: 2px 8px; border-radius: 6px; }}
.news-item ul {{ margin: 8px 0 0; padding-left: 20px; color: var(--muted); font-size: 14px; }}
details {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 0 16px; margin-bottom: 8px; }}
details summary {{ cursor: pointer; padding: 14px 0; font-weight: 700; }}
details .ans {{ padding-bottom: 14px; color: var(--text); }}
details .ans p {{ margin: 0 0 8px; }}
details ol, details ul {{ margin: 0; padding-left: 20px; }}
details li {{ margin-bottom: 6px; }}
footer {{ margin: 72px 0 32px; padding-top: 24px; border-top: 1px solid var(--border); color: var(--muted); font-size: 14px; display: flex; flex-direction: column; gap: 6px; }}
</style>
</head>
<body>
<div class="wrap">
  <nav class="top">
    <a class="brandrow" href="#"><div class="logo" aria-hidden="true">⚡</div><span class="brand">AI Audio Studio</span></a>
    <div class="navlinks"><a href="#tai-ve">Tải về</a><a href="#nghe-thu">Nghe thử</a><a href="#tinh-nang">Tính năng</a><a href="#su-co">Sự cố khi cài</a><a href="{GH}">GitHub</a></div>
  </nav>

  <h1>Giọng nói AI tiếng Việt,<br><em>chạy ngay trên máy tính của bạn</em></h1>
  <p class="lead">Biến văn bản thành giọng đọc tự nhiên, clone giọng từ 3–5 giây audio, tạo hội thoại nhiều nhân vật và xuất API cho phần mềm khác. Miễn phí, không cần card đồ họa, chạy offline sau lần cài đầu.</p>
  <div class="cta">
    <a class="btn primary" href="#tai-ve">⬇ Tải miễn phí</a>
    <a class="btn" href="#nghe-thu">🎧 Nghe thử 25 giọng</a>
  </div>
  <div class="badges"><span class="badge">Phiên bản {esc(tag)}</span><span class="badge">macOS · Windows · Linux</span><span class="badge">25 giọng · 3 miền</span><span class="badge">Mã nguồn mở Apache 2.0</span></div>

  <div class="video">
    <iframe src="https://www.youtube.com/embed/{YT}?rel=0" title="Giới thiệu AI Audio Studio" loading="lazy"
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
      referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>
  </div>

  <h2 id="tai-ve">⬇ Tải về</h2>
  <p class="lead">Bấm là tải ngay bộ cài bản mới nhất. Yêu cầu: RAM 8 GB, ổ trống ~5 GB, Internet ở lần cài đầu.</p>
  <div class="cards3">
{dl_cards}
  </div>

  <h2 id="cai-dat">⚡ Hoặc cài bằng 1 lệnh (khuyên dùng)</h2>
  <p class="lead">Không phải tải hay giải nén, <b>không bị macOS / Windows chặn</b>. Chạy lại đúng lệnh = cập nhật bản mới nhất, giữ nguyên giọng đã lưu và lịch sử.</p>
  <div class="cards3">
    <div class="step"><h3>🍎 macOS · 🐧 Linux</h3><span class="meta">Mở Terminal (⌘ + Space, gõ Terminal), dán lệnh rồi Enter</span>
      <div class="cmd"><code>{esc(INSTALL_SH)}</code><button type="button">Sao chép</button></div></div>
    <div class="step"><h3>🪟 Windows 10/11</h3><span class="meta">Mở PowerShell từ menu Start, dán lệnh rồi Enter</span>
      <div class="cmd"><code>{esc(INSTALL_PS)}</code><button type="button">Sao chép</button></div></div>
  </div>
  <p class="note"><b>💻 Đây là phần mềm chạy trên máy tính của bạn.</b> Máy bật và app đang chạy thì dùng được giao diện và API tại <code>http://127.0.0.1:8001</code>; tắt máy, máy ngủ hoặc thoát app thì không dùng được. Khi cài, chọn <b>tự chạy khi mở máy</b> để API luôn sẵn sàng.</p>

  <h2 id="tinh-nang">✨ Tính năng</h2>
  <div class="cards3">
{feature_html}
  </div>
  <div class="shots">
{shot_html}
  </div>

  <h2 id="nghe-thu">🎧 Nghe thử 25 giọng có sẵn</h2>
  <p class="sample">“{esc(sample)}”</p>
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

  <h2 id="moi">📝 Có gì mới</h2>
  <p class="lead">Ba bản gần nhất — xem đầy đủ ở <a href="{GH}/releases">Releases</a>.</p>
  <div class="cards3">
{news_html}
  </div>

  <h2 id="su-co">🛠 Không cài được? Xem ở đây</h2>
  <p class="lead">Các trường hợp hay gặp và cách xử lý. Vẫn chưa được: nhắn <a href="{FB}">Đặng Hữu Sơn</a> kèm ảnh chụp màn hình lỗi.</p>
{trouble_html}

  <footer>
    <span>Phát triển bởi <a href="{FB}">Đặng Hữu Sơn</a> — CEO &amp; Co-Founder LovinBot AI.</span>
    <span>Dựa trên model AI <a href="https://github.com/pnnbao97/VieNeu-TTS">VieNeu-TTS</a> của Phạm Nguyễn Ngọc Bảo · Giấy phép Apache 2.0 · <a href="{GH}">Mã nguồn trên GitHub</a></span>
  </footer>
</div>
<script>
document.querySelector(".filters").addEventListener("click", (e) => {{
  const c = e.target.closest(".chip"); if (!c) return;
  document.querySelectorAll(".chip").forEach((x) => x.setAttribute("aria-pressed", x === c));
  const f = c.dataset.f;
  document.querySelectorAll(".voice").forEach((v) => {{
    v.hidden = !(!f || (f === "star" ? v.dataset.star : f.startsWith("g:") ? v.dataset.g === f.slice(2) : v.dataset.r === f.slice(2)));
  }});
}});
document.addEventListener("play", (e) => {{
  document.querySelectorAll("audio").forEach((a) => {{ if (a !== e.target) a.pause(); }});
}}, true);
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
print("docs/index.html", len(page) // 1024, "KB ·", len(cards), "giọng · release", tag, sizes and "có dung lượng" or "chưa có dung lượng")
