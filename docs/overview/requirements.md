# Yêu cầu hệ thống & trạng thái hiện tại

Tài liệu tổng hợp yêu cầu nghiệp vụ của Derma Hospital, chia theo module và chức năng để tiện giao việc.
Trạng thái được đối chiếu với code ngày **2026-10-05** (nhánh `feat/database`).

**Ký hiệu trạng thái**

| Ký hiệu | Ý nghĩa |
|---|---|
| ✅ Xong | chạy được end-to-end (BE + FE) |
| 🟡 Một phần | có một phần (chỉ BE, chỉ schema DB, hoặc làm đơn giản hơn yêu cầu) |
| 🔲 Chưa làm | chưa có code |
| ⏸ Hoãn | ngoài scope hiện tại hoặc chưa chốt luồng |

> Kết quả AI chỉ là gợi ý hỗ trợ, **không phải chẩn đoán y khoa**.

## 1. Tác nhân

| Tác nhân | Mô tả | Hiện trạng trong code |
|---|---|---|
| **Người dùng** | người đã đăng ký và đăng nhập; quản lý tài khoản của mình, đăng xuất | bảng `users` có, **chưa có đăng ký / đăng nhập**. FE hard-code `user-1`, cả app chỉ dùng 1 app token chung |
| **Bệnh nhân** | dùng hệ thống để tiền chẩn đoán và trao đổi về bệnh da liễu: chat với chatbot (gửi ảnh, mô tả triệu chứng), tra cứu bệnh và ca bệnh từ KB, đặt lịch khám, quản lý hồ sơ bệnh án / lịch sử khám / ảnh, trao đổi với bác sĩ qua chat hoặc video call (bác sĩ chưa tiếp nhận thì tiếp tục hỏi chatbot). Cuộc trò chuyện được tổng hợp thành clinical fact và báo cáo cho bác sĩ | bảng `patient_profiles` (một user có nhiều hồ sơ). Phần chat với chatbot đã chạy |
| **Bác sĩ** | xem báo cáo tổng hợp, clinical fact, nguồn lập luận từ KB, lịch sử và hồ sơ bệnh nhân; cập nhật hồ sơ sau khám; lưu ca bệnh và ảnh đã xác nhận (làm dữ liệu tham khảo, huấn luyện CNN); chat / video call với bệnh nhân và truy xuất tin nhắn nguồn làm bằng chứng; trực quan hoá Knowledge Graph; tải giáo trình / guideline lên để bổ sung KB | bảng `doctors` có, seed 1 bác sĩ. **Chưa có màn hình nào cho bác sĩ** |
| *(Admin — có trong code, không có trong yêu cầu)* | hiện là người dùng màn `/admin/documents` để nạp sách | bảng `admins`. Theo yêu cầu thì việc tải tài liệu là của **bác sĩ**, cần thống nhất lại vai trò |

## 2. Tổng quan theo module

| Mã | Module | Tác nhân | Trạng thái | Tài liệu |
|---|---|---|---|---|
| M1 | Tài khoản & phân quyền | Người dùng | 🟡 mới có cột mật khẩu | — |
| M2 | Chatbot tư vấn AI | Bệnh nhân | ✅ phần lõi, 🟡 tra ca bệnh / memory | [chat.md](../module/chat.md) |
| M3 | Clinical fact & báo cáo tiền tư vấn | Bệnh nhân → Bác sĩ | 🟡 mới có schema | — |
| M4 | Tư vấn trực tiếp với bác sĩ (chat / video) | Bệnh nhân, Bác sĩ | 🟡 mới có schema | — |
| M5 | Đặt lịch khám | Bệnh nhân, Bác sĩ | ⏸ hoãn (ngoài scope hiện tại) | — |
| M6 | Hồ sơ bệnh nhân & bệnh án | Bệnh nhân, Bác sĩ | 🟡 mới có schema (hồ sơ, bệnh án, ảnh) | — |
| M7 | Ca bệnh & ảnh đã xác nhận (dữ liệu CNN) | Bác sĩ | 🟡 mới có cột nhãn ảnh | — |
| M8 | Knowledge Graph | Bác sĩ, Chatbot | 🟡 agent tra được, chưa trực quan hoá | — |
| M9 | Quản lý Knowledge Base (tài liệu y khoa) | Bác sĩ (hiện là Admin) | 🟡 nạp sách PDF xong, chatbot chưa dùng | [book-ingest-pipeline.md](../module/book-ingest-pipeline.md) |

## 3. Chi tiết chức năng

### M1 — Tài khoản & phân quyền

| Mã | Chức năng | Trạng thái | Hiện trạng / việc cần làm |
|---|---|---|---|
| M1.1 | Đăng ký tài khoản | 🟡 | đã có `users.password_hash` (`User.password_hash`); chưa có API, user chỉ tạo qua `make init-db` (chưa đặt mật khẩu) |
| M1.2 | Đăng nhập / đăng xuất | 🔲 | hiện chỉ có app token chung (`APP_ACCESS_TOKEN`, `fe/app/access-gate.tsx`), không phải đăng nhập theo user |
| M1.3 | Quản lý tài khoản cá nhân (xem / sửa thông tin) | 🔲 | — |
| M1.4 | Phân quyền theo vai trò (bệnh nhân / bác sĩ / admin) | 🔲 | đã có bảng `doctors`, `admins` để gắn vai trò; API đang nhận `user_id` từ client |

### M2 — Chatbot tư vấn AI

| Mã | Chức năng | Trạng thái | Hiện trạng / việc cần làm |
|---|---|---|---|
| M2.1 | Hỏi đáp với chatbot, stream câu trả lời realtime | ✅ | Core → RabbitMQ → Agent Worker → Redis → SSE |
| M2.2 | Tạo / xem danh sách / xem lịch sử hội thoại | ✅ | `/conversations`, `/conversations/{id}/messages` |
| M2.3 | Gửi ảnh da, phân loại bằng CNN | ✅ | `POST /uploads` → MinIO; tool `classify_skin_image` (22 lớp, chỉ là giả thuyết) |
| M2.4 | Mô tả triệu chứng → gợi ý chẩn đoán phân biệt | ✅ | tool `describe_morphology`, `generate_differential`, `expand_entity_context` |
| M2.5 | Chatbot hỏi lại khi thiếu thông tin | ✅ | tool `ask_user` + `interrupt()`, trả lời qua `/questions/{id}/answer` |
| M2.6 | Hiển thị các bước lập luận / tool đã dùng | ✅ | event `message.thinking`, `message.tool_result`, lưu `metadata.reasoning` |
| M2.7 | Tra cứu thông tin bệnh lý từ KB | ✅ | guideline BYT / WHO / MedlinePlus (Qdrant), PrimeKG + DermO (Neo4j), web nguồn uy tín |
| M2.8 | Tra cứu **ca bệnh liên quan** | 🔲 | chưa có kho ca bệnh, phụ thuộc M7 |
| M2.9 | Chọn model LLM cho hội thoại | ✅ | `/models`, `PATCH /conversations/{id}/model` |
| M2.10 | Ghi nhớ thông tin bệnh nhân giữa các hội thoại | 🟡 | `save_memory` + `inject_long_term_memory` chạy được nhưng store in-memory, mất khi restart Worker |
| M2.11 | Trích dẫn nguồn (sources) cho câu trả lời | 🟡 | đã có `Source` (`dto/common/chat.py`, lưu trong `messages.metadata` JSON, không có bảng riêng); agent chưa sinh, `ChatSourceDto` trên wire chưa khớp `Source` |

### M3 — Clinical fact & báo cáo tiền tư vấn

| Mã | Chức năng | Trạng thái | Hiện trạng / việc cần làm |
|---|---|---|---|
| M3.1 | Trích **clinical fact** có cấu trúc từ hội thoại (triệu chứng, thời gian, vị trí, tiền sử, thuốc, dị ứng...) | 🟡 | đã có schema: `PatientProfile.clinical_facts` → bảng `clinical_facts` (`template_id` trỏ `clinical_fact_templates` giữ loại / nhãn / `ontology_id`; fact giữ chi tiết, trạng thái thay thế). Chưa có bước trích xuất |
| M3.2 | Mỗi clinical fact liên kết tới **tin nhắn nguồn** | 🟡 | đã có schema: `ClinicalFact.provenances[].message` (`ClinicalProvenance`) → bảng `clinical_provenances` |
| M3.3 | Sinh **báo cáo tổng hợp** trước khi bác sĩ tư vấn | 🟡 | đã có schema: `ConsultationSession.report` → bảng `pre_consultation_reports`. Chưa có bước sinh báo cáo; kích hoạt khi bệnh nhân yêu cầu tư vấn (M4.1) |
| M3.4 | Bác sĩ xem clinical fact, nguồn lập luận từ KB, mở tin nhắn nguồn | 🔲 | màn hình phía bác sĩ |

### M4 — Tư vấn trực tiếp với bác sĩ

| Mã | Chức năng | Trạng thái | Hiện trạng / việc cần làm |
|---|---|---|---|
| M4.1 | Bệnh nhân gửi yêu cầu tư vấn bác sĩ từ một hội thoại | 🟡 | đã có schema: bảng `consultation_sessions` (`pending → active → resolved`), tin mốc `consultation_requested`. Chưa có API / UI |
| M4.2 | Bác sĩ xem hàng đợi yêu cầu, nhận ca | 🟡 | schema có (`doctor_id`, tin mốc `consultation_accepted`); chưa có API / UI |
| M4.3 | Bác sĩ và bệnh nhân chat trực tiếp trong cùng hội thoại | 🟡 | `messages.sender` đã có `doctor`; chưa có API gửi tin của bác sĩ, chưa có kênh realtime cho tin người-người |
| M4.4 | Bác sĩ chưa nhận thì bệnh nhân vẫn hỏi chatbot | 🔲 | cần quy tắc: khi phiên `active` thì agent dừng / chỉ hỗ trợ, khi `pending` thì agent vẫn trả lời |
| M4.5 | Video call | 🟡 | bảng `video_calls` (thuộc `consultation_sessions`, entity `ConsultationSession.video_calls`) + tin `message_type="video_call"`; chưa chọn công nghệ (WebRTC / dịch vụ ngoài), chưa có API / UI |
| M4.6 | Bác sĩ đóng ca tư vấn | 🟡 | schema có (`resolved`, tin mốc `consultation_resolved`); chưa có API / UI |

### M5 — Đặt lịch khám

| Mã | Chức năng | Trạng thái | Hiện trạng / việc cần làm |
|---|---|---|---|
| M5.1 | Bác sĩ khai báo lịch làm việc / khung giờ trống | ⏸ | hoãn: ngoài scope đồ án hiện tại, chưa có entity |
| M5.2 | Bệnh nhân đặt lịch khám | ⏸ | hoãn |
| M5.3 | Xem / huỷ / đổi lịch (cả hai phía) | ⏸ | hoãn |

### M6 — Hồ sơ bệnh nhân & bệnh án

| Mã | Chức năng | Trạng thái | Hiện trạng / việc cần làm |
|---|---|---|---|
| M6.1 | Quản lý hồ sơ bệnh nhân (một tài khoản nhiều hồ sơ, ví dụ cho người nhà) | 🟡 | bảng `patient_profiles` có, seed sẵn; tạo hội thoại bắt buộc có hồ sơ. Chưa có API CRUD / UI |
| M6.2 | Bệnh án / lịch sử khám | 🟡 | đã có schema: `PatientProfile.medical_records` → bảng `medical_records` (bác sĩ ghi, gắn phiên tư vấn), ảnh bệnh trong `patient_images`. Chưa có API / UI |
| M6.3 | Thư viện ảnh bệnh đã lưu của bệnh nhân | 🟡 | ảnh chat nằm trong `files` + `message_files`; ảnh đã gắn bệnh án nằm trong `patient_images`. Chưa có màn xem tập trung |
| M6.4 | Bác sĩ xem hồ sơ + lịch sử bệnh án của bệnh nhân | 🔲 | phụ thuộc M1.4, M6.2 |
| M6.5 | Bác sĩ cập nhật hồ sơ / bệnh án sau mỗi lượt khám | 🔲 | phụ thuộc M6.2 |

### M7 — Ca bệnh & ảnh đã xác nhận

| Mã | Chức năng | Trạng thái | Hiện trạng / việc cần làm |
|---|---|---|---|
| M7.1 | Bác sĩ lưu ca bệnh (chẩn đoán đã xác nhận + ảnh + mô tả) | 🟡 | đã có schema: cờ `medical_records.is_reference_case` trên bệnh án; chưa có API / UI |
| M7.2 | Xác nhận / gán nhãn ảnh để làm dữ liệu huấn luyện CNN | 🟡 | đã có cột `patient_images.confirmed_label`; nhãn nên khớp 22 lớp hiện tại của CNN. Chưa có API / UI |
| M7.3 | Ca bệnh đã xác nhận được nạp vào KB để chatbot tra (cho M2.8) | 🔲 | — |

### M8 — Knowledge Graph

| Mã | Chức năng | Trạng thái | Hiện trạng / việc cần làm |
|---|---|---|---|
| M8.1 | KG da liễu (bệnh – triệu chứng – thuốc – gen) và ontology thuật ngữ | ✅ | PrimeKG lọc da liễu + DermO trong Neo4j, nạp từ `core/data_ingest/` |
| M8.2 | Chatbot truy vấn KG | ✅ | `query_dermatology_kg`, `lookup_dermo_term`, `ground_medical_entities` |
| M8.3 | **Trực quan hoá** KG liên quan đến bệnh nhân | 🔲 | cần API trả subgraph quanh các thực thể của bệnh nhân (từ clinical fact M3.1) + thư viện vẽ graph ở FE |

### M9 — Quản lý Knowledge Base

| Mã | Chức năng | Trạng thái | Hiện trạng / việc cần làm |
|---|---|---|---|
| M9.1 | Tải lên giáo trình PDF, số hoá theo mục lục, nạp Qdrant | ✅ | `/admin/documents`, 4 bước `ingest → toc → chunks → index`, có người duyệt |
| M9.2 | Tải lên guideline / tài liệu y khoa dạng khác | 🟡 | guideline hiện nạp bằng script (`data_ingest/`); pipeline chỉ nhận `type="book"` |
| M9.3 | Chatbot tra cứu tài liệu đã nạp | 🔲 | chưa có tool đọc collection `derma_document_chunks` |
| M9.4 | Phối hợp chatbot để làm giàu KB (gợi ý / bổ sung tri thức) | ⏸ | chưa chốt luồng — đề xuất ở [docs/pending/kb-enrichment.md](../pending/kb-enrichment.md) |
| M9.5 | Quyền tải tài liệu dành cho bác sĩ | 🟡 | đã có `documents.uploaded_by_id` → `doctors` (`Document.uploaded_by: Doctor`); khu admin vẫn chỉ dùng app token, phụ thuộc M1.4 |

## 4. Gợi ý thứ tự làm và chia việc

Các module có phụ thuộc, nên làm theo thứ tự sau để mỗi bước demo được:

| Đợt | Việc | Lý do |
|---|---|---|
| 1 | **M1** (đăng nhập + vai trò), **M6.1** (API hồ sơ bệnh nhân) | mọi màn hình bác sĩ / bệnh nhân đều cần biết ai đang đăng nhập |
| 2 | **M9.3** (tool tra chunk sách), **M2.11** (sources) | công sức thấp, dùng ngay được dữ liệu đã có |
| 3 | **M3.1–M3.3** (clinical fact + báo cáo) | đầu vào cho màn bác sĩ và trực quan hoá KG |
| 4 | **M4.1–M4.4, M4.6** (tư vấn qua chat), **M3.4** (màn bác sĩ xem báo cáo) | luồng chính bệnh nhân ↔ bác sĩ |
| 5 | **M6.2–M6.5** (bệnh án), **M7** (ca bệnh), **M2.8** | cần bác sĩ đã dùng được hệ thống |
| 6 | **M8.3** (trực quan hoá KG), **M4.5** (video call), **M9.4** | tính năng mở rộng |
| — | **M5** (đặt lịch) | hoãn, ngoài scope đồ án hiện tại |

Có thể giao song song theo 3 nhánh ít đụng nhau:
- **Nhánh nền tảng (BE + FE)**: M1, M6.
- **Nhánh AI / agent**: M2.8, M2.10, M2.11, M3.1–M3.3, M9.3, M9.4.
- **Nhánh tư vấn bác sĩ (BE + FE)**: M4, M3.4, M7, M8.3.

Quy trình thêm một nghiệp vụ mới: entity `dto/base` (**hỏi duyệt trước**) → model + migration → repository →
service → endpoint → màn hình FE. Quy ước chi tiết trong các skill ở `.claude/skills/`.
