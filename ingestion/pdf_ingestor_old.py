from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

import pdfplumber

from ingestion.base import BaseIngestor, TextChunk
from settings import get_settings

try:
    import ocrmypdf
except ImportError:  # noqa: F401
    ocrmypdf = None

logger = logging.getLogger(__name__)


class PDFIngestor(BaseIngestor):
    def __init__(self) -> None:
        settings = get_settings()
        self.threshold = settings.pdf_ocr_fallback_threshold
        self.digital_page_char_threshold = 120
        self.digital_low_text_ratio = 0.35
        # Track whether OCRmyPDF package is installed and whether the
        # tesseract binary is available on the system PATH. OCRmyPDF
        # requires the `tesseract` executable at runtime.
        self.ocr_installed = ocrmypdf is not None
        self.tesseract_available = shutil.which("tesseract") is not None
        self.ocr_available = self.ocr_installed and self.tesseract_available

    def _markdown_from_page(self, page, page_no: int) -> str:
        words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
        if not words:
            return ""

        lines: dict[int, list[str]] = {}
        for word in words:
            top = int(round(word["top"]))
            lines.setdefault(top, []).append(word["text"])

        sorted_lines = [" ".join(lines[key]).strip() for key in sorted(lines)]
        sorted_lines = [line for line in sorted_lines if line]

        return "\n".join(sorted_lines)

    def read_digital_pdf(self, file_path: str) -> list[TextChunk]:
        """Extract text with layout preservation using pdfplumber."""
        try:
            chunks: list[TextChunk] = []
            with pdfplumber.open(file_path) as pdf:
                for page_no, page in enumerate(pdf.pages, start=1):
                    page_text = self._markdown_from_page(page, page_no)
                    if not page_text.strip():
                        continue

                    chunks.append(
                        TextChunk(
                            chunk_id=page_no,
                            text=page_text.strip(),
                            metadata={
                                "page": page_no,
                                "reading_medium": "pdfplumber",
                                "original_document_format": "PDF",
                                "original_page_text_length": len(page_text.strip()),
                            },
                        )
                    )
            return chunks
        except Exception as e:
            logger.exception(
                "Failed digital extraction for %s due to unexpected exception: %s",
                file_path,
                e,
            )
            return []

    def read_scanned_pdf(self, file_path: str) -> list[TextChunk]:
        """Use OCRmyPDF then extract structured text with pdfplumber."""
        if not self.ocr_installed:
            raise RuntimeError(
                "OCRmyPDF is not installed. Install it to use scanned PDF fallback."
            )

        if not self.tesseract_available:
            raise RuntimeError(
                "Tesseract executable not found on PATH. Install Tesseract-OCR and ensure 'tesseract' is on PATH. "
                "On Windows, add the Tesseract installation directory (for example, C:\\Program Files\\Tesseract-OCR) to your PATH."
            )

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
                temp_path = tmp_pdf.name
                try:
                    ocrmypdf.ocr(
                        file_path,
                        temp_path,
                        deskew=True,
                        force_ocr=True,
                        optimize=0,
                    )
                except Exception as e:
                    logger.exception("OCRmyPDF failed for %s: %s", file_path, e)
                    raise RuntimeError(
                        "OCR failed: ensure OCRmyPDF and Tesseract are installed and available on PATH"
                    ) from e

            return self.read_digital_pdf(temp_path)
        finally:
            if temp_path and Path(temp_path).exists():
                try:
                    Path(temp_path).unlink()
                except Exception:
                    logger.warning("Failed to delete temporary OCR file: %s", temp_path)

    def _should_fallback_to_ocr(
        self, chunks: list[TextChunk], total_pages: int
    ) -> bool:
        if not chunks:
            return True

        total_text = sum(len(chunk.text) for chunk in chunks)
        if total_text < self.threshold:
            return True

        low_text_pages = sum(
            1
            for chunk in chunks
            if len(chunk.text.strip()) < self.digital_page_char_threshold
        )
        if low_text_pages / max(1, total_pages) >= self.digital_low_text_ratio:
            return True

        return False

    async def ingest(self, file_path: str) -> list[TextChunk]:
        if not Path(file_path).exists():
            raise FileNotFoundError(f"Target ingestion artifact not found: {file_path}")

        logger.info("PDF Ingestor Processing: %s", file_path)

        chunks = await asyncio.to_thread(self.read_digital_pdf, file_path)
        total_pages = len(chunks)

        if self._should_fallback_to_ocr(chunks, total_pages):
            logger.warning(
                "Fallback to OCR: digital extraction was low quality (%d pages, %d chars).",
                total_pages,
                sum(len(chunk.text) for chunk in chunks),
            )
            chunks = await asyncio.to_thread(self.read_scanned_pdf, file_path)

        logger.info(
            "PDF Ingestor Core complete: Extracted %d structural chunks", len(chunks)
        )
        return chunks
