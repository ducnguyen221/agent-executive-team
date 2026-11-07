# Nhật ký thay đổi

## Chưa phát hành

SPR-02 (hợp đồng gọi `1.1.0`):

- Thêm `--format text`: bản đọc cho người, mọi chữ của input nằm trong ngoặc kép và được thoát; JSON mặc định giữ từng byte.
- Thêm mã `invalid_arguments` (exit 2): đối số sai bị từ chối trước khi đọc stdin.
- CLI bền khi luồng chuẩn đóng hoặc ghi hỏng; một hàm duy nhất đọc ngày.
- Script khởi chạy nằm trong skill (`skills/chief-of-staff/scripts/executive_memo.py`), chạy được từ nơi cài trên bash và PowerShell.
- Thêm `docs/CONTRACT.md`, `ECOSYSTEM.md`, `CHANGELOG.md`.
- CI GitHub Actions: Ubuntu, macOS, Windows × Python 3.11 đến 3.13, công cụ test cài từ file khóa có hash.
- Thêm `.claude-plugin/marketplace.json`; `CLAUDE.md` ở gốc chuyển thành `.claude/CLAUDE.md` (import `@../AGENTS.md`) để `claude plugin validate --strict` đạt.

## 0.1.0 — 2026-11-07

- Khởi tạo: lát ngoại tuyến đầu tiên, một lệnh đọc dữ liệu tổng hợp từ stdin và in bản nháp memo quyết định xác định; một skill `chief-of-staff`.
