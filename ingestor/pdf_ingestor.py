from __future__ import annotations

from ingestor.base import BaseIngestor, TextChunk

from settings import get_settings

import pymupdf4llm

import logging

import asyncio

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

logger = logging.getLogger(__name__)

class PDFIngestor(BaseIngestor):
    def __init__(self):
        self.threshold = get_settings().pdf_ocr_fallback_threshold
        self.OCR : DocumentConverter | None = None
        self.ocr_lock = asyncio.Lock()
        
    async def initilize_ocr(self) -> None:
        
        async with self.ocr_lock:
            
            if self.OCR is not None:
                return None
            
            def init_ocr():
                return DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(
                        pipeline_options=PdfPipelineOptions(do_ocr=True)
                    )
                }
            )
        
            self.OCR = await asyncio.to_thread(init_ocr)
        
            logger.info("OCR Engine is Initialized.")
        
            return None
        
    def read_digital_pdf(self, file_path:str) ->  list[TextChunk]:
        
        pages = pymupdf4llm.to_markdown(file_path, page_chunks=True)
        chunks: list[TextChunk] = []
        
        for page in pages:
            
            text = page.get("text", "")
            if not text or not text.strip():
                continue
        
            chunks.append(
                TextChunk(
                    chunk_id=page.get("metadata", {}).get("page",len(chunks)),
                    text=text,
                    metadata={
                        "page": page.get("metadata", {}).get("page"),
                        "reading_medium": "PyMuPDF4LLM",
                        "original_document_format": "PDF"                  
                    }
                )
            )
            
        return chunks

    def read_scaned_pdf(self,file_path:str) ->  list[TextChunk]:
        
        result = self.OCR.convert(file_path)
        
        chunks: list[TextChunk] = []
        
        pages: dict[int,list[str]] = {}
        
        for page in result.document.pages():
            
            page_no = page.page_no
            
            text = result.document.export_to_markdown(page_no=page_no)
            
            if not text or not text.strip():
                continue
            
            chunks.append(
                TextChunk(
                    chunk_id=page_no,
                    text=text,
                    metadata={
                        "page": page_no,
                        "reading_medium": "Docling",
                        "original_document_format": "PDF"
                    }
                )
            )
            
        # for element, _ in result.document.iterate_items():
            
        #     text = getattr(element, "text", None)
        #     if not text or not text.strip():
        #         continue
            
        #     page_no = 0
            
        #     prov = getattr(element, "prov", None)
            
        #     if prov and len(prov) > 0:
        #         if hasattr(prov[0], "page_no"):
        #             page_no = prov[0].page_no
            
        #     pages.setdefault(page_no,[]).append(text.strip())
            
        # chunks = [
        #     TextChunk(
        #         chunk_id= page_number,
        #         text= "\n".join(text),
        #         metadata={
        #             "page": page_number,
        #             "reading_medium": "Docling",
        #             "original_document_format": "PDF"
        #         }
        #     )
        #     for page_number, text in pages.items()
        #     ]
                
            
        return chunks
    
    
    async def ingest(self, file_path:str) -> list[TextChunk]:
        
        logger.info("PDF Ingestor Processing %s", file_path)
        
        chunks = await asyncio.to_thread(self.read_digital_pdf,file_path)
        
        total_text = sum(len(c.text) for c in chunks)
        
        if total_text < self.threshold:
            logger.warning(
                "PDF Reader yielded %d chars and threashold is %d, hence falling back to OCR", 
                total_text, 
                self.threshold
            )
            
            await self.initilize_ocr()
            
            chunks = await asyncio.to_thread(self.read_scaned_pdf,file_path)
            
        logger.info("PDF Ingestor: Extracted %d chunks", len(chunks))
            
        return chunks