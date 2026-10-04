"""Test lưu trữ (MinIO qua MemoryMinio) và bước lưu vào kho tri thức (Qdrant in-memory + embedding giả).

python -m unittest pipeline.document_ingest.tests.test_storage_index -v"""

import unittest

from app.services.document_service import DocumentService

from app.infra.qdrant_client import eq_filter
from app.exception.errors import PipelineError

from pipeline.document_ingest.profile import default_profile
from pipeline.document_ingest.stages import StageError
from pipeline.document_ingest.tests.test_document_pipeline import DIM, Base, FakeEmbedding, _pages

class StorageTest(Base):
    def test_records_in_db_and_files_in_object_store(self) -> None:
        self.run_toc({"pages": "2-3"})
        keys = set(self.minio.objects)
        for name in ("pages.jsonl", "toc.auto.json", "toc.json", "logs/toc.log"):
            self.assertIn(f"document/tbook/{name}", keys)
        for name in ("book.json", "profile.yaml", "status.json"):  # bản ghi nằm trong DB, không còn file
            self.assertNotIn(f"document/tbook/{name}", keys)
        self.assertEqual(self.repo.list_ids(), ["tbook"])
        self.assertEqual(self.repo.status(self.document_id)["stages"]["toc"]["state"], "pending_review")
        self.assertEqual(DocumentService.read_profile(self.repo, self.document_id).document_id, "tbook")

    def test_log_is_written_then_reset_on_rerun(self) -> None:
        self.repo.reset_log(self.document_id, "toc")
        self.repo.append_log(self.document_id, "toc", "một")
        self.repo.append_log(self.document_id, "toc", "hai")
        tail = self.repo.tail_log(self.document_id, "toc")
        self.assertTrue(
            tail.splitlines()[0].endswith("một")
            and tail.splitlines()[1].endswith("hai")
        )
        self.repo.reset_log(self.document_id, "toc")
        self.assertEqual(self.repo.tail_log(self.document_id, "toc"), "")

    def test_local_pdf_is_a_temp_copy_reused_until_the_object_changes(
        self,
    ) -> None:
        self.files.put_bytes("source.pdf", b"%PDF-one")
        p = DocumentService.local_pdf(self.repo, self.document_id)
        self.assertEqual(p.read_bytes(), b"%PDF-one")
        self.files.put_bytes("source.pdf", b"%PDF-changed")
        self.assertEqual(DocumentService.local_pdf(self.repo, self.document_id).read_bytes(), b"%PDF-changed")
        self.runner.documentService.delete_document("tbook")
        self.assertFalse(p.exists())

    def test_path_traversal_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.files.key("../other/book.json")


class IndexTest(Base):
    def setUp(self) -> None:
        super().setUp()
        self.run_toc({"pages": "2-3"})
        self.fix_pustular()
        self.runner.run_stage("tbook", "chunks", {}, force=True)

    def points(self, book: str = "tbook") -> list:
        pts, _ = self.qdrant.sync_client.scroll(
            self.vectors.collection,
            scroll_filter=eq_filter("document_id", book),
            limit=1000,
            with_payload=True,
        )
        return pts

    def test_chunks_become_points_with_toc_metadata_and_source_location(
        self,
    ) -> None:
        out = self.runner.run_stage("tbook", "index", {}, force=True)
        chunks = self.files.read_jsonl("chunks.jsonl")
        self.assertEqual((out["points"], out["dimension"]), (len(chunks), DIM))
        pts = {p.payload["chunk_id"]: p.payload for p in self.points()}
        c = next(x for x in chunks if x["topic"] == "Atopic Dermatitis")
        pl = pts[c["chunk_id"]]
        self.assertEqual(
            (pl["part"], pl["section"], pl["topic"]),
            (c["part"], c["section"], c["topic"]),
        )
        self.assertEqual(
            (pl["page_start"], pl["pages_hint"], pl["document_id"]),
            (c["page_start"], c["pages_hint"], "tbook"),
        )
        self.assertEqual(pl["source_pdf"], "document/tbook/source.pdf")
        info = self.files.read_json("index.json")
        self.assertEqual(
            (info["points"], info["embedding_model"]),
            (len(chunks), "fake-embed"),
        )

    def test_reindex_replaces_stale_points_of_the_same_document_only(self) -> None:
        self.runner.run_stage("tbook", "index", {}, force=True)
        self.repo.create("Other", {}, default_profile("obook"), {}, document_id="obook")
        self.vectors.upsert_chunks(
            "obook",
            [{"chunk_id": "obook:c1", "text": "x", "context_text": "x"}],
            FakeEmbedding().embed(["x"])[0],
            {},
        )
        self.assertIn(
            "Contact Dermatitis", {p.payload["topic"] for p in self.points()}
        )
        # xoá mục Contact Dermatitis rồi chia lại: ít đoạn hơn
        ents = self.files.read_json("toc.json")["entries"]
        self.repo.overrides.update(self.document_id, 
            "toc",
            {
                "_deleted": [
                    next(
                        e["id"]
                        for e in ents
                        if e["title"] == "Contact Dermatitis"
                    )
                ]
            },
        )
        self.runner.reapply("tbook", "toc")
        self.runner.run_stage("tbook", "chunks", {}, force=True)
        out = self.runner.run_stage("tbook", "index", {}, force=True)
        self.assertEqual(len(self.points()), out["points"])
        self.assertNotIn(
            "Contact Dermatitis", {p.payload["topic"] for p in self.points()}
        )  # đoạn cũ không còn sót
        self.assertEqual(
            len(self.points("obook")), 1
        )  # sách khác không bị đụng

    def test_delete_document_removes_objects_and_points(self) -> None:
        self.runner.run_stage("tbook", "index", {}, force=True)
        self.assertTrue(self.points())
        self.runner.documentService.delete_document("tbook")
        self.assertEqual(self.points(), [])
        self.assertEqual(
            [k for k in self.minio.objects if k.startswith("document/tbook/")], []
        )

    def test_index_needs_chunks_and_is_gated(self) -> None:
        self.files.delete("chunks.jsonl")
        with self.assertRaises(StageError):
            self.runner.run_stage("tbook", "index", {}, force=True)
        with self.assertRaises(PipelineError):
            self.runner.run_stage("tbook", "index", {})  # chunks chưa được xác nhận

    def test_rerunning_chunks_makes_index_stale(self) -> None:
        self.runner.run_stage("tbook", "index", {}, force=True)
        self.runner.approve("tbook", "index")
        self.runner.run_stage("tbook", "chunks", {}, force=True)
        self.assertEqual(
            self.repo.status(self.document_id)["stages"]["index"]["state"], "stale"
        )
        self.assertTrue(_pages())


if __name__ == "__main__":
    unittest.main()
