import type { Conversation, ChatMessage } from "@/features/chat/types";

export const now = () => new Date().toISOString();

export const delay = (ms: number) =>
  new Promise((resolve) => setTimeout(resolve, ms));

export interface SeedConversation extends Conversation {
  messages: ChatMessage[];
}

export const seedConversations: SeedConversation[] = [
  {
    id: "conv-1",
    title: "Chăm sóc da mụn trứng cá",
    createdAt: "2026-08-19T09:00:00.000Z",
    updatedAt: "2026-08-19T09:05:00.000Z",
    messages: [
      {
        id: "msg-1-1",
        conversationId: "conv-1",
        role: "user",
        content:
          "Em 17 tuổi, da mặt nhiều mụn viêm ở má và cằm, nên dùng thuốc gì và chăm sóc thế nào?",
        createdAt: "2026-08-19T09:00:00.000Z",
        status: "done",
      },
      {
        id: "msg-1-2",
        conversationId: "conv-1",
        role: "assistant",
        content:
          "Theo Hướng dẫn điều trị mụn trứng cá, trường hợp mụn viêm mức độ trung bình nên phối hợp:\n\n1. **Retinoid bôi** (adapalene 0,1%) bôi toàn mặt buổi tối, bắt đầu cách ngày để da quen.\n2. **Benzoyl peroxide 2,5–5%** buổi sáng hoặc kháng sinh bôi (clindamycin) lên vùng mụn viêm.\n3. Nếu sau 6–8 tuần chưa cải thiện, bác sĩ da liễu có thể cân nhắc **doxycycline đường uống** tối đa 3 tháng, luôn kèm thuốc bôi.\n\nChăm sóc hằng ngày: sữa rửa mặt dịu nhẹ 2 lần/ngày, kem dưỡng ẩm non-comedogenic, chống nắng SPF ≥ 30 mỗi sáng. **Không tự ý nặn mụn** và hạn chế sản phẩm chứa cồn, tẩy tế bào chết mạnh.",
        reasoning: [
          {
            id: "r-1-2-1",
            title: "Nhận diện vấn đề",
            content:
              "Mụn viêm ở má và cằm tuổi dậy thì — cần đánh giá mức độ để chọn phác đồ thuốc bôi hoặc phối hợp thuốc uống.",
            status: "done",
          },
          {
            id: "r-1-2-2",
            title: "Đối chiếu hướng dẫn chuyên môn",
            content:
              "Hướng dẫn điều trị mụn trứng cá khuyến cáo mụn viêm trung bình dùng retinoid bôi + benzoyl peroxide/kháng sinh bôi, cân nhắc kháng sinh uống nếu đáp ứng kém.",
            status: "done",
          },
          {
            id: "r-1-2-3",
            title: "Lưu ý chăm sóc và an toàn",
            content:
              "Dưỡng ẩm, chống nắng, tránh nặn mụn; retinoid gây khô, kích ứng nhẹ giai đoạn đầu nên khởi đầu cách ngày.",
            status: "done",
          },
        ],
        createdAt: "2026-08-19T09:00:30.000Z",
        status: "done",
      },
      {
        id: "msg-1-3",
        conversationId: "conv-1",
        role: "user",
        content: "Bôi retinoid bị bong tróc và đỏ da thì có nên ngưng không?",
        createdAt: "2026-08-19T09:04:00.000Z",
        status: "done",
      },
      {
        id: "msg-1-4",
        conversationId: "conv-1",
        role: "assistant",
        content:
          "Bong tróc, đỏ nhẹ trong 2–4 tuần đầu là phản ứng thường gặp, **không cần ngưng hẳn**. Bạn nên:\n\n- Giảm tần suất xuống 2–3 lần/tuần rồi tăng dần khi da quen.\n- Dùng lượng bằng hạt đậu cho cả mặt, bôi lên da khô, có thể dưỡng ẩm trước 10–15 phút (kỹ thuật \"sandwich\").\n- Tăng cường dưỡng ẩm phục hồi và chống nắng ban ngày.\n\nNgưng thuốc và đi khám nếu da **đỏ rát nhiều, sưng, rỉ dịch hoặc nổi mụn nước** — có thể là viêm da kích ứng nặng.",
        reasoning: [
          {
            id: "r-1-4-1",
            title: "Đánh giá phản ứng của da",
            content:
              "Bong tróc và đỏ nhẹ giai đoạn đầu khi dùng retinoid là hiện tượng thích nghi, thường tự giảm sau vài tuần.",
            status: "done",
          },
          {
            id: "r-1-4-2",
            title: "Điều chỉnh cách dùng",
            content:
              "Giảm tần suất, dùng lượng nhỏ, phối hợp dưỡng ẩm; chỉ ngưng khi có dấu hiệu viêm da kích ứng nặng.",
            status: "done",
          },
        ],
        createdAt: "2026-08-19T09:05:00.000Z",
        status: "done",
      },
    ],
  },
  {
    id: "conv-2",
    title: "Phác đồ điều trị viêm da cơ địa",
    createdAt: "2026-08-18T15:20:00.000Z",
    updatedAt: "2026-08-18T15:22:00.000Z",
    messages: [
      {
        id: "msg-2-1",
        conversationId: "conv-2",
        role: "user",
        content: "Con em 3 tuổi bị viêm da cơ địa, hay ngứa gãi về đêm, nên điều trị và chăm sóc thế nào?",
        createdAt: "2026-08-18T15:20:00.000Z",
        status: "done",
      },
      {
        id: "msg-2-2",
        conversationId: "conv-2",
        role: "assistant",
        content:
          "Với viêm da cơ địa ở trẻ, nền tảng là phục hồi hàng rào da và kiểm soát viêm:\n\n1. **Dưỡng ẩm** ngày 2–3 lần, bôi ngay trong 3 phút sau khi tắm; chọn loại không mùi, dịu nhẹ.\n2. **Tắm** nước ấm ≤ 10 phút, sữa tắm dịu nhẹ, không chà xát; lau khô nhẹ rồi bôi dưỡng ẩm.\n3. **Đợt bùng phát**: corticoid bôi hoạt lực thấp cho mặt và nếp gấp, dùng ngắn ngày theo chỉ định; vùng da mỏng cân nhắc tacrolimus/pimecrolimus.\n4. **Giảm ngứa đêm**: kháng histamine đường uống theo cân nặng, cắt móng tay, cho bé mặc đồ cotton mềm.\n\nTránh len dạ, xà phòng kiềm mạnh, nóng ẩm ra mồ hôi nhiều. Nên cho bé khám bác sĩ da liễu để kê corticoid phù hợp và theo dõi.",
        reasoning: [
          {
            id: "r-2-2-1",
            title: "Nhận diện vấn đề",
            content:
              "Viêm da cơ địa ở trẻ nhỏ kèm ngứa về đêm — cần chăm sóc hàng rào da, kiểm soát viêm và giảm ngứa an toàn theo tuổi.",
            status: "done",
          },
          {
            id: "r-2-2-2",
            title: "Đối chiếu hướng dẫn chuyên môn",
            content:
              "Hướng dẫn điều trị viêm da cơ địa: dưỡng ẩm là nền tảng; corticoid bôi hoạt lực thấp cho trẻ, ngắn ngày; ức chế calcineurin cho vùng da mỏng.",
            status: "done",
          },
          {
            id: "r-2-2-3",
            title: "Lưu ý an toàn cho trẻ",
            content:
              "Ưu tiên corticoid hoạt lực thấp, thời gian ngắn, theo dõi bởi bác sĩ; tránh yếu tố kích ứng và cắt móng tay để hạn chế cào gãi.",
            status: "done",
          },
        ],
        createdAt: "2026-08-18T15:22:00.000Z",
        status: "done",
      },
    ],
  },
  {
    id: "conv-3",
    title: "Điều trị nám má sau sinh",
    createdAt: "2026-08-17T10:00:00.000Z",
    updatedAt: "2026-08-17T10:02:00.000Z",
    messages: [
      {
        id: "msg-3-1",
        conversationId: "conv-3",
        role: "user",
        content: "Em sinh xong 6 tháng, hai bên gò má bị nám sạm lên nhiều, đang cho con bú thì trị được không?",
        createdAt: "2026-08-17T10:00:00.000Z",
        status: "done",
      },
      {
        id: "msg-3-2",
        conversationId: "conv-3",
        role: "assistant",
        content:
          "Đang cho con bú vẫn có thể xử lý nám má, nhưng cần chọn phương pháp an toàn:\n\n**Bắt buộc – chống nắng:**\n- Kem chống nắng phổ rộng SPF ≥ 50, PA++++, thoa lại mỗi 2–3 giờ khi ra ngoài.\n- Che chắn vật lý: mũ rộng vành, khẩu trang; hạn chế nắng gắt 10–16 giờ.\n\n**Thuốc bôi phù hợp giai đoạn cho con bú:**\n- Azelaic acid, vitamin C, niacinamide — được ưu tiên.\n- **Trì hoãn hydroquinone, retinoid bôi và laser** cho tới khi ngừng cho bú và tình trạng ổn định.\n\nNám sau sinh thường cải thiện dần khi nội tiết trở lại bình thường. Bạn nên khám bác sĩ da liễu để xác định nám thượng bì hay trung bì trước khi chọn phác đồ lâu dài.",
        reasoning: [
          {
            id: "r-3-2-1",
            title: "Nhận diện vấn đề",
            content:
              "Nám má xuất hiện/nặng lên sau sinh, người bệnh đang cho con bú — cần loại trừ các hoạt chất và thủ thuật chống chỉ định.",
            status: "done",
          },
          {
            id: "r-3-2-2",
            title: "Đối chiếu hướng dẫn chuyên môn",
            content:
              "Hướng dẫn điều trị nám má: chống nắng là nền tảng; giai đoạn cho con bú ưu tiên azelaic acid, vitamin C; trì hoãn hydroquinone và laser.",
            status: "done",
          },
          {
            id: "r-3-2-3",
            title: "Tiên lượng và hướng theo dõi",
            content:
              "Nám sau sinh thường mờ dần theo thời gian khi nội tiết ổn định; nên khám để phân loại nám trước khi điều trị chuyên sâu.",
            status: "done",
          },
        ],
        createdAt: "2026-08-17T10:02:00.000Z",
        status: "done",
      },
    ],
  },
  {
    id: "conv-4",
    title: "Tư vấn nấm da chân",
    createdAt: "2026-08-16T14:00:00.000Z",
    updatedAt: "2026-08-16T14:07:00.000Z",
    messages: [
      {
        id: "msg-4-1",
        conversationId: "conv-4",
        role: "user",
        content: "Chân em bị ngứa, bong da và nứt kẽ ngón đã hơn một tháng, dùng thuốc gì?",
        createdAt: "2026-08-16T14:00:00.000Z",
        status: "done",
      },
      {
        id: "msg-4-2",
        conversationId: "conv-4",
        role: "assistant",
        content: "Bạn muốn tôi tư vấn khía cạnh nào khi điều trị nấm da chân?",
        reasoning: [
          {
            id: "r-4-2-1",
            title: "Nhận diện vấn đề",
            content:
              "Ngứa, bong da, nứt kẽ ngón chân kéo dài — hướng nhiều đến nấm bàn chân; cần làm rõ mong muốn của người bệnh để tư vấn trọng tâm.",
            status: "done",
          },
          {
            id: "r-4-2-2",
            title: "Đặt câu hỏi làm rõ",
            content:
              "Đưa ra các lựa chọn về thuốc bôi, thuốc uống, phòng tái phát và nấm móng đi kèm.",
            status: "done",
          },
        ],
        choice: {
          questionId: "q-namda-demo",
          question: "Bạn muốn tôi tư vấn khía cạnh nào khi điều trị nấm da chân?",
          options: [
            { id: "qt1", label: "Chọn thuốc chống nấm bôi" },
            { id: "qt2", label: "Khi nào cần thuốc chống nấm uống" },
            { id: "qt3", label: "Phòng tái phát và vệ sinh" },
            { id: "qt4", label: "Nấm móng đi kèm" },
          ],
          answered: { optionId: "qt3", label: "Phòng tái phát và vệ sinh" },
        },
        createdAt: "2026-08-16T14:02:00.000Z",
        status: "done",
      },
      {
        id: "msg-4-3",
        conversationId: "conv-4",
        role: "user",
        content: "Phòng tái phát và vệ sinh",
        createdAt: "2026-08-16T14:03:00.000Z",
        status: "done",
      },
      {
        id: "msg-4-4",
        conversationId: "conv-4",
        role: "assistant",
        content:
          "**Theo lựa chọn \"Phòng tái phát và vệ sinh\" của bạn, tôi xin tư vấn như sau:**\n\nNấm da chân rất dễ tái phát nếu không xử lý môi trường ẩm:\n\n1. **Giữ khô kẽ ngón**: sau khi tắm lau thật khô, có thể dùng máy sấy mát; dùng bột hút ẩm hoặc bột chống nấm ở giày.\n2. **Vớ và giày**: thay vớ cotton hằng ngày, luân phiên 2–3 đôi giày cho khô hẳn, không đi giày kín ẩm liên tục.\n3. **Không dùng chung**: khăn, dép, bấm móng; đi dép ở khu vực ẩm chung (hồ bơi, phòng tắm công cộng).\n4. **Xử lý đồ dùng**: giặt vớ, khăn, thảm ở nhiệt độ cao và phơi nắng.\n5. Bôi thuốc chống nấm **đủ thời gian**, duy trì thêm 1–2 tuần sau khi hết triệu chứng để tránh tái phát.\n\nNếu tái phát nhiều lần hoặc lan lên móng, nên khám bác sĩ da liễu để cân nhắc thuốc chống nấm đường uống.",
        reasoning: [
          {
            id: "r-4-4-1",
            title: "Nhận diện vấn đề",
            content:
              "Người dùng quan tâm việc phòng tái phát nấm da chân — trọng tâm là kiểm soát độ ẩm và vệ sinh đồ dùng.",
            status: "done",
          },
          {
            id: "r-4-4-2",
            title: "Đối chiếu hướng dẫn chuyên môn",
            content:
              "Hướng dẫn điều trị nấm da: giữ da khô thoáng, thay vớ hằng ngày, không dùng chung đồ, giặt đồ nhiệt độ cao; bôi thuốc duy trì sau khi hết triệu chứng.",
            status: "done",
          },
          {
            id: "r-4-4-3",
            title: "Soạn câu trả lời",
            content:
              "Tổng hợp các biện pháp giữ khô, chăm sóc giày vớ, xử lý đồ dùng và thời gian dùng thuốc theo từng bước.",
            status: "done",
          },
        ],
        createdAt: "2026-08-16T14:07:00.000Z",
        status: "done",
      },
    ],
  },
  {
    id: "conv-5",
    title: "Hướng dẫn chăm sóc da sau laser",
    createdAt: "2026-08-15T09:30:00.000Z",
    updatedAt: "2026-08-15T09:35:00.000Z",
    messages: [
      {
        id: "msg-5-1",
        conversationId: "conv-5",
        role: "user",
        content: "Soạn giúp em hướng dẫn chăm sóc da tại nhà cho bệnh nhân sau khi bắn laser trị nám.",
        createdAt: "2026-08-15T09:30:00.000Z",
        status: "done",
      },
      {
        id: "msg-5-2",
        conversationId: "conv-5",
        role: "assistant",
        content:
          "Dưới đây là mẫu **hướng dẫn chăm sóc da sau laser** để phát cho người bệnh. Bạn có thể bấm chuột phải vào khối văn bản và chọn **\"Chỉnh sửa block\"** để mở canvas, điền thông tin cụ thể.",
        reasoning: [
          {
            id: "r-5-2-1",
            title: "Nhận diện vấn đề",
            content: "Yêu cầu soạn hướng dẫn chăm sóc da tại nhà sau thủ thuật laser trị nám.",
            status: "done",
          },
          {
            id: "r-5-2-2",
            title: "Soạn văn bản",
            content: "Tạo khung hướng dẫn theo khuyến cáo chăm sóc da sau laser: làm dịu, chống nắng, kiêng hoạt chất mạnh.",
            status: "done",
          },
        ],
        document: {
          id: "doc-5-2",
          title: "Hướng dẫn chăm sóc da sau laser",
          content: [
            "<h2>Hướng dẫn chăm sóc da sau laser</h2>",
            "<p>Người bệnh: ……………………………  Ngày thực hiện: ……/……/……</p>",
            "<h3>3 ngày đầu</h3>",
            "<p>1. Rửa mặt nhẹ nhàng bằng nước sạch hoặc sữa rửa mặt dịu nhẹ, không chà xát.</p>",
            "<p>2. Bôi kem làm dịu, phục hồi (panthenol, ceramide) 2–3 lần/ngày.</p>",
            "<p>3. Có thể chườm mát qua lớp gạc sạch, không chườm đá trực tiếp.</p>",
            "<h3>Tuần đầu</h3>",
            "<p>1. Tuyệt đối chống nắng, hạn chế ra nắng; đội mũ, che chắn.</p>",
            "<p>2. Dùng kem chống nắng phổ rộng SPF ≥ 50 khi da đã lành bề mặt.</p>",
            "<p>3. Không bóc vảy, không tẩy tế bào chết, tạm ngưng retinoid, AHA/BHA, sản phẩm chứa cồn.</p>",
            "<h3>Dấu hiệu cần tái khám ngay</h3>",
            "<p>Đau tăng, sưng nóng đỏ lan rộng, mụn mủ, sốt — có thể là nhiễm trùng.</p>",
          ].join("\n"),
          isCanvas: false,
        },
        createdAt: "2026-08-15T09:35:00.000Z",
        status: "done",
      },
    ],
  },
];
