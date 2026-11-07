# Hệ sinh thái

- **Role:** Biến dữ liệu quyết định tổng hợp thành bản nháp memo xác định, ngoại tuyến, luôn chờ người quyết.
- **Upstream:** Một file JSON tổng hợp do người vận hành cấp.
- **Downstream:** Người có thẩm quyền đọc bản nháp; không tự gửi, không tự quyết.
- **Bundles:** Chưa có; kết nối dữ liệu thật, xác minh bằng chứng và gửi memo là năng lực tương lai.
- **Handoff:** Memo `needs_human_decision` kèm cảnh báo; người có thẩm quyền chốt.
