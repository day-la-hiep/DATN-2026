import unittest
from unittest import mock

from qdrant_client import QdrantClient

from app.infra.bm25 import SPARSE_NAME, encode_query, stopwords, tokenize
from app.infra.bm25.tokenizer import tokenize_with_folds
from app.infra.qdrant_client import QdrantVectorClient, eq_filter
from app.infra.text_clean import clean_text
from app.services.document_service import DocumentService
from app.config.settings import settings


class TextCleanTest(unittest.TestCase):
    def test_noi_gach_noi_cuoi_dong_va_bo_ky_tu_la(self) -> None:
        self.assertEqual(clean_text("psori-\nasis​ α-blocker"), "psoriasis alpha-blocker")
        self.assertEqual(clean_text("Anti-\nTNF"), "Anti-\nTNF")


class TokenizeTest(unittest.TestCase):
    def test_mixed(self) -> None:
        tokens = tokenize("The treatments of IL-17 inhibitors cho vảy nến mảng. Điều trị không có dị ứng.")
        for t in ("treatment", "il-17", "il", "17", "inhibitor", "điều_trị", "không"):
            self.assertIn(t, tokens)
        for t in ("the", "of", "."):
            self.assertNotIn(t, tokens)

    def test_so_it_so_nhieu(self) -> None:
        self.assertEqual(tokenize("databases"), tokenize("database"))

    def test_en_khong_goi_underthesea(self) -> None:
        with mock.patch("underthesea.word_tokenize", side_effect=AssertionError("không được gọi")):
            self.assertEqual(tokenize("The treatments of IL-17", "en"), ["treatment", "il-17", "il", "17"])

    def test_vi_giu_tu_ghep_va_khong_stem(self) -> None:
        tokens = tokenize("Điều trị databases", "vi")
        self.assertIn("điều_trị", tokens)
        self.assertIn("databases", tokens)

    def test_token_bo_dau(self) -> None:
        tokens, folds = tokenize_with_folds("Điều trị vảy nến", "vi")
        self.assertIn("~dieu", folds)
        self.assertIn("~vay", folds)
        self.assertNotIn("~vay", tokens)
        self.assertEqual(tokenize_with_folds("treatment", "en")[1], [])  # phía đoạn: chỉ từ có dấu
        self.assertEqual(tokenize_with_folds("treatment", "en", all_tokens=True)[1], ["~treatment"])

    def test_stopword(self) -> None:
        en = stopwords.get_stopwords("en")
        self.assertIn("the", en)
        self.assertNotIn("not", en)
        self.assertNotIn("không", stopwords.get_stopwords("vi"))

    def test_nltk_loi_thi_roi_ve_builtin(self) -> None:
        with mock.patch.dict("sys.modules", {"nltk": None}):
            self.assertEqual(stopwords._nltk("en"), stopwords._builtin("en"))


class SearchByModeTest(unittest.TestCase):
    def test_moi_tai_lieu_tim_duoc_bang_cau_hoi_ma_hoa_dung_ngon_ngu(self) -> None:
        raw = QdrantClient(":memory:")
        svc = DocumentService.__new__(DocumentService)
        svc._qdrant = QdrantVectorClient("http://x", sync_client=raw)  # type: ignore[attr-defined]
        svc.collection = settings.QDRANT_DOCUMENT_COLLECTION  # type: ignore[misc]
        svc.ensure_collection(4)
        vec = [1.0, 0.0, 0.0, 0.0]
        svc.upsert_chunks("en-doc", [{"chunk_id": "a", "text": "Treatments of plaque psoriasis"}], [vec], {}, language="en")
        svc.upsert_chunks("vi-doc", [{"chunk_id": "b", "text": "Điều trị vảy nến mảng bám"}], [vec], {}, language="vi")

        def find(query: str, mode: str) -> list[str]:
            res = raw.query_points(svc.collection, query=encode_query(query, mode), using=SPARSE_NAME,
                                   query_filter=eq_filter("bm25_mode", mode), limit=5)
            return [str(p.payload["document_id"]) for p in res.points if p.payload]

        self.assertEqual(find("treatment of psoriasis", "en"), ["en-doc"])
        self.assertEqual(find("điều trị vảy nến", "vi"), ["vi-doc"])
        self.assertEqual(find("điều trị vảy nến", "en"), [])
        self.assertEqual(find("dieu tri vay nen", "vi"), ["vi-doc"])  # không dấu vẫn khớp nhờ token bỏ dấu


if __name__ == "__main__":
    unittest.main()
