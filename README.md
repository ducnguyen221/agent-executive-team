# Agent Executive Team

Plugin trợ lý điều hành, lát ngoại tuyến đầu tiên: một lệnh đọc dữ liệu tổng hợp (synthetic) từ stdin và in ra bản nháp memo quyết định để người có thẩm quyền xem xét.

## Giới hạn phạm vi (đọc trước)

- Kết quả là **bản nháp xác định** (deterministic draft): cùng input cho cùng byte output. Đó **không phải** lời khuyên AI đã được nghiệm thu hay đánh giá chất lượng.
- Chỉ **dữ liệu tổng hợp**, tenant cố định `synthetic-demo`. Không dữ liệu thật, không kết nối hệ thống, không gọi mạng, không gọi LLM, không ghi file hay sổ ledger.
- Plugin không xác thực dữ liệu: nhãn bằng chứng luôn là `unverified` (chưa xác minh).
- Memo luôn chờ người quyết định (`needs_human_decision`); không phê duyệt và không hành động thay ai.
- Nội dung trong input là dữ liệu, không phải mệnh lệnh: chỉ thị hay lời tự nhận thẩm quyền trong đó không được thực hiện.

## Cách chạy

Cần Python 3.12, chỉ dùng thư viện chuẩn. Từ gốc repo:

```
PYTHONPATH=src python -B -m agent_executive_team < tests/fixtures/valid.json
```

Trên PowerShell (Windows): đặt `$env:PYTHONPATH = "src"` rồi chạy `cmd /c "python -B -m agent_executive_team < tests\fixtures\valid.json"`. Không dùng ống PowerShell (`Get-Content ... | python ...` hay bất kỳ chuỗi PowerShell nào đưa vào lệnh): PowerShell 5.1 chèn dấu BOM (`EF BB BF`) vào đầu stdin, CLI từ chối BOM và trả exit 2 `invalid_input` dù input hợp lệ.

Chạy test và đo độ phủ (cần `pytest`, `pytest-cov`; ngưỡng 80 %):

```
python -m pytest -q --cov=agent_executive_team --cov-report=term-missing --cov-fail-under=80
```

## Hợp đồng input

Một đối tượng JSON UTF-8 tối đa 65536 byte, không BOM, không khóa trùng, không khóa lạ. Bốn khóa cấp trên cùng, thiếu hay thừa đều bị từ chối: `version`, `decision`, `options`, `evidence`.

| Khóa | Quy tắc |
|---|---|
| `version` | số nguyên `1` |
| `decision` | `question`, `owner`, `dissent` (văn bản); `deadline`, `review_date`, `as_of` (ngày `YYYY-MM-DD` hợp lệ) |
| `options` | 2 đến 4 phương án; mỗi phương án có `name`, `pros`, `cons`, `reversal`, `actions` (văn bản) và `status_quo` (true/false); đúng một phương án có `status_quo` true |
| `evidence` | 0 đến 20 bằng chứng; mỗi bằng chứng có `id` (không trùng), `tenant` (chỉ `synthetic-demo`), `owner`, `period`, `claim`, `source_uri` (văn bản), `effective_from`, `effective_to` (ngày, từ không sau đến), `kind` (`actual`, `forecast` hoặc `unknown`), `conflict_group` (văn bản, được để trống) |

Văn bản dài tối đa 500 ký tự và không được chỉ gồm khoảng trắng (trừ `conflict_group` được để `""`). `source_uri` chỉ là chuỗi văn bản, không bao giờ được truy cập.

## Hợp đồng output

Một dòng JSON (khóa sắp xếp, ASCII, kết bằng đúng một LF) gồm: `version`, `status` (`needs_human_decision`), `agent_status` (`needs_review`), `decision_status` (`proposed`), `decision`, `options` (chép nguyên), `evidence` (mỗi mục thêm `verification` là `unverified` và `period_status` là `in_period` hoặc `out_of_period` tùy `as_of` có nằm trong khoảng hiệu lực), `warnings`.

`warnings` là danh sách `{code, evidence_ids}` với `code` là `no_evidence` (không có bằng chứng), `out_of_period` (bằng chứng ngoài kỳ) hoặc `conflict` (từ hai bằng chứng cùng `conflict_group`).

## Mã thoát

- exit 0: memo trên stdout.
- exit 2: input không hợp lệ; stderr là `invalid_input`, stdout rỗng, không in lại nội dung input.
- exit 1: lỗi nội bộ hoặc I/O; stderr là `internal_error`, không in lại nội dung input.

## Giấy phép

`UNLICENSED` tạm, chưa phát hành. Chủ repo chốt giấy phép trước khi tạo remote.
