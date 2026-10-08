/**
 * Mock data cho màn hình bác sĩ — dùng để phát triển UI trước khi backend
 * consultation API sẵn sàng. Dữ liệu mô phỏng đúng schema thật.
 */
import type {
  ConsultationSession,
  DoctorViewMessage,
} from "./types";

/* ────────── Mock Consultation Sessions ────────── */

export const MOCK_SESSIONS: ConsultationSession[] = [
  {
    id: "cs-001",
    conversationId: "conv-001",
    conversationTitle: "Nổi mẩn đỏ ngứa sau khi dùng thuốc",
    patient: {
      id: "pp-001",
      fullName: "Nguyễn Văn An",
      dob: "1990-05-12",
      gender: "male",
    },
    doctorId: null,
    status: "pending",
    reason: "Bệnh nhân muốn được bác sĩ tư vấn thêm về tình trạng nổi mẩn đỏ sau dùng thuốc kháng sinh.",
    requestedAt: "2026-10-07T09:15:00Z",
    startedAt: null,
    resolvedAt: null,
    report: {
      id: "rpt-001",
      summary: `## Tóm tắt tình trạng

Bệnh nhân nam, 36 tuổi, xuất hiện **mẩn đỏ ngứa lan rộng** trên cánh tay và thân mình sau 3 ngày sử dụng Amoxicillin 500mg (3 lần/ngày) để điều trị viêm họng.

### Triệu chứng chính
- Mẩn đỏ dạng sẩn, kích thước 2–5mm, rải rác cánh tay và bụng
- Ngứa mức độ trung bình, tăng về đêm
- Không sốt, không phù mạch, không khó thở

### Tiền sử liên quan
- Lần đầu sử dụng Amoxicillin
- Tiền sử dị ứng: **Chưa ghi nhận** dị ứng thuốc trước đó
- Không có tiền sử hen phế quản hay viêm da cơ địa

### Đánh giá sơ bộ (AI)
Nghi ngờ **phản ứng dị ứng thuốc dạng ban sẩn** (maculopapular drug eruption) liên quan đến Amoxicillin. Mức độ nhẹ – trung bình, chưa có dấu hiệu phản ứng toàn thân nặng.

### Đề xuất hướng xử trí
1. Ngưng Amoxicillin và thay thế kháng sinh nhóm khác (nếu cần tiếp tục điều trị viêm họng)
2. Kháng histamin đường uống (Cetirizine 10mg/ngày)
3. Theo dõi tiến triển trong 48–72 giờ
4. Tái khám nếu tổn thương lan rộng hoặc xuất hiện triệu chứng toàn thân`,
      createdAt: "2026-10-07T09:16:00Z",
    },
    clinicalFacts: [
      {
        id: "cf-001",
        templateLabel: "Mẩn đỏ / Ban sẩn",
        factType: "lesion",
        detail: "Sẩn đỏ 2–5mm, rải rác cánh tay và bụng, xuất hiện sau 3 ngày dùng Amoxicillin",
        status: "active",
        createdAt: "2026-10-07T09:16:00Z",
      },
      {
        id: "cf-002",
        templateLabel: "Ngứa",
        factType: "symptom",
        detail: "Ngứa mức độ trung bình, tăng về đêm, kèm theo mẩn đỏ",
        status: "active",
        createdAt: "2026-10-07T09:16:00Z",
      },
      {
        id: "cf-003",
        templateLabel: "Dùng thuốc Amoxicillin",
        factType: "medication",
        detail: "Amoxicillin 500mg x 3 lần/ngày, bắt đầu 3 ngày trước, điều trị viêm họng",
        status: "active",
        createdAt: "2026-10-07T09:16:00Z",
      },
      {
        id: "cf-004",
        templateLabel: "Không tiền sử dị ứng",
        factType: "history",
        detail: "Chưa ghi nhận dị ứng thuốc, không hen, không viêm da cơ địa",
        status: "active",
        createdAt: "2026-10-07T09:16:00Z",
      },
    ],
  },
  {
    id: "cs-002",
    conversationId: "conv-002",
    conversationTitle: "Nấm da bàn chân tái phát",
    patient: {
      id: "pp-002",
      fullName: "Trần Thị Bích",
      dob: "1985-11-23",
      gender: "female",
    },
    doctorId: "doc-001",
    status: "active",
    reason: "Nấm da bàn chân tái phát nhiều lần, đã dùng nhiều loại kem bôi nhưng không khỏi hẳn.",
    requestedAt: "2026-10-07T08:30:00Z",
    startedAt: "2026-10-07T08:45:00Z",
    resolvedAt: null,
    report: {
      id: "rpt-002",
      summary: `## Tóm tắt tình trạng

Bệnh nhân nữ, 41 tuổi, nấm da bàn chân **tái phát lần thứ 4** trong 2 năm qua. Đã tự mua Clotrimazole cream bôi nhưng chỉ đỡ tạm thời.

### Triệu chứng chính
- Bong tróc da kẽ ngón chân (kẽ 3–4 và 4–5)
- Ngứa ngáy, có mùi hôi nhẹ
- Da ướt, nứt nẻ kẽ ngón

### Tiền sử liên quan
- Tái phát 4 lần / 2 năm
- Đã dùng: Clotrimazole cream 1%, Ketoconazole cream
- Nghề nghiệp: công nhân, mang giày kín thường xuyên
- Không tiểu đường, không suy giảm miễn dịch

### Đánh giá sơ bộ (AI)
**Tinea pedis thể kẽ ngón** (interdigital), tái phát do yếu tố nguy cơ (giày kín, ẩm ướt) chưa được kiểm soát. Có thể cần điều trị toàn thân nếu bôi tại chỗ thất bại.

### Đề xuất hướng xử trí
1. Xét nghiệm KOH / nuôi cấy nấm xác nhận chẩn đoán
2. Terbinafine cream 1% × 2 tuần hoặc Terbinafine uống 250mg/ngày × 2–4 tuần
3. Giữ chân khô, đổi tất thường xuyên, dùng giày thoáng khí
4. Bột chống nấm dự phòng sau điều trị`,
      createdAt: "2026-10-07T08:31:00Z",
    },
    clinicalFacts: [
      {
        id: "cf-005",
        templateLabel: "Bong tróc da",
        factType: "lesion",
        detail: "Bong tróc kẽ ngón 3–4 và 4–5, da ướt, nứt nẻ",
        status: "active",
        createdAt: "2026-10-07T08:31:00Z",
      },
      {
        id: "cf-006",
        templateLabel: "Ngứa",
        factType: "symptom",
        detail: "Ngứa kẽ ngón chân, kèm mùi hôi nhẹ",
        status: "active",
        createdAt: "2026-10-07T08:31:00Z",
      },
      {
        id: "cf-007",
        templateLabel: "Tiền sử tái phát",
        factType: "history",
        detail: "Nấm da tái phát 4 lần trong 2 năm, đã dùng Clotrimazole và Ketoconazole",
        status: "active",
        createdAt: "2026-10-07T08:31:00Z",
      },
      {
        id: "cf-008",
        templateLabel: "Dùng thuốc kháng nấm",
        factType: "medication",
        detail: "Clotrimazole cream 1%, Ketoconazole cream – chỉ đỡ tạm thời",
        status: "active",
        createdAt: "2026-10-07T08:31:00Z",
      },
    ],
  },
  {
    id: "cs-003",
    conversationId: "conv-003",
    conversationTitle: "Vết bớt sắc tố bất thường",
    patient: {
      id: "pp-003",
      fullName: "Lê Minh Tuấn",
      dob: "1978-03-08",
      gender: "male",
    },
    doctorId: "doc-001",
    status: "resolved",
    reason: "Vết bớt sắc tố thay đổi kích thước và màu sắc, lo ngại ác tính.",
    requestedAt: "2026-10-06T14:00:00Z",
    startedAt: "2026-10-06T14:20:00Z",
    resolvedAt: "2026-10-06T15:10:00Z",
    report: {
      id: "rpt-003",
      summary: `## Tóm tắt tình trạng

Bệnh nhân nam, 48 tuổi, phát hiện **nốt ruồi/bớt sắc tố thay đổi** ở lưng trên trong 6 tháng qua.

### Triệu chứng chính
- Nốt sắc tố đường kính ~8mm, bờ không đều
- Thay đổi màu sắc: từ nâu đều sang nâu đen không đồng nhất
- Tăng kích thước khoảng 2mm trong 6 tháng
- Không ngứa, không đau, không chảy máu

### Đánh giá theo tiêu chí ABCDE
- **A** (Asymmetry): Bất đối xứng
- **B** (Border): Bờ không đều
- **C** (Color): Đa sắc (nâu, nâu đen)
- **D** (Diameter): 8mm (>6mm)
- **E** (Evolution): Thay đổi kích thước và màu sắc

### Đề xuất hướng xử trí
1. **Sinh thiết cắt trọn** (excisional biopsy) để mô bệnh học
2. Không trì hoãn — chuyển chuyên khoa da liễu hoặc ung thư da
3. Chụp dermoscopy nếu có điều kiện trước sinh thiết`,
      createdAt: "2026-10-06T14:01:00Z",
    },
    clinicalFacts: [
      {
        id: "cf-009",
        templateLabel: "Tổn thương sắc tố",
        factType: "lesion",
        detail: "Nốt sắc tố 8mm, bờ không đều, đa sắc, lưng trên",
        status: "active",
        createdAt: "2026-10-06T14:01:00Z",
      },
      {
        id: "cf-010",
        templateLabel: "Thay đổi kích thước",
        factType: "symptom",
        detail: "Tăng 2mm trong 6 tháng, đổi màu từ nâu đều sang nâu đen không đồng nhất",
        status: "active",
        createdAt: "2026-10-06T14:01:00Z",
      },
    ],
  },
];

/* ────────── Mock Messages cho conversation conv-001 ────────── */

export const MOCK_MESSAGES: Record<string, DoctorViewMessage[]> = {
  "conv-001": [
    {
      id: "msg-001",
      sender: "patient",
      content: "Chào bác sĩ AI, tôi bị nổi mẩn đỏ ngứa trên tay và bụng sau khi uống thuốc kháng sinh được 3 ngày.",
      messageType: "text",
      createdAt: "2026-10-07T09:00:00Z",
    },
    {
      id: "msg-002",
      sender: "ai",
      content: "Chào bạn, tôi sẽ giúp bạn tìm hiểu về tình trạng này. Bạn đang uống thuốc kháng sinh gì và liều lượng như thế nào ạ?",
      messageType: "text",
      createdAt: "2026-10-07T09:00:30Z",
    },
    {
      id: "msg-003",
      sender: "patient",
      content: "Tôi uống Amoxicillin 500mg, ngày 3 lần, để trị viêm họng.",
      messageType: "text",
      createdAt: "2026-10-07T09:01:00Z",
    },
    {
      id: "msg-004",
      sender: "ai",
      content: "Cảm ơn bạn đã chia sẻ. Mẩn đỏ có dạng như thế nào — là các nốt nhỏ sần hay là mảng đỏ phẳng? Kích thước khoảng bao nhiêu?",
      messageType: "text",
      createdAt: "2026-10-07T09:01:30Z",
    },
    {
      id: "msg-005",
      sender: "patient",
      content: "Là các nốt nhỏ sần, kích thước khoảng 2–5mm, rải rác trên cánh tay và bụng. Ngứa nhiều hơn vào buổi tối.",
      messageType: "text",
      createdAt: "2026-10-07T09:02:00Z",
    },
    {
      id: "msg-006",
      sender: "ai",
      content: "Bạn có bị sốt, phù mặt/môi, hoặc khó thở không? Trước đây bạn đã từng sử dụng Amoxicillin hoặc nhóm Penicillin chưa?",
      messageType: "text",
      createdAt: "2026-10-07T09:02:30Z",
    },
    {
      id: "msg-007",
      sender: "patient",
      content: "Không sốt, không khó thở, không phù. Đây là lần đầu tiên tôi uống Amoxicillin. Tôi cũng chưa từng bị dị ứng gì cả.",
      messageType: "text",
      createdAt: "2026-10-07T09:03:00Z",
    },
    {
      id: "msg-008",
      sender: "ai",
      content: "Dựa trên thông tin bạn cung cấp, tình trạng của bạn có nhiều khả năng là **phản ứng dị ứng thuốc dạng ban sẩn** (maculopapular drug eruption) liên quan đến Amoxicillin. Đây là loại phản ứng dị ứng thuốc phổ biến nhất, thường xuất hiện sau 3–14 ngày dùng thuốc.\n\nTôi khuyên bạn nên:\n1. **Ngưng Amoxicillin** và thông báo cho bác sĩ đã kê đơn\n2. Uống thuốc kháng histamin như Cetirizine 10mg/ngày để giảm ngứa\n3. Theo dõi trong 48–72 giờ\n\nBạn có muốn tôi chuyển ca cho bác sĩ tư vấn trực tiếp không?",
      messageType: "text",
      createdAt: "2026-10-07T09:04:00Z",
    },
    {
      id: "msg-009",
      sender: "patient",
      content: "Vâng, tôi muốn được bác sĩ thật tư vấn thêm ạ.",
      messageType: "text",
      createdAt: "2026-10-07T09:14:00Z",
    },
    {
      id: "msg-010",
      sender: "ai",
      content: "Tôi đã gửi yêu cầu tư vấn cho bác sĩ. Bác sĩ sẽ xem lại toàn bộ cuộc hội thoại và báo cáo phân tích của tôi để hỗ trợ bạn tốt nhất. Vui lòng chờ trong giây lát.",
      messageType: "consultation_requested",
      createdAt: "2026-10-07T09:15:00Z",
    },
  ],
  "conv-002": [
    {
      id: "msg-011",
      sender: "patient",
      content: "Chào AI, tôi bị nấm da bàn chân tái đi tái lại hoài, đã bôi nhiều loại kem mà không khỏi hẳn.",
      messageType: "text",
      createdAt: "2026-10-07T08:00:00Z",
    },
    {
      id: "msg-012",
      sender: "ai",
      content: "Chào bạn, nấm da tái phát là tình trạng khá phổ biến. Bạn có thể mô tả chi tiết hơn về vị trí tổn thương và các loại kem đã sử dụng không?",
      messageType: "text",
      createdAt: "2026-10-07T08:00:30Z",
    },
    {
      id: "msg-013",
      sender: "patient",
      content: "Tổn thương ở kẽ ngón chân 3–4 và 4–5, bong tróc da, ướt và nứt nẻ. Tôi đã dùng Clotrimazole cream và Ketoconazole cream nhưng chỉ đỡ tạm thời.",
      messageType: "text",
      createdAt: "2026-10-07T08:01:00Z",
    },
    {
      id: "msg-014",
      sender: "ai",
      content: "Bạn có ngứa không? Công việc của bạn có phải mang giày kín thường xuyên không? Bạn có tiền sử tiểu đường hoặc bệnh lý miễn dịch gì không?",
      messageType: "text",
      createdAt: "2026-10-07T08:01:30Z",
    },
    {
      id: "msg-015",
      sender: "patient",
      content: "Có ngứa và hôi nhẹ. Tôi là công nhân, mang giày kín cả ngày. Không bị tiểu đường hay bệnh gì khác.",
      messageType: "text",
      createdAt: "2026-10-07T08:02:00Z",
    },
    {
      id: "msg-016",
      sender: "ai",
      content: "Tình trạng của bạn rất phù hợp với **Tinea pedis thể kẽ ngón** (nấm kẽ chân). Việc tái phát nhiều lần có thể do:\n- Giày kín tạo môi trường ẩm ướt\n- Thời gian điều trị chưa đủ\n- Chưa phòng ngừa sau điều trị\n\nBạn có muốn được bác sĩ da liễu tư vấn trực tiếp để có phác đồ điều trị triệt để hơn không?",
      messageType: "text",
      createdAt: "2026-10-07T08:03:00Z",
    },
    {
      id: "msg-017",
      sender: "patient",
      content: "Có, tôi muốn gặp bác sĩ để được tư vấn kỹ hơn.",
      messageType: "text",
      createdAt: "2026-10-07T08:29:00Z",
    },
  ],
  "conv-003": [
    {
      id: "msg-018",
      sender: "patient",
      content: "Tôi có một nốt ruồi ở lưng mà gần đây thấy to ra và đổi màu, tôi lo lắng quá.",
      messageType: "text",
      createdAt: "2026-10-06T13:45:00Z",
    },
    {
      id: "msg-019",
      sender: "ai",
      content: "Tôi hiểu sự lo lắng của bạn. Thay đổi ở nốt ruồi cần được đánh giá cẩn thận. Bạn có thể cho tôi biết:\n- Nốt ruồi ở vị trí nào trên lưng?\n- Kích thước hiện tại khoảng bao nhiêu?\n- Thay đổi trong bao lâu?",
      messageType: "text",
      createdAt: "2026-10-06T13:45:30Z",
    },
    {
      id: "msg-020",
      sender: "patient",
      content: "Ở lưng trên, bên phải. Khoảng 8mm. Trong 6 tháng qua nó to thêm khoảng 2mm và đổi từ màu nâu đều sang nâu đen loang lổ.",
      messageType: "text",
      createdAt: "2026-10-06T13:46:00Z",
    },
    {
      id: "msg-021",
      sender: "ai",
      content: "Cảm ơn bạn. Tôi cần hỏi thêm: nốt ruồi có bờ đều hay không đều? Có đối xứng không? Có ngứa, đau, hoặc chảy máu không?",
      messageType: "text",
      createdAt: "2026-10-06T13:46:30Z",
    },
    {
      id: "msg-022",
      sender: "patient",
      content: "Bờ không đều, hình dạng không đối xứng. Không ngứa, không đau, không chảy máu.",
      messageType: "text",
      createdAt: "2026-10-06T13:47:00Z",
    },
    {
      id: "msg-023",
      sender: "ai",
      content: "Theo tiêu chí ABCDE, tổn thương của bạn có **nhiều yếu tố cần lưu ý**:\n- Bất đối xứng\n- Bờ không đều\n- Đa sắc\n- Đường kính > 6mm\n- Thay đổi theo thời gian\n\n**Tôi khuyến nghị bạn nên gặp bác sĩ da liễu sớm nhất có thể để sinh thiết đánh giá.** Đây không nhất thiết là ung thư, nhưng cần được kiểm tra chuyên khoa. Tôi sẽ chuyển ca cho bác sĩ ngay.",
      messageType: "text",
      createdAt: "2026-10-06T13:48:00Z",
    },
  ],
};
