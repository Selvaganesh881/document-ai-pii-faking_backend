from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pdfplumber

try:
    import pymupdf4llm
except ImportError:  # pragma: no cover
    pymupdf4llm = None

from docling.chunking import HierarchicalChunker
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from settings import get_settings

from ingestion.base import BaseIngestor, TextChunk

logger = logging.getLogger(__name__)


class PDFIngestor(BaseIngestor):
    def __init__(self) -> None:
        settings = get_settings()
        self.threshold = settings.pdf_ocr_fallback_threshold
        self.ocr_engine: DocumentConverter | None = None
        self.ocr_lock = asyncio.Lock()

    async def initialize_ocr(self) -> None:
        """Thread-safe lazy initialization of the computationally heavy Docling OCR engine."""
        async with self.ocr_lock:
            if self.ocr_engine is not None:
                return

            def init_ocr() -> DocumentConverter:
                return DocumentConverter(
                    format_options={
                        InputFormat.PDF: PdfFormatOption(
                            pipeline_options=PdfPipelineOptions(do_ocr=True)
                        )
                    }
                )

            logger.info("Initializing high-fidelity Docling OCR Engine...")
            self.ocr_engine = await asyncio.to_thread(init_ocr)
            logger.info("OCR Engine is successfully initialized.")

    def read_digital_pdf(self, file_path: str) -> list[TextChunk]:
        """Fast textual extraction using PyMuPDF4LLM when available, else pdfplumber."""
        # 1. Cast to string to prevent pathlib.Path object compatibility crashes
        file_path_str = str(file_path)

        if pymupdf4llm is not None:
            try:
                # In older versions, this returns a string. In newer versions, a list of dicts.
                result = pymupdf4llm.to_markdown(file_path_str, page_chunks=True)
                chunks: list[TextChunk] = []

                # 2. Defend against older API versions returning a raw string
                if isinstance(result, str):
                    if result.strip():
                        chunks.append(
                            TextChunk(
                                chunk_id=1,
                                text=result.strip(),
                                metadata={
                                    "page": 1,
                                    "reading_medium": "PyMuPDF4LLM (Legacy)",
                                    "original_document_format": "PDF",
                                },
                            )
                        )
                    return chunks

                # 3. Handle the modern API list of dictionaries
                for page in result:
                    text = page.get("text", "")
                    if not text or not text.strip():
                        continue

                    # 4. FIX: PyMuPDF4LLM stores the page number under 'page_number', not 'page'
                    page_meta = page.get("metadata", {})
                    page_no = page_meta.get("page_number", len(chunks) + 1)

                    chunks.append(
                        TextChunk(
                            chunk_id=page_no,
                            text=text.strip(),
                            metadata={
                                "page": page_no,
                                "reading_medium": "PyMuPDF4LLM",
                                "original_document_format": "PDF",
                            },
                        )
                    )
                return chunks

            except Exception as e:
                # 5. FIX: Added exc_info=True so the terminal actually prints the stack trace!
                logger.error(
                    "Failed digital extraction for %s using PyMuPDF4LLM: %s",
                    file_path_str,
                    str(e),
                    exc_info=True,
                )
                # falls through to pdfplumber extraction

        # --- PDFPlumber Fallback ---
        try:
            chunks: list[TextChunk] = []
            with pdfplumber.open(file_path_str) as pdf:
                for page_no, page in enumerate(pdf.pages, start=1):
                    page_text = page.extract_text() or ""
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
                            },
                        )
                    )
            return chunks
        except Exception as e:
            logger.error(
                "Failed digital extraction for %s due to unexpected exception: %s",
                file_path_str,
                str(e),
                exc_info=True,
            )
            return []

    # def read_digital_pdf(self, file_path: str) -> list[TextChunk]:
    #     """Fast textual extraction using PyMuPDF4LLM when available, else pdfplumber."""
    #     if pymupdf4llm is not None:
    #         try:
    #             pages = pymupdf4llm.to_markdown(file_path, page_chunks=True)
    #             chunks: list[TextChunk] = []

    #             for page in pages:
    #                 text = page.get("text", "")
    #                 if not text or not text.strip():
    #                     continue

    #                 # Default to fallback length counter if page metadata is corrupt
    #                 page_meta = page.get("metadata", {})
    #                 page_no = page_meta.get("page", len(chunks))

    #                 chunks.append(
    #                     TextChunk(
    #                         chunk_id=page_no,
    #                         text=text.strip(),
    #                         metadata={
    #                             "page": page_no,
    #                             "reading_medium": "PyMuPDF4LLM",
    #                             "original_document_format": "PDF",
    #                         },
    #                     )
    #                 )
    #             return chunks
    #         except Exception as e:
    #             logger.error(
    #                 "Failed digital extraction for %s using PyMuPDF4LLM: %s",
    #                 file_path,
    #                 str(e),
    #             )
    #             # fall through to pdfplumber extraction

    #     try:
    #         chunks: list[TextChunk] = []
    #         with pdfplumber.open(file_path) as pdf:
    #             for page_no, page in enumerate(pdf.pages, start=1):
    #                 page_text = page.extract_text() or ""
    #                 if not page_text.strip():
    #                     continue

    #                 chunks.append(
    #                     TextChunk(
    #                         chunk_id=page_no,
    #                         text=page_text.strip(),
    #                         metadata={
    #                             "page": page_no,
    #                             "reading_medium": "pdfplumber",
    #                             "original_document_format": "PDF",
    #                         },
    #                     )
    #                 )
    #         return chunks
    #     except Exception as e:
    #         logger.error(
    #             "Failed digital extraction for %s due to unexpected exception: %s",
    #             file_path,
    #             str(e),
    #         )
    #         return []

    def read_scanned_pdf(self, file_path: str) -> list[TextChunk]:
        """Structure-aware chunking and layouts extraction via Docling fallback."""
        if not self.ocr_engine:
            raise RuntimeError("OCR layout engine requested but not instantiated.")

        result = self.ocr_engine.convert(file_path)
        chunker = HierarchicalChunker()
        docling_chunks = chunker.chunk(result.document)

        pages: dict[int, list[str]] = {}

        for chunk in docling_chunks:
            if not chunk.text or not chunk.text.strip():
                continue

            page_no = 0
            if chunk.meta and chunk.meta.doc_items:
                prov = getattr(chunk.meta.doc_items[0], "prov", None)
                if prov and len(prov) > 0 and hasattr(prov[0], "page_no"):
                    page_no = prov[0].page_no

            pages.setdefault(page_no, []).append(chunk.text.strip())

        # CRITICAL: Sort by key (page number) to keep structural sequential context intact
        sorted_chunks = [
            TextChunk(
                chunk_id=page_number,
                text="\n\n".join(texts),
                metadata={
                    "page": page_number,
                    "reading_medium": "Docling",
                    "original_document_format": "PDF",
                },
            )
            for page_number, texts in sorted(pages.items())
        ]

        return sorted_chunks

    async def ingest(self, file_path: str) -> list[TextChunk]:
        if not Path(file_path).exists():
            raise FileNotFoundError(f"Target ingestion artifact not found: {file_path}")

        logger.info("PDF Ingestor Processing: %s", file_path)

        # Execute fast text extraction in worker pool thread
        chunks = await asyncio.to_thread(self.read_digital_pdf, file_path)
        total_text = sum(len(c.text) for c in chunks)

        # Determine fallback threshold criteria (e.g. image-only or low density scans)
        if total_text < self.threshold:
            logger.warning(
                "Digital extraction yielded low density payload (%d chars). Threshold is %d. Falling back to OCR processing.",
                total_text,
                self.threshold,
            )

            await self.initialize_ocr()
            chunks = await asyncio.to_thread(self.read_scanned_pdf, file_path)

        logger.info(
            "PDF Ingestor Core complete: Extracted %d structural chunks", len(chunks)
        )
        return chunks
