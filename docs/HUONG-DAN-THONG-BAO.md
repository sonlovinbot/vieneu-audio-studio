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
| `title`, `text` | Tiêu đề (≤120 ký tự) và mô tả (≤300 ký tự). Chỉ chữ thường, không HTML |
| `image` | Ảnh cho thẻ sidebar, link `https://…` (nên ngang ~600×300) — bỏ trống nếu không dùng |
| `link`, `cta` | Link khi bấm (`https://…`) và chữ trên nút |
| `start`, `end` | Ngày bắt đầu / kết thúc dạng `2026-10-31` — bỏ trống = luôn hiện |
| `min_version`, `max_version` | Chỉ hiện cho bản trong khoảng này, ví dụ nhắc riêng người dùng bản cũ |
| `dismissible` | `true` = có nút ✕ để tắt (nhớ trong trình duyệt) |

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
