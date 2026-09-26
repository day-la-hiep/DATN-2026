# who — WHO fact sheets & báo cáo

12 bệnh da liễu / bệnh nhiệt đới có biểu hiện ngoài da, tóm tắt từ trang fact sheet của WHO
(leprosy, scabies, mycetoma, yaws, chromoblastomycosis, psoriasis, cutaneous leishmaniasis, Buruli ulcer,
lymphatic filariasis, podoconiosis, noma, mpox).

| | |
|---|---|
| Input | trang WHO (URL + ngày truy cập ghi ở `core/knowledge_base/knowledge_base/sources.json`, `accessed_at`) |
| Scripts | không có — biên soạn tay |
| Output | `output/who_skin_diseases.json` — 12 bệnh, schema như `byt` (xem `../byt/README.md`) |

`id` có hậu tố `_who` (vd `benh_phong_who`) để không trùng id BYT — `01_normalize_diseases.py` kiểm tra id duy nhất giữa các nguồn.
Trạng thái duyệt: `needs_manual_verification`.
