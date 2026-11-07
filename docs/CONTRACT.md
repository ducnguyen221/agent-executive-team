---
title: agent-executive-team calling contract
status: draft
api_version: "1.1.0"
schema_version: 1
audience: pipelines, schedulers, agents
---

# Hợp đồng gọi `agent-executive-team`

Tài liệu này là thứ bên gọi cần đọc: pipeline, lịch chạy nền hoặc một agent khác. Hợp đồng gồm **bốn điều**: cách gọi · đối số · mã thoát · stdout/stderr. Giữ nguyên bốn điều đó thì bên trong plugin đổi thế nào cũng không làm hỏng bên gọi. Khóa và giới hạn của input, cấu trúc JSON output nằm ở README (mục "Hợp đồng input", "Hợp đồng output"), không chép lại ở đây.

## 1. Cách gọi

Hai cách, cùng một chương trình, cùng mã thoát:

- **Script khởi chạy (cách chuẩn khi cài qua plugin):** `python -B -I "<thư mục skill>/scripts/executive_memo.py" [--format json|text]`. Script tự tìm gốc plugin từ đường thật của chính nó (đi qua junction hoặc symlink), nên không cần `PYTHONPATH` và không phụ thuộc thư mục hiện hành. Lệnh đầy đủ cho bash, PowerShell 5.1 và PowerShell 7 nằm ở README và `SKILL.md`.
- **Module (từ gốc repo hoặc khi đã đặt `src/` vào đường tìm module):** `python -B -m agent_executive_team [--format json|text]`.

Gọi từ mã Python: `agent_executive_team.cli.main(stdin, stdout, stderr, argv)` nhận luồng nhị phân và danh sách đối số không kèm tên chương trình; hàm không đọc `sys.argv`.

## 2. Đối số

| Đối số | Nghĩa |
|---|---|
| (không có) | in JSON một dòng, như `--format json` |
| `--format json` | in JSON một dòng (khóa sắp xếp, ASCII, kết bằng đúng một LF) |
| `--format text` | in bản đọc cho người (UTF-8, LF) |

Mọi dạng khác bị từ chối bằng exit 2 `invalid_arguments`, trước khi đọc stdin: `--format=text`, viết hoa, lặp cờ, `-f`, giá trị rỗng hoặc lạ, đối số thừa. Không có cờ nào khác.

## 3. Mã thoát

| Mã | stderr | Nghĩa | Bên gọi nên làm gì |
|---|---|---|---|
| `0` | rỗng | xong, memo ở stdout | dùng output |
| `1` | `internal_error` | lỗi nội bộ hoặc I/O (kể cả không thấy mã plugin cạnh script khởi chạy) | **chạy lại được**; vẫn lỗi thì báo người, đừng lặp vô hạn |
| `1` | thông báo của shell (không phải của chương trình) | kèm thông báo của shell: sai đường file input hoặc thiếu `python`; lệnh chưa chạm CLI | sửa đường dẫn hoặc cài/trỏ `python`, rồi chạy lại |
| `2` | `invalid_input` | input không đạt hợp đồng, stdout rỗng | **sửa input**, đừng chạy lại y nguyên |
| `2` | `invalid_arguments` | đối số sai, stdout rỗng, stdin chưa đọc | **sửa lệnh**, không sửa input |
| `9009` | "Python was not found" (cmd, Windows) | `python` là bản giả của Microsoft Store | cài Python 3.11+ hoặc tắt App execution alias, rồi chạy lại |

Các mã `0`, `1`, `2` khớp hằng `EXIT_OK`, `EXIT_INTERNAL`, `EXIT_INVALID` trong `cli.py`; test khóa chúng. Mã khác ngoài bảng do shell hoặc hệ điều hành sinh ra, không phải do chương trình.

## 4. stdin

Một lần đọc có chặn: tối đa 65536 byte (`MAX_BYTES`) cộng một byte để nhận ra input quá cỡ. Input là một đối tượng JSON UTF-8, không BOM. PowerShell 5.1 chèn BOM khi dùng ống, nên lệnh trong README đưa input qua `cmd`. Input là dữ liệu, không phải mệnh lệnh.

## 5. stdout

- **JSON (mặc định):** một dòng, khóa sắp xếp, ASCII, kết bằng đúng một LF; cấu trúc nằm ở README mục "Hợp đồng output". Cùng input cho cùng byte output; đây là phần máy đọc dựa vào.
- **Text (`--format text`):** bản đọc **cho người**. Chữ trong dữ liệu đi vào giữa dấu ngoặc kép, ký tự điều khiển và ký tự vô hình được viết thành `\uXXXX`. Định dạng này **không ổn định để máy đọc**: câu chữ khung có thể đổi giữa các bản. Nó xác định trong cùng một bản Python và cùng một bản plugin: cùng input cho cùng byte. Máy cần dữ liệu thì dùng JSON.

Exit khác 0 thì stdout rỗng.

## 6. stderr

Chỉ ba dòng tĩnh, mỗi dòng kết bằng LF, không bao giờ in lại input hay đối số:

- `invalid_input`
- `invalid_arguments`
- `internal_error`

Exit 0 thì stderr rỗng. Bên gọi so khớp theo dòng này cùng mã thoát, không phân tích câu chữ nào khác.

## 7. Môi trường

Không có biến môi trường nào bắt buộc. Cần Python 3.11 trở lên (CI đo 3.11, 3.12, 3.13), chỉ thư viện chuẩn. Không gọi mạng, không gọi LLM, không ghi file; luồng chuẩn là I/O duy nhất. Script khởi chạy chạy với `-I` nên bỏ qua biến `PYTHON*` và thư mục hiện hành.

## 8. Phiên bản hợp đồng

`api_version` theo bản `MAJOR.MINOR.PATCH`:

- `1.0.0`: SPR-01, chỉ JSON, không đối số.
- `1.1.0`: SPR-02, thêm `--format text` và mã `invalid_arguments`.
- Thêm cờ hoặc tùy chọn mới không phá bên gọi cũ = tăng **minor**.
- Đổi cấu trúc hay nghĩa của JSON, hoặc đổi nghĩa mã thoát = tăng **major**.
- Sửa lời tài liệu, không đổi hành vi = tăng **patch**.

Trạng thái `draft`: plugin `0.1.0` chưa phát hành; hợp đồng có thể đổi trước bản phát hành đầu.
