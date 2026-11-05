"""Reading CV files: PDF (text layer, or OCR for scanned pages), Word, plain text and images.

The file type comes from the first bytes, not the name, so a renamed file cannot pick its own parser.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field

from PIL import Image, UnidentifiedImageError

from clearhire.ingest.ocr import OcrError, TesseractOcr
from clearhire.text import clean_text

__all__ = ["ParsedDocument", "TesseractOcr", "UnreadableDocument", "detect_type", "read_document"]

MIN_PAGE_TEXT = 40  # characters; below this a PDF page counts as scanned
OCR_DPI = 300


class UnreadableDocument(ValueError):
    """The file is not a supported type, is damaged, or needs OCR that is not available."""


@dataclass
class ParsedDocument:
    text: str
    media_type: str  # pdf | docx | text | image
    pages: list[tuple[int, int]] = field(default_factory=list)  # [start, end) of each page in `text`
    ocr_pages: list[int] = field(default_factory=list)  # 1-based numbers of pages read with OCR
    ocr_confidence: float | None = None  # mean Tesseract word confidence over those pages

    def page_of(self, offset: int) -> int | None:
        for number, (start, end) in enumerate(self.pages, start=1):
            if start <= offset < end or (offset == end and number == len(self.pages)):
                return number
        return None


def detect_type(data: bytes) -> str:
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if "word/document.xml" in archive.namelist():
                    return "docx"
        except zipfile.BadZipFile:
            pass
        raise UnreadableDocument("a ZIP file that is not a Word document")
    if (
        data[:8] == b"\x89PNG\r\n\x1a\n"
        or data[:3] == b"\xff\xd8\xff"
        or data[:4] in (b"II*\x00", b"MM\x00*")
    ):
        return "image"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image"
    try:
        data[:4096].decode("utf-8")
    except UnicodeDecodeError:
        try:
            data[:4096].decode("cp1251")
        except UnicodeDecodeError as exc:
            raise UnreadableDocument("not a PDF, Word file, image or text") from exc
    if b"\x00" in data[:4096]:
        raise UnreadableDocument("binary data that is not a supported document")
    return "text"


def _join(pages: list[str]) -> tuple[str, list[tuple[int, int]]]:
    parts: list[str] = []
    spans: list[tuple[int, int]] = []
    offset = 0
    for page in pages:
        cleaned = clean_text(page)
        if parts:
            parts.append("\n\n")
            offset += 2
        parts.append(cleaned)
        spans.append((offset, offset + len(cleaned)))
        offset += len(cleaned)
    return "".join(parts), spans


def _read_pdf(data: bytes, ocr: TesseractOcr | None, max_pages: int) -> ParsedDocument:
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        raise UnreadableDocument(f"damaged or encrypted PDF: {exc}") from exc
    pages: list[str] = []
    ocr_pages: list[int] = []
    confidences: list[float] = []
    try:
        if len(pdf) > max_pages:
            raise UnreadableDocument(f"{len(pdf)} pages; a CV may have at most {max_pages}")
        for index in range(len(pdf)):
            page = pdf[index]
            text = page.get_textpage().get_text_bounded()
            if len(text.strip()) < MIN_PAGE_TEXT:
                if ocr is None or not ocr.available:
                    if text.strip():
                        pages.append(text)
                        continue
                    raise UnreadableDocument("the PDF is a scan and OCR is not available")
                image = page.render(scale=OCR_DPI / 72).to_pil()
                try:
                    result = ocr.recognize(image)
                except OcrError as exc:
                    raise UnreadableDocument(f"OCR failed: {exc}") from exc
                text = "\n".join(result.lines)
                ocr_pages.append(index + 1)
                confidences.append(result.confidence)
            pages.append(text)
    finally:
        pdf.close()
    text, spans = _join(pages)
    confidence = round(sum(confidences) / len(confidences), 1) if confidences else None
    return ParsedDocument(text, "pdf", spans, ocr_pages, confidence)


def _read_docx(data: bytes) -> ParsedDocument:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        document = Document(io.BytesIO(data))
    except Exception as exc:  # python-docx raises several unrelated types for damaged files
        raise UnreadableDocument(f"damaged Word file: {exc}") from exc
    lines: list[str] = []
    for block in document.element.body.iterchildren():
        tag = block.tag.rsplit("}", 1)[-1]
        if tag == "p":
            lines.append(Paragraph(block, document).text)
        elif tag == "tbl":
            for row in Table(block, document).rows:
                cells: list[str] = []
                for cell in row.cells:
                    value = cell.text.strip()
                    if value and (not cells or cells[-1] != value):  # merged cells repeat their text
                        cells.append(value)
                lines.append(" | ".join(cells))
    text, spans = _join(["\n".join(lines)])
    return ParsedDocument(text, "docx", spans)


def _read_image(data: bytes, ocr: TesseractOcr | None) -> ParsedDocument:
    if ocr is None or not ocr.available:
        raise UnreadableDocument("an image needs OCR, which is not available")
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise UnreadableDocument(f"damaged image: {exc}") from exc
    try:
        result = ocr.recognize(image)
    except OcrError as exc:
        raise UnreadableDocument(f"OCR failed: {exc}") from exc
    text, spans = _join(["\n".join(result.lines)])
    return ParsedDocument(text, "image", spans, [1], result.confidence)


def _read_text(data: bytes) -> ParsedDocument:
    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError:
        decoded = data.decode("cp1251")
    text, spans = _join([decoded])
    return ParsedDocument(text, "text", spans)


def read_document(data: bytes, *, ocr: TesseractOcr | None = None, max_pages: int = 10) -> ParsedDocument:
    media_type = detect_type(data)
    if media_type == "pdf":
        document = _read_pdf(data, ocr, max_pages)
    elif media_type == "docx":
        document = _read_docx(data)
    elif media_type == "image":
        document = _read_image(data, ocr)
    else:
        document = _read_text(data)
    if not document.text.strip():
        raise UnreadableDocument("no text found in the document")
    return document
