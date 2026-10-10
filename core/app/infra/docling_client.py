"""Docling dùng chung"""
import io
from pathlib import Path
from typing import Any

# nhãn Docling -> nhãn của pipeline (nhãn khác bị bỏ). `picture` thành "figure": ảnh được lưu riêng, không vào chữ thân
_LABELS = {
    "section_header": "heading", "title": "heading", "text": "text", "paragraph": "text", "list_item": "list",
    "caption": "caption", "footnote": "text", "formula": "text", "code": "text", "table": "table",
    "document_index": "toc", "page_header": "page_header", "page_footer": "page_footer", "picture": "figure",
}


def _figure_block(doc: Any, item: Any) -> list[dict[str, Any]]:
    """Một hình minh hoạ -> khối "figure". Hình Docling không xuất được ảnh (None) thì bỏ, không có gì để lưu."""
    img = item.get_image(doc)
    if img is None:
        return []
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    box = item.prov[0].bbox
    return [{"page": item.prov[0].page_no, "label": "figure", "text": " ".join((item.caption_text(doc) or "").split()),
             "bbox": [box.l, box.t, box.r, box.b], "image_png": buf.getvalue()}]


class DoclingClient:
    def __init__(self) -> None:
        self._converters: dict[tuple[bool, bool, bool], Any] = {}

    def converter(self, ocr: bool, force_ocr: bool, tables: bool) -> Any:
        key = (ocr, force_ocr, tables)
        if key not in self._converters:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption

            opts = PdfPipelineOptions()
            opts.do_ocr = ocr
            if ocr:
                ocr_opts = RapidOcrOptions()
                ocr_opts.force_full_page_ocr = force_ocr  # không tin lớp text ẩn của PDF
                opts.ocr_options = ocr_opts
            opts.do_table_structure = tables
            opts.generate_picture_images = True  # cần để lấy được ảnh của hình minh hoạ
            self._converters[key] = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
        return self._converters[key]

    def convert_pages(self, pdf: Path, first: int, last: int, *, ocr: bool = True, force_ocr: bool = True,
                          tables: bool = True) -> list[dict[str, Any]]:
        """Chuyển trang [first, last]"""
        doc = self.converter(ocr, force_ocr, tables).convert(str(pdf), page_range=(first, last)).document
        blocks: list[dict[str, Any]] = []
        for item, _lvl in doc.iterate_items():
            if not item.prov:
                continue
            label = _LABELS.get(str(item.label).split(".")[-1].lower())
            if label is None:
                continue
            if label == "figure":
                blocks.extend(_figure_block(doc, item))
                continue
            if label in {"table", "toc"}:
                try:
                    text = (item.export_to_markdown(doc) or "").strip()
                except Exception:
                    text = ""
            else:
                text = " ".join((getattr(item, "text", "") or "").split())
            if text:
                blocks.append({"page": item.prov[0].page_no, "label": label, "text": text})
        return blocks
