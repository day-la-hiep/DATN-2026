import os
import sys
import json
import pickle
from collections import defaultdict
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import google.generativeai as genai

# Append knowledge_graph folder to sys.path to import SemanticFeatureRetriever and ExplanationEngine
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(BASE_DIR, "knowledge_base", "knowledge_graph"))

from semantic_feature_retriever import SemanticFeatureRetriever
from explanation_engine import ExplanationEngine

class DermatologyChatbotEngine:
    def __init__(self):
        # Resolve paths
        self.catalog_path = os.path.join(BASE_DIR, "knowledge_base", "knowledge_graph", "semantic_features", "feature_catalog.json")
        self.feature_index_path = os.path.join(BASE_DIR, "knowledge_base", "knowledge_graph", "semantic_features", "feature_index.faiss")
        
        self.relations_path = os.path.join(BASE_DIR, "knowledge_base", "knowledge_graph", "relations_auto.json")
        self.disease_profiles_dir = os.path.join(BASE_DIR, "knowledge_base", "disease_profiles")
        
        self.faiss_index_path = os.path.join(BASE_DIR, "load_chunk_json", "faiss_index.bin")
        self.chunks_path = os.path.join(BASE_DIR, "load_chunk_json", "chunks.pkl")
        
        print("Initializing SentenceTransformer Model (all-MiniLM-L6-v2)...")
        self.model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        
        print("Initializing Semantic Feature Retriever...")
        self.feature_retriever = SemanticFeatureRetriever(
            catalog_path=self.catalog_path,
            index_path=self.feature_index_path
        )
        
        print("Initializing Explanation Engine...")
        self.explanation_engine = ExplanationEngine(knowledge_dir=self.disease_profiles_dir)
        
        # Load relations
        print("Loading Knowledge Graph Relations...")
        with open(self.relations_path, "r", encoding="utf-8") as f:
            self.relations = json.load(f)
            
        # Load FAISS index & chunks for RAG
        print("Loading RAG FAISS index...")
        self.rag_index = faiss.read_index(self.faiss_index_path)
        with open(self.chunks_path, "rb") as f:
            self.rag_chunks = pickle.load(f)
            
        # Weights for graph reasoning
        self.relation_weights = {
            "HAS_SYMPTOM": 5,
            "HAS_VISUAL_FEATURE": 4,
            "HAS_RISK": 2,
            "CAUSED_BY": 1,
            "DIAGNOSED_BY": 1,
            "TREATED_BY": 0.5,
            "HAS_PROGNOSIS": 0.5
        }
        
    def extract_features(self, query, threshold=0.45):
        # Extract features semantically using SemanticFeatureRetriever
        matched = self.feature_retriever.retrieve(query, top_k=10, threshold=threshold)
        return [item["feature"] for item in matched], matched

    def graph_reasoning(self, user_features):
        scores = defaultdict(float)
        explanations = defaultdict(list)
        
        for edge in self.relations:
            disease = edge["s"]
            relation = edge["r"]
            target = edge["t"]
            confidence = edge.get("confidence", 1.0)
            
            if target in user_features:
                weight = self.relation_weights.get(relation, 0) * confidence
                scores[disease] += weight
                explanations[disease].append({
                    "feature": target,
                    "relation": relation,
                    "score": weight
                })
        return scores, explanations

    def retrieve_rag(self, query, top_k=5):
        # Embed query
        q_emb = self.model.encode([query], convert_to_numpy=True).astype(np.float32)
        faiss.normalize_L2(q_emb)
        
        # Search index
        distances, indices = self.rag_index.search(q_emb, top_k)
        
        retrieved_chunks = []
        rag_scores = defaultdict(float)
        
        for score, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(self.rag_chunks):
                continue
            chunk = self.rag_chunks[idx]
            retrieved_chunks.append(chunk)
            
            # Since IndexFlatIP gives dot product (cosine similarity because of L2 normalization)
            disease = chunk["disease"]
            # We track the maximum similarity score for each disease in top retrieves
            if score > rag_scores[disease]:
                rag_scores[disease] = float(score)
                
        return retrieved_chunks, rag_scores

    def get_mock_cnn_predictions(self, image_filename):
        # A helper to simulate image classification based on name cues or default distribution
        name = image_filename.lower()
        if "mel" in name or "melanoma" in name:
            return {"MEL": 0.80, "NV": 0.10, "BCC": 0.05, "AKIEC": 0.03, "BKL": 0.01, "DF": 0.00, "VASC": 0.01}
        elif "bcc" in name or "basal" in name:
            return {"BCC": 0.85, "AKIEC": 0.05, "MEL": 0.04, "NV": 0.03, "BKL": 0.02, "DF": 0.00, "VASC": 0.01}
        elif "akiec" in name or "actinic" in name:
            return {"AKIEC": 0.75, "BCC": 0.15, "MEL": 0.05, "BKL": 0.03, "NV": 0.01, "DF": 0.00, "VASC": 0.01}
        elif "nv" in name or "nevus" in name or "mole" in name:
            return {"NV": 0.85, "BKL": 0.08, "MEL": 0.05, "DF": 0.01, "BCC": 0.01, "AKIEC": 0.00, "VASC": 0.00}
        elif "bkl" in name or "seborrheic" in name:
            return {"BKL": 0.80, "NV": 0.10, "MEL": 0.04, "BCC": 0.03, "AKIEC": 0.02, "DF": 0.00, "VASC": 0.01}
        elif "df" in name or "dermatofibroma" in name:
            return {"DF": 0.80, "NV": 0.10, "BKL": 0.05, "BCC": 0.02, "MEL": 0.02, "AKIEC": 0.00, "VASC": 0.01}
        elif "vasc" in name or "vascular" in name or "angioma" in name:
            return {"VASC": 0.90, "NV": 0.05, "BKL": 0.03, "MEL": 0.01, "BCC": 0.01, "AKIEC": 0.00, "DF": 0.00}
        else:
            # Default distribution
            return {"MEL": 0.25, "NV": 0.20, "BCC": 0.15, "AKIEC": 0.15, "BKL": 0.15, "DF": 0.05, "VASC": 0.05}

    def process_query(self, query, image_filename=None, gemini_api_key=None):
        # 1. Extract features semantically
        user_features, feature_details = self.extract_features(query)
        
        # 2. Graph Reasoning
        graph_scores, graph_exps = self.graph_reasoning(user_features)
        
        # 3. FAISS RAG
        retrieved_chunks, rag_scores = self.retrieve_rag(query)
        
        # 4. CNN scores (mock if image is provided)
        cnn_scores = {}
        if image_filename:
            cnn_scores = self.get_mock_cnn_predictions(image_filename)
            
        # 5. Late Fusion
        # Normalize graph scores to range [0, 1] relative to max graph score
        max_graph = max(graph_scores.values()) if graph_scores else 1.0
        norm_graph = {d: s / max_graph for d, s in graph_scores.items()}
        
        # Fusion weights
        if image_filename:
            w_cnn, w_graph, w_rag = 0.4, 0.3, 0.3
        else:
            w_cnn, w_graph, w_rag = 0.0, 0.5, 0.5
            
        diseases = ["AKIEC", "BCC", "BKL", "DF", "MEL", "NV", "VASC"]
        combined_scores = {}
        
        for d in diseases:
            score = (
                w_cnn * cnn_scores.get(d, 0.0) +
                w_graph * norm_graph.get(d, 0.0) +
                w_rag * rag_scores.get(d, 0.0)
            )
            combined_scores[d] = round(score, 3)
            
        # Get suspected disease
        suspected_id = max(combined_scores, key=combined_scores.get)
        suspected_score = combined_scores[suspected_id]
        
        # 6. Generate detailed explanation from ExplanationEngine
        reasoning_details = [{"feature": item["feature"], "score": item["score"]} for item in feature_details]
        explanation = self.explanation_engine.generate(
            disease_id=suspected_id,
            disease_score=suspected_score,
            reasoning_details=reasoning_details
        )
        
        # 7. Generate natural language response via Gemini API
        response_text = self.generate_gemini_response(
            query=query,
            suspected_id=suspected_id,
            explanation=explanation,
            retrieved_chunks=retrieved_chunks,
            gemini_api_key=gemini_api_key
        )
        
        return {
            "suspected_disease": suspected_id,
            "scores": combined_scores,
            "explanation": explanation,
            "extracted_features": user_features,
            "response": response_text
        }

    def generate_gemini_response(self, query, suspected_id, explanation, retrieved_chunks, gemini_api_key=None):
        api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY")
        
        # Format RAG contexts
        rag_texts = ""
        for i, chunk in enumerate(retrieved_chunks, start=1):
            rag_texts += f"[{i}] {chunk['text']}\n"
            
        prompt = f"""Bạn là một chuyên gia tư vấn y khoa da liễu kỹ thuật số cực kỳ chuyên nghiệp và tận tâm.
Dựa trên bằng chứng lâm sàng được trích xuất từ Đồ thị Tri thức (Knowledge Graph) và cơ sở tri thức y khoa (RAG) dưới đây, hãy phản hồi lại thắc mắc của bệnh nhân.

Câu hỏi/Triệu chứng của bệnh nhân: "{query}"

Bệnh nghi ngờ nhất: {explanation['disease_name']} ({suspected_id})
Độ nguy hiểm (Severity): {explanation['severity']}
Điểm tin cậy (Fusion Score): {explanation['score']}

[THÔNG TIN LÂM SÀNG TỪ ĐỒ THỊ TRI THỨC]
- Các triệu chứng/đặc điểm khớp được: {', '.join(explanation['matched_features']) if explanation['matched_features'] else 'Không phát hiện đặc điểm lâm sàng cụ thể'}
- Vị trí phổ biến: {', '.join(explanation['common_locations'])}
- Biện pháp điều trị bước đầu (First Line Treatment): {', '.join(explanation['first_line_treatment'])}
- Biến chứng có thể xảy ra: {', '.join(explanation['complications']) if explanation['complications'] else 'Không có biến chứng nguy hiểm đặc thù được ghi nhận'}

[TÀI LIỆU Y KHOA THAM KHẢO (RAG)]
{rag_texts}

Hãy viết một phản hồi bằng tiếng Việt thân thiện, dễ hiểu, có cấu trúc rõ ràng:
1. Gửi lời chào bệnh nhân một cách lịch sự, thể hiện sự đồng cảm.
2. Giải thích rõ ràng tại sao hệ thống nghi ngờ tình trạng này (dựa trên các đặc điểm lâm sàng bệnh nhân đã miêu tả khớp với bệnh).
3. Đưa ra kiến thức giáo dục y tế về các triệu chứng, vị trí và cách điều trị thông thường cho bệnh nhân tham khảo.
4. Cảnh báo các biến chứng nguy hiểm nếu không điều trị kịp thời.
5. ĐẶC BIỆT LƯU Ý: Phải chèn một lời khuyên y tế (Disclaimer) thật nổi bật, nhấn mạnh rằng đây chỉ là trợ lý AI mang tính chất tham khảo giáo dục, không thể thay thế chẩn đoán lâm sàng của bác sĩ chuyên khoa da liễu và khuyên họ nên đi khám trực tiếp.
"""

        # If API key is available, run Gemini
        if api_key:
            try:
                genai.configure(api_key=api_key)
                # Use the recommended Gemini model
                model = genai.GenerativeModel("gemini-2.5-flash")
                response = model.generate_content(prompt)
                return response.text
            except Exception as e:
                print(f"Gemini API Error: {e}")
                return self.generate_fallback_response(explanation, e)
        else:
            return self.generate_fallback_response(explanation, "Chưa cấu hình Gemini API Key")

    def generate_fallback_response(self, exp, reason):
        # Fallback local response generator if Gemini API is missing/fails
        disclaimer = "\n\n⚠️ **LƯU Ý Y TẾ QUAN TRỌNG:** Đây là kết quả tự động từ hệ thống AI nhằm mục đích tham khảo giáo dục. Bạn cần đến gặp bác sĩ chuyên khoa Da liễu để được khám trực tiếp và chẩn đoán chính xác nhất."
        
        features_str = ", ".join(exp["matched_features"]) if exp["matched_features"] else "mô tả chung"
        
        text = f"Chào bạn, dựa trên các triệu chứng bạn miêu tả và phân tích từ hệ thống, chúng tôi nhận thấy các đặc điểm này khớp nhiều nhất với **{exp['disease_name']}** (Mức độ nguy hiểm: **{exp['severity']}**).\n\n"
        text += f"🔍 **Lý do nghi ngờ:** Triệu chứng của bạn khớp với các đặc điểm: *{features_str}*.\n\n"
        
        if exp["common_locations"]:
            text += f"📍 **Vị trí thường gặp:** {', '.join(exp['common_locations'])}\n"
        if exp["symptoms"]:
            text += f"📋 **Các triệu chứng đi kèm khác:** {', '.join(exp['symptoms'])}\n"
        if exp["first_line_treatment"]:
            text += f"💊 **Hướng điều trị bước đầu thông thường:** {', '.join(exp['first_line_treatment'])}\n"
        if exp["complications"]:
            text += f"⚠️ **Biến chứng có thể gặp:** {', '.join(exp['complications'])}\n"
            
        text += f"\n*(Lưu ý: Hệ thống đang chạy ở chế độ Fallback do: {reason})*"
        text += disclaimer
        return text

if __name__ == "__main__":
    # Quick test
    engine = DermatologyChatbotEngine()
    result = engine.process_query("I have a rough scaly lesion on my face that burns")
    print("\n--- TEST RESULT ---")
    print(result["response"])
