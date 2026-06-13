import json
import faiss
import numpy as np

from sentence_transformers import SentenceTransformer


class SemanticFeatureRetriever:

    def __init__(
        self,
        catalog_path="semantic_features/feature_catalog.json",
        index_path="semantic_features/feature_index.faiss"
    ):

        self.catalog_path = catalog_path
        self.index_path = index_path

        print("Loading SentenceTransformer...")

        self.model = SentenceTransformer(
            "sentence-transformers/all-MiniLM-L6-v2"
        )

        with open(
            self.catalog_path,
            "r",
            encoding="utf-8"
        ) as f:

            self.catalog = json.load(f)

        self.index = None

    # ======================================================
    # BUILD INDEX
    # ======================================================

    def build_index(self):

        texts = [

            f"{item['feature']} {item['description']}"

            for item in self.catalog
        ]

        embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True
        )

        embeddings = embeddings.astype(
            np.float32
        )

        dim = embeddings.shape[1]

        index = faiss.IndexFlatIP(dim)

        index.add(embeddings)

        faiss.write_index(
            index,
            self.index_path
        )

        print(
            f"Feature index saved -> {self.index_path}"
        )

    # ======================================================
    # LOAD INDEX
    # ======================================================

    def load_index(self):

        self.index = faiss.read_index(
            self.index_path
        )

    # ======================================================
    # RETRIEVE
    # ======================================================

    def retrieve(
        self,
        query,
        top_k=10,
        threshold=0.45
    ):

        if self.index is None:

            self.load_index()

        q_emb = self.model.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=True
        )

        q_emb = q_emb.astype(
            np.float32
        )

        scores, ids = self.index.search(
            q_emb,
            top_k
        )

        results = []

        for score, idx in zip(
            scores[0],
            ids[0]
        ):

            if score >= threshold:

                results.append({

                    "feature":
                        self.catalog[idx]["feature"],

                    "score":
                        round(
                            float(score),
                            3
                        )
                })

        return results

    # ======================================================
    # DEBUG
    # ======================================================

    def debug(
        self,
        query
    ):

        if self.index is None:

            self.load_index()

        q_emb = self.model.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=True
        )

        q_emb = q_emb.astype(
            np.float32
        )

        scores, ids = self.index.search(
            q_emb,
            len(self.catalog)
        )

        print("=" * 60)
        print("QUERY")
        print("=" * 60)
        print(query)

        print("\nRANKING")
        print("=" * 60)

        for score, idx in zip(
            scores[0],
            ids[0]
        ):

            print(
                f"{self.catalog[idx]['feature']:25s}"
                f"{float(score):.3f}"
            )
            
retriever = SemanticFeatureRetriever()

retriever.build_index()