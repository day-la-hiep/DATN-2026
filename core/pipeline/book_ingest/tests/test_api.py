"""Test lớp API/service của luồng mục lục (không cần DB/RabbitMQ: chỉ mount router này).

Bước được chạy trong backend ở thread nền (không còn CLI/subprocess); logic từng bước đã có test_toc_pipeline.
    python -m unittest pipeline.book_ingest.tests.test_api -v"""

import io
import time
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from app.exception.exception_handler import register_exception_handlers
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from app.api.toc_pipeline_api import router
from app.api.deps import get_book_service, get_book_ingest_pipeline_service

from pipeline.book_ingest.tests.test_toc_pipeline import Base


def _pdf(pages: int = 3) -> bytes:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=200, height=300)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


class ApiTest(Base):
    def setUp(self) -> None:
        super().setUp()
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(router, prefix="/api/v1")
        self.c = TestClient(app)
        self.svc = self.runner
        app.dependency_overrides[get_book_ingest_pipeline_service] = lambda: self.svc
        app.dependency_overrides[get_book_service] = lambda: self.vectors  # service dựng bằng runner của test (MinIO/Qdrant giả)
        self.base = "/api/v1/admin/toc-pipeline"

    def seed_chunks(self) -> None:
        self.run_toc({"pages": "2-3"})
        self.fix_pustular()
        self.runner.run_stage("tbook", "chunks", {}, force=True)

    def test_create_validate_get_and_delete_book(self) -> None:
        r = self.c.post(
            f"{self.base}/books",
            data={"title": "Sách thử", "engine": "pdftotext"},
            files={"file": ("a.pdf", _pdf(), "application/pdf")},
        )
        self.assertEqual(r.status_code, 201, r.text)
        book = r.json()["data"]
        self.assertEqual(
            (book["id"], book["pdfPages"], [s["id"] for s in book["stages"]]),
            ("sach-thu", 3, ["ingest", "toc", "chunks", "index"]),
        )
        self.assertEqual(book["stages"][2]["blockedBy"], ["ingest", "toc"])
        bad = self.c.post(
            f"{self.base}/books",
            data={"title": "x"},
            files={"file": ("a.pdf", b"not a pdf", "application/pdf")},
        )
        self.assertEqual(bad.status_code, 422)
        self.assertEqual(
            self.c.post(
                f"{self.base}/books",
                data={"title": "Sách thử", "bookId": "sach-thu"},
                files={"file": ("a.pdf", _pdf(), "application/pdf")},
            ).status_code,
            409,
        )
        self.assertEqual(
            len(self.c.get(f"{self.base}/books").json()["data"]), 2
        )  # sách của Base + sách vừa tạo
        self.assertEqual(
            self.c.delete(f"{self.base}/books/sach-thu").status_code, 204
        )
        self.assertEqual(
            self.c.get(f"{self.base}/books/sach-thu").status_code, 404
        )

    def test_settings_roundtrip_and_validation(self) -> None:
        s = self.c.get(f"{self.base}/books/tbook/settings").json()["data"]
        self.assertEqual(
            (s["engine"], s["maxTokens"], s["boundaryLevel"]),
            ("pdftotext", 400, 3),
        )
        s.update(
            {
                "maxTokens": 200,
                "engine": "docling",
                "title": "Mới",
                "noisePages": ["1-3", " "],
            }
        )
        got = self.c.put(f"{self.base}/books/tbook/settings", json=s).json()[
            "data"
        ]
        self.assertEqual(
            (got["maxTokens"], got["engine"], got["title"], got["noisePages"]),
            (200, "docling", "Mới", ["1-3"]),
        )
        self.assertEqual(
            self.c.get(f"{self.base}/books/tbook").json()["data"]["title"],
            "Mới",
        )
        s["maxTokens"] = 5
        self.assertEqual(
            self.c.put(f"{self.base}/books/tbook/settings", json=s).status_code,
            422,
        )

    def test_toc_edit_becomes_override_and_chunks_are_filterable(self) -> None:
        self.seed_chunks()
        toc = self.c.get(f"{self.base}/books/tbook/toc").json()["data"]
        ents = {e["title"]: e for e in toc["entries"]}
        self.assertEqual(toc["offset"], 3)
        r = self.c.patch(
            f"{self.base}/books/tbook/toc",
            json={
                "items": [
                    {
                        "id": ents["Atopic Dermatitis"]["id"],
                        "title": "Atopic Dermatitis (AD)",
                    }
                ],
                "deleted": [ents["Contact Dermatitis"]["id"]],
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        stages = {s["id"]: s["state"] for s in r.json()["data"]["stages"]}
        self.assertEqual(
            (stages["toc"], stages["chunks"]), ("pending_review", "stale")
        )  # sửa mục lục làm chunk cũ hết hạn
        self.assertEqual(
            self.c.patch(f"{self.base}/books/tbook/toc", json={}).status_code,
            422,
        )
        self.assertEqual(
            self.c.patch(
                f"{self.base}/books/tbook/toc", json={"deleted": ["nope"]}
            ).status_code,
            404,
        )

        self.runner.run_stage("tbook", "chunks", {}, force=True)
        sec = next(
            e
            for e in self.c.get(f"{self.base}/books/tbook/toc").json()["data"][
                "entries"
            ]
            if e["title"] == "SECTION 2 PSORIASIS"
        )
        lst = self.c.get(
            f"{self.base}/books/tbook/chunks", params={"node": sec["id"]}
        ).json()["data"]
        self.assertTrue(
            lst["items"]
            and all(c["section"] == "SECTION 2 PSORIASIS" for c in lst["items"])
        )  # lọc theo nhánh mục lục
        self.assertEqual(lst["counts"]["perNode"][sec["id"]], lst["total"])
        self.assertEqual(
            self.c.get(
                f"{self.base}/books/tbook/chunks", params={"node": "nope"}
            ).status_code,
            404,
        )
        q = self.c.get(
            f"{self.base}/books/tbook/chunks", params={"q": "page 10"}
        ).json()["data"]
        self.assertTrue(q["total"] >= 1)
        exp = self.c.get(f"{self.base}/books/tbook/chunks/export")
        self.assertEqual(
            (exp.status_code, exp.text.count("\n")), (200, lst["counts"]["all"])
        )

    def test_pages_text_and_image(self) -> None:
        self.assertEqual(
            self.c.get(f"{self.base}/books/tbook/pages/2").json()["data"][
                "page"
            ],
            2,
        )
        self.assertEqual(
            self.c.get(f"{self.base}/books/tbook/pages/999").status_code, 404
        )
        self.store.files.put_bytes("source.pdf", _pdf(3))
        img = self.c.get(f"{self.base}/books/tbook/pages/2/image")
        self.assertEqual(
            (img.status_code, img.headers["content-type"], img.content[:4]),
            (200, "image/png", b"\x89PNG"),
        )
        self.assertEqual(
            self.c.get(f"{self.base}/books/tbook/pages/9/image").status_code,
            404,
        )

    def wait_state(
        self,
        stage: str,
        states: set[str],
        timeout: float = 20.0,
        book: str = "tbook",
    ) -> dict:
        end = time.time() + timeout
        while time.time() < end:
            b = self.c.get(f"{self.base}/books/{book}").json()["data"]
            st = next(x for x in b["stages"] if x["id"] == stage)
            if st["state"] in states:
                return st
            time.sleep(0.05)
        self.fail(
            f"bước {stage} không đạt trạng thái {states} trong {timeout}s"
        )

    def test_stage_runs_in_a_background_thread_inside_the_backend(self) -> None:
        self.store.files.put_bytes("source.pdf", _pdf(3))
        r = self.c.post(f"{self.base}/books/tbook/stages/ingest/run", json={})
        self.assertEqual(r.status_code, 202, r.text)
        self.assertEqual(
            next(s for s in r.json()["data"]["stages"] if s["id"] == "ingest")[
                "state"
            ],
            "running",
        )  # trả về ngay
        st = self.wait_state("ingest", {"pending_review", "failed"})
        self.assertEqual(
            (st["state"], st["summary"]["pages"]), ("pending_review", 3)
        )
        self.assertIn(
            "xong",
            self.c.get(f"{self.base}/books/tbook/stages/ingest/log").json()[
                "data"
            ],
        )

    def test_cancel_stops_a_running_stage(self) -> None:
        def slow(ctx):  # noqa: ANN001, ANN202
            for i in range(2000):
                ctx.progress(i, 2000, "đang làm")
                time.sleep(0.01)
            return {}

        with patch("pipeline.book_ingest.stages.ingest.run", slow):
            self.assertEqual(
                self.c.post(
                    f"{self.base}/books/tbook/stages/ingest/run", json={}
                ).status_code,
                202,
            )
            self.assertEqual(
                self.c.post(
                    f"{self.base}/books/tbook/stages/chunks/run", json={}
                ).status_code,
                409,
            )  # đang bận / chưa xác nhận
            self.assertEqual(
                self.c.post(
                    f"{self.base}/books/tbook/stages/ingest/cancel"
                ).status_code,
                200,
            )
            st = self.wait_state("ingest", {"cancelled", "pending_review"})
        self.assertEqual(st["state"], "cancelled")
        self.assertEqual(
            self.c.post(
                f"{self.base}/books/tbook/stages/ingest/cancel"
            ).status_code,
            409,
        )  # không còn chạy

    def test_stage_left_running_without_a_thread_is_marked_failed(self) -> None:
        self.store.update_stage(
            "toc", state="running"
        )  # vd Core vừa khởi động lại: không thread nào chạy bước này
        st = self.wait_state("toc", {"failed"}, timeout=2)
        self.assertIn("dừng bất thường", st["error"])

    def test_run_is_refused_while_blocked_and_unknown_stage_404(self) -> None:
        r = self.c.post(f"{self.base}/books/tbook/stages/chunks/run", json={})
        self.assertEqual(r.status_code, 409)
        self.assertIn("Đọc nội dung", r.json()["detail"])
        self.assertEqual(
            self.c.post(
                f"{self.base}/books/tbook/stages/nope/run", json={}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.c.post(
                f"{self.base}/books/tbook/stages/toc/cancel"
            ).status_code,
            409,
        )


if __name__ == "__main__":
    unittest.main()
