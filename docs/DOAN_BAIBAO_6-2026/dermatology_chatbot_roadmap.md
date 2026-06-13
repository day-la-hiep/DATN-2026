# Roadmap xây dựng Dermatology Chatbot từ 7 bệnh đến hàng trăm bệnh

## 1. Mục tiêu hệ thống

Xây dựng hệ thống chatbot da liễu có khả năng:

- Phân tích ảnh tổn thương da
- Trả lời câu hỏi y khoa
- Giải thích dự đoán
- Mở rộng từ 7 bệnh HAM10000 lên hàng trăm bệnh
- Kết hợp CNN + Knowledge Graph + Vector Database + RAG

---

# 2. Kiến trúc tổng thể

```text
                    USER
                      |
        +-------------+-------------+
        |                           |
        v                           v
   Image Upload                Text Query
        |                           |
        v                           v
     CNN Model              NLP Processing
        |                           |
        +-------------+-------------+
                      |
                      v
               Feature Layer
                      |
          +-----------+-----------+
          |                       |
          v                       v
     Knowledge Graph       Vector Retrieval
          |                       |
          +-----------+-----------+
                      |
                      v
                Fusion Layer
                      |
                      v
              Disease Ranking
                      |
                      v
                Explanation
                      |
                      v
                   Chatbot
```

---

# 3. Giai đoạn 1: HAM10000

## Diseases

- MEL
- NV
- BCC
- AKIEC
- BKL
- DF
- VASC

## Pipeline

```text
Image
  |
  v
CNN
  |
  v
Disease Probabilities
```

Output:

```text
MEL   0.82
BCC   0.10
NV    0.05
```

---

# 4. Giai đoạn 2: Knowledge Graph

## Node Types

### Disease

```text
MEL
BCC
NV
...
```

### Feature

```text
asymmetry
border_irregularity
color_variation
ulceration
pearly_nodule
...
```

### Symptom

```text
itching
bleeding
pain
```

### Risk Factor

```text
sun_exposure
family_history
fair_skin
```

### Diagnosis

```text
dermoscopy
biopsy
```

### Treatment

```text
surgery
cryotherapy
radiotherapy
```

---

## Graph Structure

```text
Disease
   |
   +---- HAS_FEATURE
   |
   +---- HAS_SYMPTOM
   |
   +---- HAS_RISK
   |
   +---- DIAGNOSED_BY
   |
   +---- TREATED_BY
```

---

# 5. Giai đoạn 3: Disease Profiles

Mỗi bệnh có profile riêng.

Ví dụ:

```json
{
  "disease": "MEL",
  "description": "...",
  "features": [
    "asymmetry",
    "border_irregularity",
    "color_variation"
  ],
  "symptoms": [
    "itching",
    "bleeding"
  ]
}
```

---

# 6. Giai đoạn 4: Vector Database

## Dữ liệu

- Dermatology textbooks
- PubMed articles
- Clinical guidelines
- Disease profiles

## Chunking

```text
Document
    |
    v
Chunks
    |
    v
Embeddings
    |
    v
FAISS
```

---

# 7. Giai đoạn 5: Semantic Retrieval

## Feature Retrieval

```text
Query
   |
   v
Embedding
   |
   v
Feature Nodes
```

Ví dụ:

```text
"many colors"
    -> color_variation

"uneven edges"
    -> border_irregularity
```

---

# 8. Giai đoạn 6: Node Embeddings

Mỗi node trong graph có embedding.

```text
Disease Node
Feature Node
Symptom Node
Risk Node
Treatment Node
```

Ví dụ:

```python
{
    "node": "border_irregularity",
    "embedding": [...]
}
```

---

# 9. Giai đoạn 7: Graph Retrieval

Thay vì search document trước:

```text
Query
  |
  v
Graph Node Retrieval
  |
  v
Graph Expansion
  |
  v
Disease Candidates
```

---

# 10. Giai đoạn 8: Fusion Layer

## Inputs

### CNN

$$
P_{cnn}(d)
$$

### Graph

$$
P_{graph}(d)
$$

### Retrieval

$$
P_{rag}(d)
$$

---

## Fusion

$$
Score(d)
=
w_1 P_{cnn}(d)
+
w_2 P_{graph}(d)
+
w_3 P_{rag}(d)
$$

Trong đó:

$$
w_1+w_2+w_3=1
$$

---

# 11. Giai đoạn 9: Explanation Engine

Ví dụ:

```text
Prediction: MEL
Confidence: 0.87

Reasons:

- CNN detected melanoma patterns
- Border irregularity detected
- Color variation detected
- Retrieved medical evidence supports melanoma
```

---

# 12. Giai đoạn 10: Mở rộng lên hàng trăm bệnh

## Không nên

```text
FEATURE_MAP
``

vì sẽ tăng rất nhanh.

---

## Nên

```text
Knowledge Graph
      +
Node Embeddings
      +
Graph Retrieval
```

---

# 13. Kiến trúc cuối cùng

```text
                           USER
                             |
           +-----------------+-----------------+
           |                                   |
           v                                   v
      IMAGE INPUT                        TEXT INPUT
           |                                   |
           v                                   v
      CNN MODEL                        NLP MODULE
           |                                   |
           +---------------+-------------------+
                           |
                           v
                     FEATURE LAYER
                           |
             +-------------+-------------+
             |                           |
             v                           v
      KNOWLEDGE GRAPH             VECTOR STORE
             |                           |
             +-------------+-------------+
                           |
                           v
                     FUSION LAYER
                           |
                           v
                    DISEASE RANKING
                           |
                           v
                   EXPLANATION ENGINE
                           |
                           v
                        CHATBOT
```

---

# Khuyến nghị nghiên cứu

Đối với bài toán mở rộng từ HAM10000 lên hàng trăm bệnh:

1. CNN chỉ dùng cho ảnh.
2. Knowledge Graph là trung tâm tri thức.
3. FAISS dùng cho RAG.
4. Mỗi node trong graph có embedding.
5. Fusion CNN + Graph + RAG là tầng quyết định cuối cùng.
6. Tránh phụ thuộc vào rule-based feature extraction.
