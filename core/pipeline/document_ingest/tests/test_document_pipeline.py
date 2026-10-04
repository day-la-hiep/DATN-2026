"""Test luồng mục lục: LLM đọc mục lục -> độ lệch + neo (luật) -> chunk theo khung mục lục.

LLM giả + sách tổng hợp (không cần PDF/mạng). Chạy từ `core/`:
    python -m unittest pipeline.document_ingest.tests.test_document_pipeline -v"""

import hashlib
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from qdrant_client import QdrantClient

from app.infra.qdrant_client import QdrantVectorClient
from app.services.document_service import DocumentService
from app.infra.llm_client import LLMClient, LLMError
from app.exception.errors import PipelineError
from app.services.document_service import temp_root
from app.repositories.document_repository import DocumentRepository
from app.services.file_store_service import FileStoreService
from app.services.document_ingest_pipeline_service import DocumentIngestPipelineService

from pipeline.document_ingest.profile import default_profile
from pipeline.document_ingest.stages import StageError
from pipeline.document_ingest.stages import toc as T
from pipeline.document_ingest.stages.chunks import build_chunks, est_tokens, toc_nodes
from pipeline.document_ingest.tests.memory_infra import MemoryMinio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base as BaseModel
from app.models.document import Document, DocumentOverride, DocumentStage

TOC_ROWS = [
    "| PART I GENERAL DERMATOLOGY | |",
    "| SECTION 1 ECZEMA | 1 |",
    "| Contact Dermatitis | 1 |",
    "| Atopic Dermatitis | 3 |",
    "| SECTION 2 PSORIASIS | 5 |",
    "| Psoriasis Vulgaris | 5 |",
    "| Pustular Psoriasis | 2 |",  # OCR sai chữ số (đúng là 7): trang lùi so với mục trước nên bị đánh dấu nghi ngờ
]
BODY = {  # trang PDF -> dòng đầu; độ lệch thật = 3 (trang in 1 = PDF 4)
    4: ["SECTION 1 ECZEMA", "Contact Dermatitis"],
    6: ["Atopic Dermatitis"],
    8: ["SECTION 2 PSORIASIS", "Psoriasis Vulgaris"],
    10: ["Pustular Psoriasis"],
}


def _pages() -> list[dict]:
    rows = [
        {"page": 1, "text": "TITLE PAGE OF THE BOOK"},
        {"page": 2, "text": "CONTENTS\n" + "\n".join(TOC_ROWS[:4])},
        {"page": 3, "text": "\n".join(TOC_ROWS[4:])},
    ]
    for n in range(4, 12):
        head = BODY.get(n, [])
        rows.append(
            {
                "page": n,
                "text": "\n".join(
                    [
                        *head,
                        f"Body paragraph of page {n} with enough words to count as running text.",
                    ]
                ),
            }
        )
    return [
        {
            **r,
            "page_printed": r["page"],
            "header": "",
            "noise": False,
            "noise_reason": None,
            "noise_score": 0.0,
        }
        for r in rows
    ]


def toc_llm(system: str, user: str) -> str:
    if "MỤC LỤC (danh sách" in system:
        return json.dumps(
            {
                "toc_pages": [2, 3],
                "reason": "có CONTENTS và các hàng tên | số trang",
            }
        )
    if "đọc các trang MỤC LỤC" in system:
        entries = []
        for pg in json.loads(user.split("(JSON):\n", 1)[1])["pages"]:
            for line in pg["text"].split("\n"):
                m = re.match(r"\|\s*(.+?)\s*\|\s*(\d+)?\s*\|", line)
                if m:
                    t = m.group(1)
                    entries.append(
                        {
                            "level": 0
                            if t.startswith("PART")
                            else 1
                            if t.startswith("SECTION")
                            else 2,
                            "title": t,
                            "printed_page": int(m.group(2))
                            if m.group(2)
                            else None,
                        }
                    )
        return json.dumps({"entries": entries})
    raise AssertionError("prompt lạ: " + system[:60])


DIM = 8


class FakeEmbedding:
    """Thay `EmbeddingClient` thật: vector giả, ổn định theo nội dung."""

    def embed(self, texts: list[str]) -> tuple[list[list[float]], int, str]:
        out = []
        for text in texts:
            h = hashlib.sha256(text.encode()).digest()
            v = [b / 255 + 0.01 for b in h[:DIM]]
            n = sum(x * x for x in v) ** 0.5
            out.append([x / n for x in v])
        return out, DIM, "fake-embed"


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        # mọi phụ thuộc được dựng bằng constructor: MinIO giả (bộ nhớ), Qdrant in-memory, embedding giả
        self.minio = MemoryMinio()
        self.qdrant = QdrantVectorClient("http://unused", sync_client=QdrantClient(":memory:"))
        # Postgres thay bằng SQLite file tạm (chỉ các bảng sách; thread nền của test API cũng dùng được)
        engine = create_engine(f"sqlite:///{root / 'documents.db'}")
        BaseModel.metadata.create_all(engine, tables=[Document.__table__, DocumentStage.__table__, DocumentOverride.__table__])  # type: ignore[list-item]
        self.addCleanup(engine.dispose)
        self.repo = DocumentRepository(FileStoreService(self.minio, "books-test"), sessionmaker(bind=engine, expire_on_commit=False))  # type: ignore[arg-type]
        self.vectors = DocumentService(self.repo, self.qdrant, "document_chunks_test")  # type: ignore[arg-type]
        self.runner = DocumentIngestPipelineService(self.vectors, self.repo, embedding=FakeEmbedding())  # type: ignore[arg-type]
        self.addCleanup(lambda: shutil.rmtree(temp_root() / "tbook", ignore_errors=True))
        self.document_id = "tbook"
        self.files = self.repo.files_for("tbook")
        self.repo.create("Test", {}, default_profile("tbook"), {}, document_id="tbook")
        self.files.write_jsonl("pages.jsonl", _pages())
        self.llm = LLMClient("fake", cache_dir=root / "_cache", fn=toc_llm)

    def run_toc(
        self, opts: dict | None = None, llm: LLMClient | None = None
    ) -> dict:
        return self.runner.run_stage(
            "tbook", "toc", opts or {}, force=True, llm=llm or self.llm
        )

    def fix_pustular(self) -> None:
        pid = next(
            x["id"]
            for x in self.files.read_json("toc.json")["entries"]
            if x["title"] == "Pustular Psoriasis"
        )
        self.repo.overrides.update("tbook", "toc", {pid: {"printed_page": 7}})
        self.runner.reapply("tbook", "toc")


class TocStageTest(Base):
    def test_user_pages_skip_the_page_finder(self) -> None:
        calls: list[str] = []

        def spy(system: str, user: str) -> str:
            calls.append(system[:20])
            return toc_llm(system, user)

        out = self.run_toc(
            {"pages": "2-3"},
            LLMClient("fake", cache_dir=Path(self.tmp.name) / "_spy", fn=spy),
        )
        self.assertEqual(
            (out["tocPages"], out["pagesSource"], out["entries"]),
            ("2-3", "user", 7),
        )
        self.assertTrue(all("tìm" not in c for c in calls))

    def test_llm_finds_toc_pages_and_builds_tree(self) -> None:
        out = self.run_toc()
        self.assertEqual(
            (out["tocPages"], out["pagesSource"]), ("2-3", "llm")
        )
        e = {x["title"]: x for x in self.files.read_json("toc.json")["entries"]}
        self.assertEqual(
            (out["parts"], out["sections"], out["topics"]), (1, 2, 4)
        )
        self.assertEqual(
            e["Atopic Dermatitis"]["path"],
            [
                "PART I GENERAL DERMATOLOGY",
                "SECTION 1 ECZEMA",
                "Atopic Dermatitis",
            ],
        )
        self.assertEqual(
            e["Psoriasis Vulgaris"]["parent_id"], e["SECTION 2 PSORIASIS"]["id"]
        )

    def test_suspect_page_flagged_and_fix_is_anchored(self) -> None:
        out = self.run_toc({"pages": "2-3"})
        bad = next(
            x
            for x in self.files.read_json("toc.json")["entries"]
            if x["title"] == "Pustular Psoriasis"
        )
        self.assertTrue(bad["suspect"])
        self.assertEqual(out["suspect"], 1)
        self.repo.overrides.update(self.document_id, "toc", {bad["id"]: {"printed_page": 7}})
        self.assertEqual(self.runner.reapply("tbook", "toc")["suspect"], 0)
        fixed = next(
            x
            for x in self.files.read_json("toc.json")["entries"]
            if x["id"] == bad["id"]
        )
        self.assertEqual(
            (fixed["printed_page"], fixed["pdf_page"], fixed["anchored"]),
            (7, 10, True),
        )

    def test_offset_voted_from_body_and_user_override_wins(self) -> None:
        out = self.run_toc({"pages": "2-3"})
        self.assertEqual(out["offset"], 3)
        self.assertEqual(
            self.files.read_json("toc.json")["offset_info"]["source"], "auto"
        )
        self.assertGreaterEqual(out["anchored"], 5)
        self.repo.overrides.update(self.document_id, "toc", {"_offset": 4})
        self.runner.reapply("tbook", "toc")
        doc = self.files.read_json("toc.json")
        self.assertEqual(
            (doc["offset"], doc["offset_info"]["source"]), (4, "user")
        )

    def test_part_and_section_without_page_are_anchored_by_title(self) -> None:
        self.run_toc({"pages": "2-3"})
        e = {x["title"]: x for x in self.files.read_json("toc.json")["entries"]}
        sec = e[
            "SECTION 2 PSORIASIS"
        ]  # có số trang 5 nên neo bằng số trang; part không có số trang
        self.assertTrue(sec["anchored"])
        self.assertEqual((sec["pdf_page"], sec["anchor_line"]), (8, 0))

    def test_heading_glued_to_following_text_is_anchored_only_when_uppercase(
        self,
    ) -> None:
        pages = _pages()
        pages[9]["text"] = (
            "PUSTULAR PSORIASIS ICD-10: L40.1 • A rare and severe form of psoriasis with sterile pustules on the palms and soles.\nbody"
        )
        self.files.write_jsonl(
            "pages.jsonl", pages
        )  # trang 10 (PDF) = tiêu đề viết HOA dính liền đoạn văn
        self.run_toc({"pages": "2-3"})
        self.fix_pustular()
        e = next(
            x
            for x in self.files.read_json("toc.json")["entries"]
            if x["title"] == "Pustular Psoriasis"
        )
        self.assertEqual(
            (e["pdf_page"], e["anchor_line"], e["anchored"]), (10, 0, True)
        )
        pages[9]["text"] = (
            "Pustular psoriasis is a rare and severe form of psoriasis with sterile pustules on the palms and soles of patients.\nbody"
        )
        self.files.write_jsonl(
            "pages.jsonl", pages
        )  # câu văn thường mở đầu bằng tên bệnh: KHÔNG phải tiêu đề
        self.runner.reapply("tbook", "toc")
        e = next(
            x
            for x in self.files.read_json("toc.json")["entries"]
            if x["title"] == "Pustular Psoriasis"
        )
        self.assertFalse(e["anchored"])

    def test_no_pages_yet_means_no_offset_not_a_guess(self) -> None:
        self.files.delete("pages.jsonl")
        self.files.write_jsonl(
            "pages.jsonl", [r for r in _pages() if r["page"] <= 3]
        )  # chỉ có trang mục lục
        out = self.run_toc({"pages": "2-3"})
        self.assertIsNone(out["offset"])
        self.assertTrue(any("độ chênh lệch" in w for w in out["warnings"]))

    def test_delete_and_add_entries(self) -> None:
        self.run_toc({"pages": "2-3"})
        ents = self.files.read_json("toc.json")["entries"]
        vulgaris = next(x for x in ents if x["title"] == "Psoriasis Vulgaris")
        self.repo.overrides.update(self.document_id, 
            "toc",
            {
                "_deleted": [ents[0]["id"]],
                "_added": [
                    {
                        "id": "x1",
                        "title": "Nail Psoriasis",
                        "level": 2,
                        "printed_page": 6,
                        "after": vulgaris["id"],
                    }
                ],
            },
        )
        self.runner.reapply("tbook", "toc")
        titles = [
            x["title"] for x in self.files.read_json("toc.json")["entries"]
        ]
        self.assertNotIn("PART I GENERAL DERMATOLOGY", titles)
        self.assertEqual(
            titles[titles.index("Psoriasis Vulgaris") + 1], "Nail Psoriasis"
        )

    def test_llm_failure_on_a_page_is_reported_not_lost(self) -> None:
        def flaky(system: str, user: str) -> str:
            if (
                "đọc các trang MỤC LỤC" in system
                and '"page": 3,' in user
                and '"page": 2,' not in user
            ):
                raise LLMError("hỏng")
            return toc_llm(system, user)

        pages = _pages()
        pages[1]["text"] += "\n" + "x" * 9000  # ép đọc từng trang
        self.files.write_jsonl("pages.jsonl", pages)
        out = self.run_toc(
            {"pages": "2-3"},
            LLMClient("fake", cache_dir=Path(self.tmp.name) / "_fl", fn=flaky),
        )
        self.assertTrue(any("trang mục lục 3" in w for w in out["warnings"]))
        self.assertEqual(out["entries"], 4)

    def test_flag_suspects_keeps_the_longest_increasing_run(self) -> None:
        ents = [{"printed_page": p} for p in (1, 2, 3, 99, 4, 5, 2, 6)]
        T.flag_suspects(ents)
        self.assertEqual(
            [i for i, e in enumerate(ents) if e["suspect"]], [3, 6]
        )


class ChunksTest(Base):
    def chunks(self) -> list[dict]:
        self.run_toc({"pages": "2-3"})
        self.fix_pustular()
        out = self.runner.run_stage("tbook", "chunks", {}, force=True)
        self.assertEqual(out["offset"], 3)
        return self.files.read_jsonl("chunks.jsonl")

    def test_chunks_carry_part_section_topic_and_pages(self) -> None:
        chunks = self.chunks()
        self.assertFalse(
            any(
                "CONTENTS" in c["text"] or "| SECTION" in c["text"]
                for c in chunks
            )
        )
        atopic = next(c for c in chunks if c["topic"] == "Atopic Dermatitis")
        self.assertEqual(
            (atopic["part"], atopic["section"]),
            ("PART I GENERAL DERMATOLOGY", "SECTION 1 ECZEMA"),
        )
        self.assertEqual(
            (atopic["page_start"], atopic["page_end"]), (6, 7)
        )  # tới trước mục kế (Section 2 ở PDF 8)
        self.assertEqual(
            (atopic["page_printed_start"], atopic["boundary"]), (3, False)
        )
        self.assertEqual(atopic["pages_hint"], [6, 8])
        self.assertEqual(atopic["toc_path"][-1], "Atopic Dermatitis")
        pust = next(c for c in chunks if c["topic"] == "Pustular Psoriasis")
        self.assertEqual(pust["section"], "SECTION 2 PSORIASIS")
        self.assertIn("running text", pust["text"])

    def test_no_chunk_crosses_a_toc_boundary(self) -> None:
        for c in self.chunks():
            self.assertEqual(len(c["toc_node_ids"]), 1)
        text = {c["topic"]: c["text"] for c in self.chunks() if c["topic"]}
        self.assertNotIn(
            "Body paragraph of page 8", text["Atopic Dermatitis"]
        )  # trang 8 thuộc Section 2
        self.assertNotIn("Atopic", text["Contact Dermatitis"])

    def test_text_before_first_entry_is_reported_not_silently_dropped(
        self,
    ) -> None:
        self.run_toc({"pages": "2-3"})
        out = self.runner.run_stage("tbook", "chunks", {}, force=True)
        self.assertEqual(out["outsideTocLines"], 1)  # trang bìa
        self.assertTrue(any("trước mục đầu tiên" in w for w in out["warnings"]))

    def test_unanchored_entry_is_marked_boundary_and_queued_for_review(
        self,
    ) -> None:
        self.run_toc({"pages": "2-3"})  # Pustular chưa sửa: nghi ngờ + chưa neo
        out = self.runner.run_stage("tbook", "chunks", {}, force=True)
        self.assertGreaterEqual(out["boundaryChunks"], 1)
        review = self.files.read_json("review/chunks.json")
        self.assertTrue(
            any(
                "vị trí bắt đầu" in r["reason"] or "cần kiểm tra" in r["reason"]
                for r in review
            )
        )

    def test_max_tokens_splits_inside_an_entry_only(self) -> None:
        prof = default_profile("tbook")
        prof.chunking.max_tokens = 50
        DocumentService.save_profile(self.repo, self.document_id, prof)
        long = [
            {
                **r,
                "text": r["text"]
                + "\n"
                + " ".join(f"word{i}" for i in range(60))
                + ".",
            }
            for r in _pages()
        ]
        self.files.write_jsonl("pages.jsonl", long)
        chunks = self.chunks()
        self.assertTrue(all(c["tokens"] <= 60 for c in chunks))
        pust = [c for c in chunks if c["topic"] == "Pustular Psoriasis"]
        self.assertGreater(len(pust), 1)
        self.assertEqual({c["section"] for c in pust}, {"SECTION 2 PSORIASIS"})

    def test_boundary_level_merges_deep_entries_into_their_parent_region(
        self,
    ) -> None:
        self.run_toc({"pages": "2-3"})
        self.fix_pustular()
        doc = self.files.read_json("toc.json")
        prof = default_profile("tbook")
        prof.chunking.boundary_level = 1  # chỉ part/section là ranh giới: các mục bệnh trong cùng section được gom
        units = [
            (r["page"], i, ln)
            for r in self.files.read_jsonl("pages.jsonl")
            if r["page"] > 3
            for i, ln in enumerate(r["text"].split("\n"))
        ]
        chunks, _ = build_chunks(
            toc_nodes(doc, 11),
            units,
            prof.chunking,
            document_id="tbook",
            document_title="Test",
            printed_offset=3,
        )
        merged = next(c for c in chunks if c["section"] == "SECTION 1 ECZEMA")
        self.assertGreaterEqual(len(merged["toc_node_ids"]), 2)
        self.assertEqual(
            merged["toc_path"][-1], "SECTION 1 ECZEMA"
        )  # tiền tố chung của các mục gom lại
        self.assertTrue(
            all(
                c["section"] == "SECTION 1 ECZEMA"
                for c in chunks
                if "SECTION 1 ECZEMA" in c["text"]
            )
        )

    def test_missing_offset_stops_with_a_clear_error(self) -> None:
        self.run_toc({"pages": "2-3"})
        self.repo.overrides.update(self.document_id, 
            "toc", {"_offset": 200}
        )  # mọi mục rơi ra ngoài file
        self.runner.reapply("tbook", "toc")
        with self.assertRaises(StageError):
            self.runner.run_stage("tbook", "chunks", {}, force=True)

    def test_est_tokens_is_monotonic(self) -> None:
        self.assertLess(est_tokens("a b c"), est_tokens("a b c d e f g h"))


class RunnerGateTest(Base):
    def test_chunks_blocked_until_ingest_and_toc_approved(self) -> None:
        with self.assertRaises(PipelineError):
            self.runner.run_stage("tbook", "chunks", {})
        self.assertEqual(
            DocumentService.blocking_deps(self.repo, self.document_id, "chunks"), ["ingest", "toc"]
        )
        self.assertEqual(DocumentService.blocking_deps(self.repo, self.document_id, "toc"), [])

    def test_rerunning_toc_makes_chunks_stale(self) -> None:
        self.run_toc({"pages": "2-3"})
        self.runner.approve("tbook", "toc")
        self.runner.run_stage("tbook", "chunks", {}, force=True)
        self.run_toc({"pages": "2-3"})
        self.assertEqual(
            self.repo.status(self.document_id)["stages"]["chunks"]["state"], "stale"
        )


if __name__ == "__main__":
    unittest.main()
