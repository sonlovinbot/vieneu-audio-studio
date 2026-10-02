# Hướng dẫn: quảng cáo, thông báo, báo bản mới cho phần mềm đã cài

Mọi máy đã cài AI Audio Studio tự đọc file **[`docs/news.json`](news.json)** (qua
`https://sonlovinbot.github.io/vieneu-audio-studio/news.json`) mỗi 3 giờ. Sửa file này, commit,
push → khoảng 1 phút sau GitHub Pages cập nhật, các máy nhận ở lần mở app hoặc làm mới tiếp theo.
**Không cần phát hành lại phần mềm.**

## Hai vị trí hiển thị

| `placement` | Hiện ở đâu | Hợp cho |
|---|---|---|
| `sidebar` | Thẻ ở menu trái, ngay trên dòng "Phát triển bởi" (ẩn trên điện thoại). Hiện **1 thẻ** | Quảng cáo khoá học, sản phẩm, kênh |
| `top` | Thanh ngang trên đầu mọi trang. Tối đa **2 thanh** | Thông báo quan trọng, sự kiện, bảo trì |

Thanh **"Đã có bản mới"** tự hiện khi `latest_version` lớn hơn bản người dùng đang chạy — chỉ cần
tăng `latest_version` sau mỗi lần phát hành.

## Các trường

| Trường | Ý nghĩa |
|---|---|
| `id` | Mã riêng, **đổi mã khi đổi nội dung** (người dùng đã bấm ✕ mã cũ sẽ thấy lại nội dung mới) |
| `tone` | `info` (trung tính) · `warning` (vàng, cần chú ý) · `promo` (cam, quảng cáo) |
| `label` | Nhãn nhỏ trên quảng cáo, mặc định `Ad · Sponsor` |
| `title`, `text` | Tiêu đề (≤120 ký tự) và mô tả (≤300 ký tự). Chỉ chữ thường, không HTML |
| `image` | Ảnh cho thẻ sidebar, link `https://…` (nên ngang ~600×300) — bỏ trống nếu không dùng |
| `link`, `cta` | Link khi bấm (`https://…`) và chữ trên nút |
| `start`, `end` | Ngày bắt đầu / ngày **cuối cùng còn hiện**, dạng `2026-10-31`, tính theo giờ máy người dùng. **Quảng cáo (`placement: sidebar` hoặc `tone: promo`) bắt buộc có `end`** — thiếu thì app không hiện. Thông báo thường (`info`, `warning`) bỏ trống `end` = luôn hiện |
| `min_version`, `max_version` | Chỉ hiện cho bản trong khoảng này, ví dụ nhắc riêng người dùng bản cũ |
| `dismissible` | `true` = có nút ✕ để tắt (nhớ trong trình duyệt) |

## Xếp lịch quảng cáo nối tiếp nhau

Thẻ sidebar chỉ hiện **1 quảng cáo**: quảng cáo **đầu tiên trong danh sách** đang trong thời hạn. Vì vậy có
thể đặt sẵn quảng cáo kế tiếp, đến ngày nó tự thay chỗ — không cần ai bấm gì:

```json
"announcements": [
  { "id": "bootcamp-ai-vibecode-2026", "placement": "sidebar", "tone": "promo",
    "title": "Bootcamp AI Vibe Code 2026", "end": "2026-10-04", "...": "..." },
  { "id": "elearning-2026-10", "placement": "sidebar", "tone": "promo",
    "title": "Khoá e-learning …", "start": "2026-10-05", "end": "2026-11-30", "...": "..." }
]
```

Ảnh quảng cáo nên để trong thư mục [`docs/ads/`](ads/) rồi dùng link
`https://sonlovinbot.github.io/vieneu-audio-studio/ads/<tên-file>.jpg` (ảnh ngang ~2:1, rộng ~960px).

## Ví dụ: thông báo sự kiện trên đầu trang, tự tắt sau 31/10

```json
{
  "id": "webinar-2026-10",
  "placement": "top",
  "tone": "promo",
  "title": "Webinar miễn phí: Làm video AI với giọng đọc tiếng Việt",
  "text": "20h thứ Bảy 25/10 — đăng ký để nhận link tham gia.",
  "link": "https://example.com/dang-ky",
  "cta": "Đăng ký",
  "end": "2026-10-25",
  "dismissible": true
}
```

## An toàn và quyền riêng tư

- App chỉ **tải về** file JSON tĩnh, không gửi dữ liệu nào của người dùng đi.
- Chỉ nhận chữ và link `https` — không chạy được mã HTML/JavaScript từ xa, nên dù file bị sửa sai
  cũng không làm hỏng hay chiếm quyền app.
- Mất mạng thì dùng bản đã tải lần trước. Người dùng muốn tắt hẳn: đặt biến môi trường `VIENEU_NEWS=off`.
