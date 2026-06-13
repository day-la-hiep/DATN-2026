# Skin Disease Diagnosis Chatbot

## Project Overview

Xây dựng chatbot hỗ trợ nhận diện và tư vấn bệnh da liễu dựa trên:

1. Ảnh tổn thương da (CNN/Transformer)
2. Triệu chứng do người dùng mô tả
3. Knowledge Base y khoa
4. Knowledge Graph Reasoning
5. Vector Search (FAISS + Embedding)

Mục tiêu cuối cùng:

```text
Image
   +
User Symptoms
   +
Medical Knowledge Base
   ↓
Disease Diagnosis
   ↓
Explanation
   ↓
Treatment Recommendation
```

---

# Dataset

Dataset: HAM10000

Classes:

| Code | Disease |
|--------|--------|
| AKIEC | Actinic Keratosis |
| BCC | Basal Cell Carcinoma |
| BKL | Benign Keratosis-like Lesion |
| DF | Dermatofibroma |
| MEL | Melanoma |
| NV | Melanocytic Nevus |
| VASC | Vascular Lesion |

Dataset size:

```text
10015 images
7 classes
```

---

# Classification Models

Đã huấn luyện:

| Model | Accuracy |
|---------|---------|
| CNN | 74.5% |
| CNN+LSTM | 62.3% |
| CNN+Transformer | 75.8% |
| CNN+Transformer+Attention | 59.0% |

Best Model:

```text
CNN + Transformer

Accuracy: 75.8%
Precision: 60.6%
Recall: 77.8%
F1: 64.4%
```

---

# Knowledge Base Architecture

```text
knowledge_base/
│
├── taxonomy.json
│
├── disease_profiles/
│     ├── AKIEC.json
│     ├── BCC.json
│     ├── BKL.json
│     ├── DF.json
│     ├── MEL.json
│     ├── NV.json
│     └── VASC.json
│
├── relations_auto.json
│
├── faiss_index.bin
│
└── chunks.pkl
```

---

# Taxonomy

taxonomy.json

Hierarchy:

```text
Skin Diseases
│
├── Malignant and Precancerous Lesions
│     ├── MEL
│     ├── BCC
│     └── AKIEC
│
├── Benign Pigmented Lesions
│     ├── NV
│     └── BKL
│
├── Benign Fibrous Lesions
│     └── DF
│
└── Vascular Lesions
      └── VASC
```

---

# Disease Profiles

Mỗi bệnh được lưu trong:

```text
disease_profiles/*.json
```

Schema:

```json
{
  "metadata": {},
  "overview": {},
  "etiology": {},
  "clinical_features": {},
  "diagnosis": {},
  "treatment": {},
  "prognosis": {}
}
```

Nguồn tham khảo:

- Cleveland Clinic
- Mayo Clinic
- DermNet
- American Cancer Society
- NHS
- NCBI Bookshelf

---

# Knowledge Graph

File:

```text
relations_auto.json
```

Auto-generated từ disease profiles.

Current graph:

```text
159 relations
```

Relation types:

```text
HAS_SYMPTOM

HAS_VISUAL_FEATURE

HAS_RISK

CAUSED_BY

DIAGNOSED_BY

TREATED_BY

HAS_PROGNOSIS
```

Example:

```json
{
  "s": "MEL",
  "r": "HAS_SYMPTOM",
  "t": "color_variation"
}
```

---

# Vector Database

Embedding model:

```text
sentence-transformers/all-MiniLM-L6-v2
```

Vector DB:

```text
FAISS IndexFlatL2
```

Current status:

```text
39 chunks
384 dimensions
```

Files:

```text
faiss_index.bin

chunks.pkl
```

Purpose:

```text
User Query
     ↓
FAISS
     ↓
Retrieve Medical Knowledge
```

---

# Graph Reasoning Engine

Input:

```text
Features
```

Example:

```python
[
    "border_irregularity",
    "color_variation"
]
```

Output:

```python
[
    ("MEL", 10.0)
]
```

Scoring:

```python
HAS_SYMPTOM = 5

HAS_VISUAL_FEATURE = 4

HAS_RISK = 2

CAUSED_BY = 1

DIAGNOSED_BY = 1
```

---

# Query Understanding

Current version:

Rule-based Feature Extraction

Example:

```text
irregular border
    ↓
border_irregularity

different colors
    ↓
color_variation
```

Current function:

```python
extract_features(query)
```

---

# Completed Components

## Knowledge Base

- [x] Taxonomy
- [x] Disease Profiles
- [x] Medical Sources
- [x] Chunk Generation

## Retrieval

- [x] Embedding
- [x] FAISS Vector Search

## Knowledge Graph

- [x] Relation Generation
- [x] Graph Construction
- [x] Graph Reasoning

## NLP

- [x] Rule-based Feature Extraction

---

# Current Development Stage

Current completion:

```text
~80%
```

Working on:

```text
Semantic Feature Retrieval
```

Goal:

```text
many different colors
      ↓
color_variation

uneven border
      ↓
border_irregularity
```

using:

```text
Sentence Transformer
```

---

# Next Steps

Priority 1:

```text
Semantic Feature Retrieval
```

Priority 2:

```text
Graph + FAISS Fusion
```

Architecture:

```text
User Query
     ↓
Feature Retrieval
     ↓
Graph Reasoning

User Query
     ↓
FAISS Retrieval

     ↓
Fusion
     ↓
Disease Ranking
```

Priority 3:

```text
CNN + Graph + FAISS Fusion
```

Architecture:

```text
Image
     ↓
CNN

Query
     ↓
Graph

Query
     ↓
FAISS

     ↓
Fusion
     ↓
Final Diagnosis
```

Priority 4:

```text
Chatbot API
```

Priority 5:

```text
Web / Mobile Interface
```

---

# Ultimate Goal

Build an explainable skin disease diagnosis assistant:

```text
Image
 +
Symptoms
 +
Medical Knowledge
 +
Reasoning
 ↓
Diagnosis
 ↓
Explanation
 ↓
Treatment Guidance
```