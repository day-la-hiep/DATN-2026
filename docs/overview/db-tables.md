# Giải thích chi tiết sơ đồ cơ sở dữ liệu

Nguồn: [db-diagram.dbml](db-diagram.dbml) (khớp ORM `core/app/models/*.py`, migration head `3e4b8f67b9ca`).
Entity nghiệp vụ tương ứng nằm ở `core/app/dto/base/` (mỗi bounded context một file).

## 0. Quy ước chung

- **Khoá chính `id`**: chuỗi tối đa 64 ký tự do **DB sinh** (`gen_random_uuid()`). Dữ liệu cũ còn id dạng `conv-<uuid>`, `msg-<uuid>` nên cột là chuỗi chứ không phải kiểu `uuid`.
- **Không dùng Postgres ENUM**: các cột trạng thái / loại (`status`, `sender`, `fact_type`...) là `varchar`, giá trị hợp lệ do code (`app/common/constant.py`) kiểm soát, để thêm giá trị mới không cần migration.
- **Thời gian** là `timestamptz` (có múi giờ, lưu UTC).
- **Nơi lưu dữ liệu khác**: file lớn (PDF, ảnh, `pages.jsonl`, chunk) ở **MinIO**, bảng `files` chỉ giữ metadata + `storage_key`; vector ở **Qdrant**; Knowledge Graph ở **Neo4j**.
- **Trạng thái triển khai**: bảng ghi "mới có schema" nghĩa là đã có bảng + entity nhưng **chưa có API / luồng nghiệp vụ** dùng nó.
- **Kiểu quan hệ**: `1-n` (một cha, nhiều con), `1-1`, `n-n` (qua bảng nối có khoá chính kép).

### Nhóm bảng

| Nhóm | Bảng |
|---|---|
| Người dùng | `users`, `patient_profiles`, `doctors`, `admins` |
| Hội thoại & tư vấn | `conversations`, `messages`, `message_files`, `consultation_sessions`, `video_calls` |
| Bệnh án | `medical_records`, `patient_images` |
| Lâm sàng | `clinical_fact_templates`, `clinical_facts`, `clinical_provenances`, `pre_consultation_reports` |
| File | `files` |
| Tài liệu (pipeline số hoá sách) | `documents`, `document_stages`, `document_overrides` |

### Bản đồ quan hệ

```
users 1─n patient_profiles 1─n conversations 1─n messages n─n files (message_files)
  │            │                    │               │
  ├─1─1 doctors│                    └─1─n consultation_sessions 1─1 pre_consultation_reports
  └─1─1 admins │                                      ├─1─n video_calls
               │                                      │ (messages.consultation_session_id, messages.video_call_id)
               ├─1─n medical_records 1─n patient_images ─n─1 files
               └─1─n clinical_facts n─1 clinical_fact_templates
                          └─n─n messages (clinical_provenances)

documents 1─n document_stages 1─1 document_overrides ;  documents ─n─1 files
```

---

## 1. Nhóm Người dùng

### `users` — tài khoản

Field chung của mọi loại tài khoản. Vai trò bác sĩ / quản trị là bảng con 1-1 (`doctors`, `admins`), bệnh nhân là `patient_profiles`. Chưa có API đăng ký / đăng nhập.

| Field | Kiểu | Null | Ý nghĩa |
|---|---|---|---|
| `id` | varchar(64) PK | không | Mã tài khoản, DB sinh. |
| `username` | varchar(64) | không, **unique** | Tên đăng nhập. |
| `full_name` | varchar(255) | không | Họ tên đầy đủ. |
| `dob` | date | không | Ngày sinh. |
| `gender` | varchar(16) | không | `male` \| `female`. |
| `password_hash` | varchar(255) | có | Hash mật khẩu. `NULL` = tài khoản mẫu chưa đặt mật khẩu, chưa đăng nhập được. |
| `created_at` | timestamptz | không | Thời điểm tạo tài khoản. |

### `patient_profiles` — hồ sơ bệnh nhân

Một tài khoản quản lý được **nhiều hồ sơ** (bản thân, người nhà). Hội thoại, bệnh án và dữ kiện lâm sàng đều gắn vào hồ sơ này, không gắn thẳng vào `users`.

| Field | Kiểu | Null | Ý nghĩa |
|---|---|---|---|
| `id` | varchar(64) PK | không | Mã hồ sơ. |
| `user_id` | varchar(64) FK → `users.id` | không | Tài khoản quản lý hồ sơ. `ON DELETE CASCADE`. Có index. |
| `full_name` | varchar(255) | không | Họ tên người bệnh (có thể khác chủ tài khoản). |
| `dob` | date | không | Ngày sinh người bệnh. |
| `gender` | varchar(16) | không | `male` \| `female`. |
| `created_at` | timestamptz | không | Thời điểm tạo hồ sơ. |

### `doctors` — vai trò bác sĩ

Quan hệ **1-1** với `users`: PK đồng thời là FK nên một user chỉ có tối đa một dòng bác sĩ. Các bảng khác trỏ vào `doctors.user_id` (không phải `users.id`) để DB chặn việc gán người không phải bác sĩ.

| Field | Kiểu | Null | Ý nghĩa |
|---|---|---|---|
| `user_id` | varchar(64) PK, FK → `users.id` | không | Tài khoản được cấp vai trò bác sĩ. `ON DELETE CASCADE`. |
| `description` | text | không | Giới thiệu chuyên môn của bác sĩ. |

### `admins` — vai trò quản trị

Quan hệ 1-1 với `users`, đánh dấu tài khoản quản trị (khu `/admin/documents`). Chưa có field riêng.

| Field | Kiểu | Null | Ý nghĩa |
|---|---|---|---|
| `user_id` | varchar(64) PK, FK → `users.id` | không | Tài khoản quản trị. `ON DELETE CASCADE`. |

---

## 2. Nhóm Hội thoại & tư vấn

### `conversations` — cuộc hội thoại

Một cuộc chat của một hồ sơ bệnh nhân. Chủ tài khoản suy ra qua `patient_profiles.user_id`, không lưu lặp ở đây.

| Field | Kiểu | Null | Ý nghĩa |
|---|---|---|---|
| `id` | varchar(64) PK | không | Mã hội thoại. |
| `patient_profile_id` | varchar(64) FK → `patient_profiles.id` | không | Hồ sơ bệnh nhân sở hữu hội thoại. |
| `title` | varchar(255) | không, mặc định `''` | Tiêu đề hiển thị trong danh sách chat. |
| `model` | varchar(32) | không | Id ngắn của model trong `AGENT_MODEL_CHOICES` (không phải chuỗi `provider:model`); worker tự map sang model thật khi chạy lượt, nên đổi danh sách model không cần migration. |
| `created_at` | timestamptz | không | Thời điểm tạo. |
| `updated_at` | timestamptz | không | Lần cập nhật gần nhất (tự cập nhật khi sửa). |

### `messages` — tin nhắn

Một luồng chung cho **AI, bệnh nhân và bác sĩ**, phân biệt bằng `sender`. Các mốc tư vấn và cuộc gọi video cũng hiện thành tin trong luồng này.

| Field | Kiểu | Null | Ý nghĩa |
|---|---|---|---|
| `id` | varchar(64) PK | không | Mã tin nhắn. |
| `conversation_id` | varchar(64) FK → `conversations.id` | không | Hội thoại chứa tin. |
| `sender` | varchar(20) | không | Người gửi: `patient` \| `ai` \| `doctor`. |
| `message_type` | varchar(32) | không, mặc định `text` | Loại tin: `text`, `attached` (có đính kèm), `video_call`, `consultation_requested`, `consultation_accepted`, `consultation_resolved`. Là cột riêng để lọc / đếm theo loại. |
| `video_call_id` | varchar(64) FK → `video_calls.id` | có | Chỉ điền với `message_type = video_call`. `ON DELETE SET NULL`. |
| `consultation_session_id` | varchar(64) FK → `consultation_sessions.id` | có | Chỉ điền với 3 tin mốc `consultation_*`: tin thuộc phiên tư vấn nào. `ON DELETE SET NULL`. Có index. |
| `content` | text | không, mặc định `''` | Nội dung chữ. |
| `status` | varchar(20) | không | Trạng thái xử lý: `queued` \| `done` \| `question` (còn khai báo `pending` \| `streaming`). `question` = agent đang chờ người dùng trả lời. |
| `metadata` | jsonb | có | Dữ liệu phụ (ORM đặt tên attribute là `extra` vì `metadata` trùng tên reserved của SQLAlchemy). Tin AI: `reasoning[]` (các bước lập luận), `choice` (câu hỏi lại), `sources[]` (nguồn trích dẫn). Tin người dùng: `attached_files`, `is_option_response`. |
| `created_at` | timestamptz | không | Thời điểm tạo tin. |

### `message_files` — tệp đính kèm của tin nhắn (n-n)

Bảng nối giữa tin nhắn và file. Một tin có thể đính kèm nhiều file, một file có thể được dùng lại ở nhiều chỗ.

| Field | Kiểu | Null | Ý nghĩa |
|---|---|---|---|
| `message_id` | varchar(64) PK, FK → `messages.id` | không | Tin nhắn. `ON DELETE CASCADE`. |
| `file_id` | varchar(64) PK, FK → `files.id` | không | File đính kèm. `ON DELETE CASCADE`. |

### `consultation_sessions` — phiên tư vấn bác sĩ

Mốc đánh dấu **một lần bệnh nhân nhờ bác sĩ hỗ trợ**; bảng này **không chứa tin nhắn**. Tin trao đổi nằm trong `messages` (`sender = doctor`), ba mốc yêu cầu / nhận / đóng là tin `consultation_*` trỏ về phiên. Bác sĩ xem luồng chat từ đầu đến tin `consultation_resolved` của phiên (phiên còn mở: tới hiện tại). Bệnh nhân vẫn chat AI song song. Mới có schema.

| Field | Kiểu | Null | Ý nghĩa |
|---|---|---|---|
| `id` | varchar(64) PK | không | Mã phiên. |
| `conversation_id` | varchar(64) FK → `conversations.id` | không | Hội thoại có phiên tư vấn. `ON DELETE CASCADE`. Có index. |
| `doctor_id` | varchar(64) FK → `doctors.user_id` | có | Bác sĩ nhận ca. `NULL` khi chưa ai nhận. `ON DELETE SET NULL`. |
| `status` | varchar(16) | không, mặc định `pending` | `pending` (chờ bác sĩ nhận) → `active` (đang trao đổi) → `resolved` (đã đóng). |
| `reason` | text | không | Lý do bệnh nhân nhờ bác sĩ. |
| `requested_at` | timestamptz | không | Lúc bệnh nhân gửi yêu cầu. |
| `started_at` | timestamptz | có | Lúc bác sĩ nhận. |
| `resolved_at` | timestamptz | có | Lúc đóng phiên. |

Ràng buộc:
- `CHECK doctor_when_not_pending`: `status = 'pending' OR doctor_id IS NOT NULL` — phiên đã nhận hoặc đã đóng thì bắt buộc có bác sĩ.
- `CHECK resolved_at_when_resolved`: `status <> 'resolved' OR resolved_at IS NOT NULL`.
- Unique **một phần** `uq_consultation_sessions_open_per_conversation` trên `conversation_id` với điều kiện `status <> 'resolved'` — mỗi hội thoại **tối đa 1 phiên đang mở**, vì tin bác sĩ gắn với phiên theo khoảng thời gian, hai phiên mở cùng lúc sẽ không phân biệt được.

### `video_calls` — cuộc gọi video

Cuộc gọi **thuộc về một phiên tư vấn** (một phiên có nhiều cuộc gọi). Tách bảng riêng (không chỉ nằm trong `messages.metadata`) vì cuộc gọi có vòng đời `pending → ongoing → ended` được cập nhật sau khi tin nhắn đã tạo. Tin `message_type = video_call` trỏ tới đây qua `messages.video_call_id`. Mới có schema.

| Field | Kiểu | Null | Ý nghĩa |
|---|---|---|---|
| `id` | varchar(64) PK | không | Mã cuộc gọi. |
| `consultation_session_id` | varchar(64) FK → `consultation_sessions.id` | không | Phiên tư vấn chứa cuộc gọi. `ON DELETE CASCADE`. Có index. |
| `room_id` | varchar(128) | không, **unique** | Mã phòng video. |
| `status` | varchar(16) | không, mặc định `pending` | `pending` \| `ongoing` \| `ended`. |
| `started_at` | timestamptz | có | Lúc bắt đầu gọi. |
| `ended_at` | timestamptz | có | Lúc kết thúc. |
| `created_at` | timestamptz | không | Lúc tạo cuộc gọi. |

---

## 3. Nhóm Bệnh án

### `medical_records` — bệnh án

Bệnh án do **bác sĩ** ghi cho một hồ sơ bệnh nhân; một hồ sơ có nhiều bệnh án. Không gắn với phiên tư vấn cụ thể. Mới có schema.

| Field | Kiểu | Null | Ý nghĩa |
|---|---|---|---|
| `id` | varchar(64) PK | không | Mã bệnh án. |
| `patient_profile_id` | varchar(64) FK → `patient_profiles.id` | không | Hồ sơ bệnh nhân. `ON DELETE CASCADE`. Có index. |
| `doctor_id` | varchar(64) FK → `doctors.user_id` | có | Bác sĩ ghi bệnh án. `ON DELETE SET NULL` — bác sĩ bị xoá thì bệnh án vẫn giữ. |
| `diagnosis` | text | không | Chẩn đoán của bác sĩ. |
| `notes` | text | không, mặc định `''` | Ghi chú thêm. |
| `is_reference_case` | boolean | không, mặc định `false` | Ca bệnh tham khảo: bác sĩ xác nhận dùng làm dữ liệu cho KB / chatbot tra ca tương tự (phải ẩn định danh khi đưa vào KB). |
| `created_at` | timestamptz | không | Lúc ghi bệnh án. |

### `patient_images` — ảnh bệnh

Ảnh bệnh do bác sĩ gắn vào bệnh án. Trỏ FK tới `files` thay vì chép file, nên bác sĩ chọn lại được ảnh bệnh nhân đã gửi trong chat mà không tạo bản sao trong MinIO. Mới có schema.

| Field | Kiểu | Null | Ý nghĩa |
|---|---|---|---|
| `id` | varchar(64) PK | không | Mã ảnh. |
| `medical_record_id` | varchar(64) FK → `medical_records.id` | không | Bệnh án chứa ảnh. `ON DELETE CASCADE`. Có index. |
| `file_id` | varchar(64) FK → `files.id` | không | File ảnh trong MinIO. `ON DELETE CASCADE`. |
| `body_site` | varchar(128) | không, mặc định `''` | Vị trí trên cơ thể. |
| `description` | text | không, mặc định `''` | Mô tả tổn thương. |
| `confirmed_label` | varchar(128) | có | Nhãn bác sĩ xác nhận, nên khớp tên lớp của CNN để dùng làm dữ liệu huấn luyện. |
| `captured_at` | timestamptz | có | Thời điểm chụp ảnh. |

---

## 4. Nhóm Lâm sàng

Luồng ý tưởng: agent trích **dữ kiện lâm sàng** từ hội thoại, mỗi dữ kiện luôn tạo từ một **mẫu chuẩn**, ghi lại **tin nhắn nguồn**, và khi bệnh nhân nhờ bác sĩ thì có một **báo cáo tóm tắt** cho phiên đó. Cả nhóm mới có schema, chưa có bước trích xuất.

### `clinical_fact_templates` — mẫu dữ kiện lâm sàng

Danh mục chuẩn (ví dụ "ngứa", "dị ứng penicillin"). Agent chỉ được trích fact theo mẫu có sẵn để nhãn và `ontology_id` nhất quán giữa các bệnh nhân.

| Field | Kiểu | Null | Ý nghĩa |
|---|---|---|---|
| `id` | varchar(64) PK | không | Mã mẫu. |
| `fact_type` | varchar(32) | không | Loại: `symptom` (triệu chứng cơ năng), `lesion` (tổn thương da), `history` (tiền sử / diễn tiến), `medication` (thuốc), `allergy` (dị ứng), `image_finding` (kết quả phân loại ảnh, chỉ là giả thuyết), `other`. |
| `label` | varchar(255) | không, **unique** | Tên chuẩn của mẫu. |
| `description` | text | không, mặc định `''` | Gợi ý cho agent / bác sĩ biết cần hỏi và ghi gì vào `clinical_facts.detail`. |
| `ontology_id` | varchar(128) | có | Id DermO / PrimeKG đã chuẩn hoá, dùng để vẽ KG liên quan bệnh nhân. |

### `clinical_facts` — dữ kiện lâm sàng

Dữ kiện của **hồ sơ bệnh nhân** (không thuộc riêng một cuộc chat), luôn tạo từ một mẫu. **Không sửa đè**: bệnh nhân đính chính thì tạo fact mới và đánh dấu fact cũ `superseded`, để bác sĩ vẫn thấy lịch sử khai báo. Hội thoại sinh ra fact truy ngược qua `clinical_provenances` → `messages`.

| Field | Kiểu | Null | Ý nghĩa |
|---|---|---|---|
| `id` | varchar(64) PK | không | Mã fact. |
| `patient_profile_id` | varchar(64) FK → `patient_profiles.id` | không | Hồ sơ bệnh nhân sở hữu fact. `ON DELETE CASCADE`. Có index. |
| `template_id` | varchar(64) FK → `clinical_fact_templates.id` | không | Mẫu của fact; loại / nhãn / ontology lấy từ mẫu. `ON DELETE RESTRICT` — không xoá được mẫu đang có fact dùng. Có index. |
| `detail` | text | không, mặc định `''` | Giá trị cụ thể của bệnh nhân: vị trí, thời gian khởi phát, mức độ, diễn tiến... |
| `status` | varchar(16) | không, mặc định `active` | `active` \| `superseded` (đã bị fact mới thay). |
| `superseded_by_id` | varchar(64) FK → `clinical_facts.id` (tự tham chiếu) | có | Fact mới thay thế fact này. `ON DELETE SET NULL`. |
| `created_at` | timestamptz | không | Lúc ghi fact. |

### `clinical_provenances` — nguồn gốc của fact (n-n)

Bảng nối giữa fact và tin nhắn, thể hiện entity `ClinicalProvenance`. Một fact có thể đến từ nhiều tin (kể cả ở nhiều hội thoại), một tin có thể sinh nhiều fact. Fact do bác sĩ tự nhập thì không có dòng nào ở đây. Sau này muốn thêm thông tin riêng cho mỗi cặp (đoạn trích, độ tin cậy) thì thêm cột vào bảng này.

| Field | Kiểu | Null | Ý nghĩa |
|---|---|---|---|
| `fact_id` | varchar(64) PK, FK → `clinical_facts.id` | không | Fact. `ON DELETE CASCADE`. |
| `message_id` | varchar(64) PK, FK → `messages.id` | không | Tin nhắn gốc làm bằng chứng. `ON DELETE CASCADE`. |

### `pre_consultation_reports` — báo cáo tiền tư vấn

Báo cáo AI tóm tắt cho bác sĩ đọc trước khi nhận ca, **1 báo cáo / phiên tư vấn**. Chỉ là gợi ý hỗ trợ, **không phải chẩn đoán y khoa**. Tạm thời chỉ có phần tóm tắt; fact lâm sàng bác sĩ xem trực tiếp từ hồ sơ bệnh nhân.

| Field | Kiểu | Null | Ý nghĩa |
|---|---|---|---|
| `id` | varchar(64) PK | không | Mã báo cáo. |
| `consultation_session_id` | varchar(64) FK → `consultation_sessions.id` | không, **unique** | Phiên tư vấn của báo cáo; unique tạo quan hệ 1-1. `ON DELETE CASCADE`. |
| `summary` | text | không | Nội dung tóm tắt. |
| `created_at` | timestamptz | không | Lúc sinh báo cáo. |

---

## 5. Bảng File

### `files` — metadata file trong MinIO

Dùng chung cho ảnh đính kèm tin nhắn, ảnh bệnh trong bệnh án và file của tài liệu. Nội dung file nằm ở MinIO, không nằm trong DB.

| Field | Kiểu | Null | Ý nghĩa |
|---|---|---|---|
| `id` | varchar(64) PK | không | Mã file. |
| `file_name` | varchar(255) | không | Tên hiển thị (ví dụ tên file gốc người dùng upload). |
| `storage_key` | varchar(512) | không, **unique** | Khoá đầy đủ của object trong bucket MinIO (không phải đường dẫn tương đối trong thư mục của entity). |
| `content_type` | varchar(128) | có | MIME type, ví dụ `application/pdf`. |
| `size` | bigint | có | Dung lượng, đơn vị byte. |
| `created_at` | timestamptz | không | Lúc tạo bản ghi. |

---

## 6. Nhóm Tài liệu (pipeline số hoá sách)

Admin upload PDF → qua 4 bước (`ingest` → `toc` → `chunks` → `index`), mỗi bước người duyệt phải approve trước khi bước sau chạy. Entity lồng nhau: `Document` → `DocumentStage` → `DocumentStageOverride`.

### `documents` — tài liệu

| Field | Kiểu | Null | Ý nghĩa |
|---|---|---|---|
| `id` | varchar(64) PK | không | Mã tài liệu; cũng là tên thư mục `document/<id>/` trong MinIO và `document_id` trong payload Qdrant. |
| `title` | varchar(255) | không | Tiêu đề. |
| `type` | varchar(16) | không, mặc định `book` | `book` \| `image` \| `video` \| `other`. Hiện chỉ `book` đi qua pipeline. |
| `source_file_id` | varchar(64) FK → `files.id` | có | File gốc người dùng upload (`source.pdf`). `ON DELETE SET NULL`. |
| `ingested_file_id` | varchar(64) FK → `files.id` | có | Kết quả bước ingest (`pages.jsonl`); chỉ có khi đã qua bước ingest. `ON DELETE SET NULL`. |
| `pdf_pages` | int | có | Số trang PDF; chỉ có với `type = book`. |
| `profile` | jsonb | có | Cấu hình xử lý của tài liệu (engine đọc chữ, tham số...), đọc / ghi qua Pydantic (`app/models/document_profile.py::Profile`). |
| `uploaded_by_id` | varchar(64) FK → `doctors.user_id` | có | Bác sĩ tải lên (chỉ bác sĩ được tải). `ON DELETE SET NULL`; `NULL` với tài liệu tạo trước khi có đăng nhập. |
| `created_at` | timestamptz | không | Lúc tạo. |
| `updated_at` | timestamptz | không | Lần cập nhật gần nhất (tự cập nhật). |

### `document_stages` — trạng thái từng bước

**4 dòng cho mỗi tài liệu** (ingest, toc, chunks, index), tạo cùng lúc với tài liệu. Có khoá `id` riêng để `document_overrides` trỏ tới mà không phải lặp `document_id`.

| Field | Kiểu | Null | Ý nghĩa |
|---|---|---|---|
| `id` | varchar(64) PK | không | Mã dòng bước. |
| `document_id` | varchar(64) FK → `documents.id` | không | Tài liệu. `ON DELETE CASCADE`. |
| `stage_id` | varchar(32) | không | Mã bước: `ingest` \| `toc` \| `chunks` \| `index`. Cặp `(document_id, stage_id)` là **unique**. |
| `state` | varchar(32) | không, mặc định `not_started` | `not_started → running → pending_review → approved`; ngoài ra `failed`, `cancelled`, và `stale` (bước phía trước chạy lại nên kết quả cũ không còn đúng). |
| `options` | jsonb | có | Tham số của lần chạy. |
| `progress` | jsonb | có | Tiến độ khi đang chạy (FE poll để hiển thị). |
| `summary` | jsonb | có | Tóm tắt kết quả, hiển thị cho người duyệt. |
| `error` | text | có | Thông báo lỗi khi `failed`; lỗi người dùng sửa được hiển thị nguyên văn trên UI. |
| `started_at` | timestamptz | có | Lúc bắt đầu chạy. |
| `finished_at` | timestamptz | có | Lúc chạy xong / dừng. |
| `approved_at` | timestamptz | có | Lúc người duyệt approve. |

### `document_overrides` — sửa tay của người duyệt

Chỉnh sửa tay của người duyệt lên kết quả một bước, **tách khỏi kết quả máy** để chạy lại bước không mất công sửa. Thuộc về bước qua `document_stage_id`, tài liệu suy ra từ bước đó. Hiện tối đa 1 dòng / bước.

| Field | Kiểu | Null | Ý nghĩa |
|---|---|---|---|
| `document_stage_id` | varchar(64) PK, FK → `document_stages.id` | không | Bước được sửa. `ON DELETE CASCADE`. |
| `data` | jsonb | không, mặc định `{}` | Nội dung sửa tay. Ví dụ bước `toc`: `{<id mục>: {...}, _deleted, _added, _offset}` (sửa mục, xoá, thêm, lệch số trang). Giá trị `null` khi cập nhật nghĩa là hoàn tác một override. |
| `updated_at` | timestamptz | không | Lần sửa gần nhất (tự cập nhật). |

---

## 7. Hành vi xoá (`ON DELETE`) tóm tắt

| Quan hệ | Khi xoá bảng cha |
|---|---|
| `users` → `patient_profiles`, `doctors`, `admins` | CASCADE |
| `patient_profiles` → `medical_records`, `clinical_facts` | CASCADE |
| `conversations` → `consultation_sessions` | CASCADE |
| `consultation_sessions` → `pre_consultation_reports`, `video_calls` | CASCADE |
| `messages` / `files` → `message_files` | CASCADE |
| `medical_records` / `files` → `patient_images` | CASCADE |
| `clinical_facts` / `messages` → `clinical_provenances` | CASCADE |
| `documents` → `document_stages` → `document_overrides` | CASCADE |
| `doctors` → `consultation_sessions.doctor_id`, `medical_records.doctor_id`, `documents.uploaded_by_id` | SET NULL (dữ liệu vẫn giữ) |
| `video_calls` / `consultation_sessions` → `messages.video_call_id` / `messages.consultation_session_id` | SET NULL |
| `files` → `documents.source_file_id` / `ingested_file_id` | SET NULL |
| `clinical_facts` → `clinical_facts.superseded_by_id` | SET NULL |
| `clinical_fact_templates` → `clinical_facts` | **RESTRICT** (không xoá được mẫu đang được dùng) |
