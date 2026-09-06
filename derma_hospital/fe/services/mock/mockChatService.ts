  import type {
  AnswerQuestionInput,
  ChatMessage,
  ChatService,
  ChatStreamEvent,
  ChoiceOption,
  ComposedDocument,
  Conversation,
  ReasoningStep,
  SendMessageInput,
} from "@/features/chat/types";
import { delay, now, seedConversations } from "./data";

const STORAGE_KEY = "derma-ai-mock-chats-v1";
const MAX_SAVED_TITLE_LENGTH = 50;

type Stored = {
  conversations: Conversation[];
  messages: ChatMessage[];
};

function seedStored(): Stored {
  const conversations: Conversation[] = seedConversations.map(
    ({ id, title, createdAt, updatedAt }) => ({
      id,
      title,
      createdAt,
      updatedAt,
    })
  );
  const messages: ChatMessage[] = seedConversations.flatMap(
    (c) => c.messages
  );
  return { conversations, messages };
}

function load(): Stored {
  if (typeof window === "undefined") {
    return seedStored();
  }
  const raw = localStorage.getItem(STORAGE_KEY);
  if (raw) {
    try {
      return JSON.parse(raw) as Stored;
    } catch {
      // ignore corrupted data
    }
  }
  const initial = seedStored();
  persist(initial);
  return initial;
}

function persist(data: Stored) {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
}

let cache: Stored = load();

function saveConversations(conversations: Conversation[]) {
  cache = { ...cache, conversations };
  persist(cache);
}

function saveMessages(messages: ChatMessage[]) {
  cache = { ...cache, messages };
  persist(cache);
}

/* ---------------- reasoning + nội dung mô phỏng ---------------- */

function topicFor(content: string): string {
  const text = content.toLowerCase();
  if (text.includes("mụn") || text.includes("trứng cá")) {
    return "mụn trứng cá";
  }
  if (
    text.includes("viêm da") ||
    text.includes("chàm") ||
    text.includes("cơ địa") ||
    text.includes("eczema")
  ) {
    return "viêm da cơ địa";
  }
  if (
    text.includes("nấm") ||
    text.includes("hắc lào") ||
    text.includes("lang ben")
  ) {
    return "nhiễm nấm da";
  }
  if (
    text.includes("nám") ||
    text.includes("tàn nhang") ||
    text.includes("sạm da")
  ) {
    return "nám và rối loạn sắc tố";
  }
  return "chăm sóc da liễu chung";
}

/** Bước suy luận gồm title (ngắn) + content (chi tiết) */
type MockReasoningStep = {
  title: string;
  content: string;
};

function reasoningFor(
  content: string,
  modelId?: string
): MockReasoningStep[] {
  const topic = topicFor(content);
  const steps: MockReasoningStep[] = [
    {
      title: "Nhận diện vấn đề",
      content: `Phân tích câu hỏi của bạn, xác định đây thuộc lĩnh vực ${topic} cần tra cứu quy định.`,
    },
    {
      title: "Đối chiếu hướng dẫn chuyên môn",
      content:
        "Tra cứu và đối chiếu các hướng dẫn chẩn đoán, phác đồ điều trị da liễu hiện hành có liên quan trực tiếp đến tình huống nêu trên.",
    },
  ];
  // model nhanh chỉ làm 2 bước, model pro làm đủ 4 bước
  if (modelId !== "derma-ai-lite") {
    steps.push(
      {
        title: "Áp dụng vào tình huống",
        content:
          "Áp dụng phác đồ vào trường hợp cụ thể, cân nhắc mức độ tổn thương, cơ địa, thuốc bôi/uống và các lưu ý khi dùng.",
      },
      {
        title: "Soạn câu trả lời",
        content:
          "Tổng hợp thành hướng dẫn dễ hiểu theo từng bước, kèm các cảnh báo và dấu hiệu cần đi khám bác sĩ da liễu.",
      }
    );
  }
  return steps;
}

function replyFor(content: string): string {
  const text = content.toLowerCase();
  if (text.includes("mụn") || text.includes("trứng cá")) {
    return "Theo Hướng dẫn điều trị mụn trứng cá, việc chọn thuốc phụ thuộc mức độ:\n\n1. **Mụn nhẹ**: retinoid bôi (adapalene/tretinoin) buổi tối, có thể phối hợp benzoyl peroxide.\n2. **Mụn trung bình**: retinoid bôi + benzoyl peroxide + kháng sinh bôi; cân nhắc doxycycline uống tối đa 3 tháng.\n3. **Mụn nặng, mụn nang, dễ để lại sẹo**: cần bác sĩ da liễu đánh giá dùng isotretinoin đường uống.\n\nSong song, dùng sữa rửa mặt dịu nhẹ, dưỡng ẩm non-comedogenic, chống nắng hằng ngày và **không tự ý nặn mụn**.\n\nBạn cho tôi biết thêm tình trạng mụn (loại, vị trí, đã dùng thuốc gì) để tư vấn cụ thể hơn nhé.";
  }
  if (
    text.includes("viêm da") ||
    text.includes("chàm") ||
    text.includes("cơ địa") ||
    text.includes("eczema")
  ) {
    return "Với viêm da cơ địa, nền tảng điều trị gồm:\n\n1. **Phục hồi hàng rào da**: dưỡng ẩm ngày 2–3 lần, bôi ngay sau khi tắm; tắm nước ấm ngắn, sữa tắm dịu nhẹ.\n2. **Kiểm soát đợt bùng phát**: corticoid bôi theo mức độ và vị trí (loại nhẹ cho mặt, nếp gấp), dùng ngắn ngày; vùng da mỏng cân nhắc tacrolimus/pimecrolimus.\n3. **Giảm ngứa**: kháng histamine đường uống, nhất là về đêm.\n4. **Tránh yếu tố kích ứng**: len dạ, xà phòng kiềm mạnh, mồ hôi, dị nguyên đã biết.\n\nVới trẻ em nên ưu tiên corticoid hoạt lực thấp, thời gian ngắn và theo dõi bởi bác sĩ.";
  }
  if (
    text.includes("nấm") ||
    text.includes("hắc lào") ||
    text.includes("lang ben")
  ) {
    return "Nấm da điều trị theo mức độ lan rộng:\n\n- **Khu trú**: thuốc chống nấm bôi (ketoconazole, clotrimazole hoặc terbinafine), bôi rộng ra ngoài rìa tổn thương và duy trì thêm 1–2 tuần sau khi hết triệu chứng.\n- **Lan rộng, nấm bàn chân mạn, kèm nấm móng**: thuốc chống nấm đường uống (terbinafine/itraconazole) 2–4 tuần, dài hơn nếu có nấm móng.\n\nĐể tránh tái phát: giữ da khô thoáng, lau khô kẽ ngón chân, thay tất hằng ngày, không dùng chung giày dép khăn, giặt đồ ở nhiệt độ cao và phơi nắng.\n\nBạn mô tả rõ hơn vị trí và thời gian bị để tôi tư vấn chi tiết hơn.";
  }
  if (
    text.includes("nám") ||
    text.includes("tàn nhang") ||
    text.includes("sạm da")
  ) {
    return "Điều trị nám má cần kiên trì và luôn đi kèm chống nắng:\n\n1. **Bắt buộc**: kem chống nắng phổ rộng SPF ≥ 50, PA++++, thoa lại mỗi 2–3 giờ + che chắn vật lý.\n2. **Thuốc bôi**: hydroquinone 2–4% từng đợt 8–12 tuần dưới theo dõi của bác sĩ; hoặc azelaic acid, tranexamic acid, vitamin C, retinoid nồng độ thấp.\n3. **Sau sinh / cho con bú**: ưu tiên chống nắng, azelaic acid, vitamin C; trì hoãn hydroquinone và laser.\n\nBạn nên khám bác sĩ da liễu để xác định loại nám (thượng bì / trung bì) trước khi chọn phác đồ.";
  }
  return "Cảm ơn câu hỏi của bạn. Dựa trên nội dung bạn đưa ra, tôi đang tra cứu các hướng dẫn chuyên môn da liễu liên quan.\n\n**Lưu ý đây là giao diện demo** — hiện dữ liệu đang được mock. Khi hệ thống kết nối backend, bạn sẽ nhận được câu trả lời phân tích từ mô hình AI thật.\n\nBạn có thể mô tả rõ hơn triệu chứng (vị trí, thời gian, hình thái tổn thương, đã dùng thuốc gì) để tôi tư vấn chính xác hơn. Các vấn đề thường gặp: **mụn trứng cá, viêm da cơ địa, nấm da, nám và rối loạn sắc tố**.";
}

/** Câu hỏi làm rõ agent đưa ra theo chủ đề */
function questionFor(content: string): { text: string; options: ChoiceOption[] } {
  const text = content.toLowerCase();
  if (text.includes("mụn") || text.includes("trứng cá")) {
    return {
      text: "Để tư vấn chính xác hơn, bạn muốn tìm hiểu khía cạnh nào của mụn trứng cá?",
      options: [
        { id: "qk1", label: "Chọn thuốc bôi theo mức độ mụn" },
        { id: "qk2", label: "Khi nào cần dùng thuốc uống" },
        { id: "qk3", label: "Chăm sóc da và chọn mỹ phẩm" },
        { id: "qk4", label: "Xử lý thâm và sẹo sau mụn" },
      ],
    };
  }
  if (
    text.includes("viêm da") ||
    text.includes("chàm") ||
    text.includes("cơ địa") ||
    text.includes("eczema")
  ) {
    return {
      text: "Bạn muốn tôi tư vấn khía cạnh nào của viêm da cơ địa?",
      options: [
        { id: "qh1", label: "Dưỡng ẩm và chăm sóc hàng rào da" },
        { id: "qh2", label: "Dùng corticoid bôi an toàn" },
        { id: "qh3", label: "Kiểm soát ngứa và đợt bùng phát" },
        { id: "qh4", label: "Viêm da cơ địa ở trẻ em" },
      ],
    };
  }
  if (
    text.includes("nấm") ||
    text.includes("hắc lào") ||
    text.includes("lang ben")
  ) {
    return {
      text: "Bạn đang quan tâm đến vấn đề nào khi điều trị nấm da?",
      options: [
        { id: "qt1", label: "Chọn thuốc chống nấm bôi" },
        { id: "qt2", label: "Khi nào cần thuốc chống nấm uống" },
        { id: "qt3", label: "Phòng tái phát và vệ sinh" },
        { id: "qt4", label: "Nấm móng đi kèm" },
      ],
    };
  }
  if (
    text.includes("nám") ||
    text.includes("tàn nhang") ||
    text.includes("sạm da")
  ) {
    return {
      text: "Bạn muốn tư vấn vấn đề nào về nám và sắc tố?",
      options: [
        { id: "ql1", label: "Chống nắng đúng cách" },
        { id: "ql2", label: "Thuốc bôi làm sáng da" },
        { id: "ql3", label: "Nám sau sinh, đang cho con bú" },
        { id: "ql4", label: "Laser và các thủ thuật" },
      ],
    };
  }
  return {
    text: "Bạn muốn tôi hỗ trợ theo hướng nào?",
    options: [
      { id: "qd1", label: "Tư vấn chăm sóc da cơ bản" },
      { id: "qd2", label: "Soạn hướng dẫn điều trị, dùng thuốc" },
      { id: "qd3", label: "Hướng dẫn quy trình chăm sóc tại nhà" },
      { id: "qd4", label: "Phân tích triệu chứng cụ thể" },
    ],
  };
}

/** Câu trả lời cuối sau khi người dùng chọn lựa */
function finalReplyFor(answerLabel: string, content: string): string {
  const base = replyFor(content);
  return `**Theo lựa chọn "${answerLabel}" của bạn, tôi xin tư vấn như sau:**\n\n${base}`;
}

const DRAFTING_KEYWORDS = [
  "soạn",
  "phác đồ",
  "hướng dẫn",
  "đơn thuốc",
  "quy trình",
  "văn bản",
  "mẫu",
  "chỉ định",
  "chăm sóc tại nhà",
  "lịch điều trị",
];

function isDraftingRequest(text: string): boolean {
  const t = text.toLowerCase();
  return DRAFTING_KEYWORDS.some((k) => t.includes(k));
}

/** Sinh mẫu văn bản soạn sẵn (HTML) cho mock */
function documentFor(content: string): { title: string; html: string } {
  const t = content.toLowerCase();
  if (t.includes("phác đồ") || t.includes("đơn thuốc") || t.includes("điều trị")) {
    return {
      title: "Phác đồ điều trị",
      html: [
        "<h2>Phác đồ điều trị</h2>",
        "<p><strong>Người bệnh:</strong> ………………………………………………</p>",
        "<p><strong>Chẩn đoán:</strong> ………………………………………………</p>",
        "<h3>Thuốc bôi</h3>",
        "<p>Tên thuốc, nồng độ, thời điểm bôi (sáng/tối), vùng bôi, thời gian dùng.</p>",
        "<h3>Thuốc uống (nếu có)</h3>",
        "<p>Tên thuốc, liều theo cân nặng, số ngày, lưu ý xét nghiệm theo dõi.</p>",
        "<h3>Tái khám</h3>",
        "<p>Hẹn tái khám sau …… tuần hoặc khi có dấu hiệu bất thường.</p>",
        "<p><em>(Phần chấm … để bác sĩ điền thông tin chi tiết.)</em></p>",
      ].join("\n"),
    };
  }
  if (t.includes("chăm sóc") || t.includes("hướng dẫn") || t.includes("quy trình")) {
    return {
      title: "Hướng dẫn chăm sóc da tại nhà",
      html: [
        "<h2>Hướng dẫn chăm sóc da tại nhà</h2>",
        "<p>Áp dụng cho: ………………………………………………</p>",
        "<h3>Buổi sáng</h3>",
        "<p>1. Rửa mặt bằng sữa rửa mặt dịu nhẹ.</p>",
        "<p>2. Bôi kem dưỡng ẩm phù hợp loại da.</p>",
        "<p>3. Thoa kem chống nắng phổ rộng SPF ≥ 30, thoa lại sau mỗi 2–3 giờ.</p>",
        "<h3>Buổi tối</h3>",
        "<p>1. Làm sạch da, rửa mặt lại với sữa rửa mặt.</p>",
        "<p>2. Bôi thuốc điều trị theo chỉ định (nếu có).</p>",
        "<p>3. Bôi kem dưỡng ẩm phục hồi.</p>",
        "<h3>Lưu ý</h3>",
        "<p>Không tự ý nặn mụn, không chà xát mạnh; ngưng sản phẩm nếu da kích ứng kéo dài và liên hệ bác sĩ.</p>",
      ].join("\n"),
    };
  }
  return {
    title: "Văn bản soạn sẵn",
    html: [
      "<h2>Văn bản soạn sẵn</h2>",
      "<p>Nội dung được trợ lý soạn thảo, bạn có thể chỉnh sửa trực tiếp.</p>",
    ].join("\n"),
  };
}

function chunkText(text: string, size: number): string[] {
  const chunks: string[] = [];
  for (let i = 0; i < text.length; i += size) {
    chunks.push(text.slice(i, i + size));
  }
  return chunks;
}

/* ---------------- mock service ---------------- */

const listeners = new Set<(event: ChatStreamEvent) => void>();
let connected = false;

/** Server sinh uuid thật cho message (mô phỏng) */
let seq = 0;
function serverMessageId() {
  seq += 1;
  return `msg-${Date.now()}-${seq}`;
}

/** Điều chỉnh tốc độ mô phỏng (ms) — tăng lên để xem reasoning chậm hơn */
const PACING = {
  initialDelay: 400,
  /** độ trễ giữa các token trong một bước — nhỏ = stream mượt như thật */
  stepTokenDelay: 90,
  /** nghỉ giữa các bước */
  stepGap: 400,
  /** nghỉ trước khi bắt đầu gen final response */
  preResponseDelay: 500,
  messageChunkDelay: 80,
} as const;

function emit(event: ChatStreamEvent) {
  listeners.forEach((listener) => listener(event));
}

/** Stream từng bước suy luận theo thời gian thực theo chuẩn ConversationStreamEvent */
async function streamSteps(
  messageId: string,
  conversationId: string,
  reasoning: MockReasoningStep[],
  clientMessageId?: string
) {
  for (let i = 0; i < reasoning.length; i++) {
    const step = reasoning[i];
    const stepId = `${messageId}-step-${i + 1}`;
    emit({
      corr_id: clientMessageId ?? messageId,
      message_id: messageId,
      conversation_id: conversationId,
      metadata: {
        status: "reasoning.step_started",
        title: step.title,
        content: "",
        stepId,
        stepType: "default",
        toolMetadata: { name: "ask_tool" },
      },
    });
    for (const token of chunkText(step.content, 3)) {
      emit({
        corr_id: clientMessageId ?? messageId,
        message_id: messageId,
        conversation_id: conversationId,
        metadata: {
          status: "reasoning_step_delta",
          title: step.title,
          content: token,
          stepId,
          toolMetadata: { name: "ask_tool" },
        },
      });
      await delay(PACING.stepTokenDelay);
    }
    emit({
      corr_id: clientMessageId ?? messageId,
      message_id: messageId,
      conversation_id: conversationId,
      metadata: {
        status: "reasoning.step_completed",
        title: step.title,
        content: step.content,
        stepId,
        toolMetadata: { name: "ask_tool" },
      },
    });
    await delay(PACING.stepGap);
  }
}

function toDoneSteps(
  reasoning: MockReasoningStep[],
  messageId: string
): ReasoningStep[] {
  return reasoning.map((step, i) => ({
    id: `${messageId}-step-${i + 1}`,
    title: step.title,
    content: step.content,
    status: "done",
  }));
}

function bumpConversation(conversationId: string, content: string) {
  saveConversations(
    cache.conversations.map((c) => {
      if (c.id !== conversationId) return c;
      const shouldRename = !c.title.trim();
      return {
        ...c,
        updatedAt: now(),
        title: shouldRename ? content.slice(0, MAX_SAVED_TITLE_LENGTH) : c.title,
      };
    })
  );
}

/**
 * Service mock: mô phỏng backend bằng cách phát sự kiện stream (SSE) theo
 * thời gian thực theo đúng cấu trúc ConversationStreamEvent.
 */
export const mockChatService: ChatService = {
  async connect() {
    await delay(120);
    connected = true;
  },

  disconnect() {
    connected = false;
  },

  async getConversations() {
    await delay(250);
    return [...cache.conversations].sort((a, b) =>
      b.updatedAt.localeCompare(a.updatedAt)
    );
  },

  async getMessages(conversationId) {
    await delay(200);
    return cache.messages
      .filter((m) => m.conversationId === conversationId)
      .sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  },

  async createConversation(input) {
    await delay(150);
    const title =
      typeof input === "string"
        ? input
        : input?.title ?? "";
    const conversation: Conversation = {
      id: `conv-${Date.now()}`,
      title: title ?? "",
      createdAt: now(),
      updatedAt: now(),
    };
    saveConversations([conversation, ...cache.conversations]);
    return conversation;
  },

  onEvent(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },

  async updateDocument({ messageId, content, isCanvas }) {
    await delay(120);
    saveMessages(
      cache.messages.map((m) =>
        m.id === messageId && m.document
          ? {
              ...m,
              document: {
                ...m.document,
                content,
                isCanvas: isCanvas ?? m.document.isCanvas,
              },
            }
          : m
      )
    );
  },

  sendMessage(input: SendMessageInput) {
    if (!connected) return;

    const { conversationId, content } = input;
    // Fallback sang corrId nếu call site quên set clientMessageId — tránh id trùng
    // (`msg-user-undefined`) khiến React coi nhiều message là cùng 1 key.
    const clientMessageId = input.clientMessageId ?? input.corrId;
    // server sinh uuid thật; client chỉ ghép luồng qua clientMessageId / corr_id
    const messageId = serverMessageId();

    const userMessage: ChatMessage = {
      id: `msg-user-${clientMessageId}`,
      conversationId,
      role: "user",
      content,
      selectionRef: input.selection,
      createdAt: now(),
      status: "done",
    };
    saveMessages([...cache.messages, userMessage]);

    const startedAt = now();

    void (async () => {
      // event đầu tiên: thông báo messageId server đã sinh (ConversationStreamEvent format)
      emit({
        corr_id: clientMessageId,
        message_id: messageId,
        conversation_id: conversationId,
        metadata: {
          status: "message.started",
          content: "",
        },
      });

      await delay(PACING.initialDelay);

      const reasoning = reasoningFor(content, input.modelId);
      const reply = replyFor(content);

      // 1. Stream toàn bộ các bước suy luận
      await streamSteps(messageId, conversationId, reasoning, clientMessageId);

      // 2. Stream câu trả lời của AI
      await delay(PACING.preResponseDelay);
      for (const chunk of chunkText(reply, 34)) {
        emit({
          corr_id: clientMessageId,
          message_id: messageId,
          conversation_id: conversationId,
          metadata: {
            status: "message.delta",
            content: chunk,
          },
        });
        await delay(PACING.messageChunkDelay);
      }

      // 3. Lưu tin nhắn hoàn chỉnh và emit message.done
      const reasoningSteps = toDoneSteps(reasoning, messageId);
      const assistantMessage: ChatMessage = {
        id: messageId,
        conversationId,
        role: "assistant",
        content: reply,
        reasoning: reasoningSteps,
        createdAt: startedAt,
        status: "done",
      };
      saveMessages([...cache.messages, assistantMessage]);
      bumpConversation(conversationId, content);

      emit({
        corr_id: clientMessageId,
        message_id: messageId,
        conversation_id: conversationId,
        metadata: {
          status: "message.done",
          content: reply,
        },
      });

      emit({
        type: "message.done",
        messageId,
        conversationId,
        reasoning: reasoningSteps,
      });
    })();
  },

  /** Mô phỏng `POST /questions/{questionId}/answer` — resume ĐÚNG message assistant đang
   * chờ (không tạo message mới), giống hành vi thật của backend. */
  answerQuestion(input: AnswerQuestionInput) {
    if (!connected) return;
    const { conversationId, questionId, optionId, label, custom } = input;

    const target = cache.messages.find(
      (m) => m.conversationId === conversationId && m.choice?.questionId === questionId
    );
    if (!target) return;

    const answeredObj = { optionId, label, custom };
    saveMessages(
      cache.messages.map((m) =>
        m.id === target.id
          ? {
              ...m,
              choice: m.choice ? { ...m.choice, answered: answeredObj } : m.choice,
              reasoning: (m.reasoning ?? []).map((rs) =>
                rs.choice ? { ...rs, choice: { ...rs.choice, answered: answeredObj } } : rs
              ),
            }
          : m
      )
    );

    const messageId = target.id;
    const originalContent = target.content || target.choice?.question || "";

    void (async () => {
      const reasoning = reasoningFor(originalContent);
      const reply = finalReplyFor(label, originalContent);

      await delay(PACING.preResponseDelay);
      await streamSteps(messageId, conversationId, reasoning);

      for (const chunk of chunkText(reply, 34)) {
        emit({ type: "message.delta", messageId, conversationId, delta: chunk });
        await delay(PACING.messageChunkDelay);
      }

      const reasoningSteps = toDoneSteps(reasoning, messageId);
      saveMessages(
        cache.messages.map((m) =>
          m.id === messageId
            ? {
                ...m,
                content: `${m.content}${reply}`,
                reasoning: [...(m.reasoning ?? []), ...reasoningSteps],
                status: "done",
              }
            : m
        )
      );
      bumpConversation(conversationId, originalContent);

      emit({
        type: "message.done",
        messageId,
        conversationId,
        reasoning: reasoningSteps,
      });
    })();
  },

  async improvePrompt(prompt: string) {
    await delay(800);
    const text = prompt.trim();
    if (!text) return "";

    const lower = text.toLowerCase();

    if (lower.includes("phác đồ") || lower.includes("soạn") || lower.includes("hướng dẫn")) {
      return `Hãy đóng vai trò là một bác sĩ da liễu. Tôi cần soạn một hướng dẫn điều trị chi tiết, rõ ràng và dễ theo dõi cho người bệnh.
Vui lòng chuẩn bị các nội dung chính sau:
1. Tóm tắt chẩn đoán và mức độ tổn thương da.
2. Thuốc bôi: tên hoạt chất, nồng độ, thời điểm và cách bôi, thời gian dùng.
3. Thuốc uống (nếu có): liều theo cân nặng, thời gian, xét nghiệm cần theo dõi.
4. Chăm sóc da hằng ngày: làm sạch, dưỡng ẩm, chống nắng.
5. Những việc cần tránh và dấu hiệu cần tái khám sớm.
6. Lịch tái khám và tiên lượng.`;
    }

    if (lower.includes("mụn") || lower.includes("trứng cá") || lower.includes("thâm") || lower.includes("sẹo")) {
      return `Tôi đang tìm hiểu cách điều trị mụn trứng cá và xử lý thâm, sẹo sau mụn. Hãy tư vấn chi tiết dựa trên hướng dẫn điều trị mụn trứng cá hiện hành, tập trung vào:
1. Phân loại mức độ mụn và lựa chọn thuốc bôi tương ứng (retinoid, benzoyl peroxide, kháng sinh bôi).
2. Khi nào cần dùng thuốc uống (kháng sinh nhóm cycline, isotretinoin) và các lưu ý an toàn.
3. Quy trình chăm sóc da và cách chọn mỹ phẩm không gây bít tắc lỗ chân lông.
4. Hướng xử lý thâm sau viêm và sẹo rỗ, cùng vai trò của chống nắng.`;
    }

    if (lower.includes("viêm da") || lower.includes("chàm") || lower.includes("cơ địa") || lower.includes("ngứa")) {
      return `Tôi cần tư vấn về chẩn đoán và điều trị viêm da cơ địa. Xin cung cấp thông tin chi tiết về:
1. Các dấu hiệu nhận biết và yếu tố làm bệnh nặng lên.
2. Cách phục hồi hàng rào bảo vệ da: chọn và dùng kem dưỡng ẩm, cách tắm đúng.
3. Sử dụng corticoid bôi và thuốc ức chế calcineurin an toàn theo vị trí và mức độ.
4. Kiểm soát ngứa, xử lý đợt bùng phát và lưu ý riêng cho trẻ em.`;
    }

    if (lower.includes("nấm") || lower.includes("hắc lào") || lower.includes("lang ben") || lower.includes("nấm móng")) {
      return `Tôi cần tư vấn về điều trị nấm da và phòng tái phát. Hãy tư vấn theo hướng dẫn điều trị nấm da hiện hành về:
1. Cách chọn thuốc chống nấm bôi và thời gian điều trị hợp lý.
2. Khi nào cần thuốc chống nấm đường uống, các lưu ý khi dùng.
3. Xử lý nấm bàn chân mạn tính và nấm móng đi kèm.
4. Vệ sinh, giữ da khô thoáng và các biện pháp phòng lây, phòng tái phát.`;
    }

    return `Hãy đóng vai trò là một bác sĩ da liễu tại Việt Nam. Vui lòng phân tích và giải đáp chi tiết cho tôi về vấn đề da liễu này:
1. Các khả năng chẩn đoán dựa trên triệu chứng tôi mô tả và thông tin cần hỏi thêm.
2. Hướng xử trí cụ thể theo từng bước: thuốc bôi, thuốc uống, chăm sóc da.
3. Những việc cần tránh và cách chăm sóc da tại nhà để hỗ trợ điều trị.
4. Dấu hiệu cảnh báo cần đi khám bác sĩ da liễu sớm.`;
  }
};
