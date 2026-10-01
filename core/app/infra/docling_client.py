"""Docling dùng chung: class `DoclingClient` = converter (layout + OCR, cache theo cấu hình) + capability chuyển PDF thành các khối chữ theo
thứ tự đọc. Dùng khi lớp text ẩn của PDF hỏng: Docling OCR lại từ ảnh trang. Import Docling/torch rất chậm nên nằm trong hàm. Chạy ĐỒNG BỘ.
Instance do `app/api/deps.py` tạo."""
from pathlib import Path
from typing import Any

# nhãn Docling -> nhãn của pipeline (nhãn khác, vd ảnh, bị bỏ)
_LABELS = {
    "section_header": "heading", "title": "heading", "text": "text", "paragraph": "text", "list_item": "list",
    "caption": "caption", "footnote": "text", "formula": "text", "code": "text", "table": "table",
    "document_index": "toc", "page_header": "page_header", "page_footer": "page_footer",
}


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
            self._converters[key] = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
        return self._converters[key]

    def convert_pages(self, pdf: Path, first: int, last: int, *, ocr: bool = True, force_ocr: bool = True,
                          tables: bool = True) -> list[dict[str, Any]]:
        """Chuyển trang [first, last] (đánh số từ 1). Mỗi khối: {page, label, text}; bảng/mục lục là Markdown."""
        doc = self.converter(ocr, force_ocr, tables).convert(str(pdf), page_range=(first, last)).document
        blocks: list[dict[str, Any]] = []
        for item, _lvl in doc.iterate_items():
            if not item.prov:
                continue
            label = _LABELS.get(str(item.label).split(".")[-1].lower())
            if label is None:
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
