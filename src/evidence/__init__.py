"""
Evidence Builder module for Trace

This module handles document context detection, PDF text extraction,
OCR for screenshots, and text buffer management.

Evidence is extracted from:
- PDFs when file path is known
- Screenshots via LLM-based OCR
- Document editors and viewers

Text buffers are transient and deleted daily after successful revision.
"""

from src.evidence.buffers import TextBuffer, TextBufferStorage
from src.evidence.builder import EvidenceBuilder, EvidenceResult, EvidenceStats
from src.evidence.detector import DocumentContext, DocumentContextDetector
from src.evidence.ocr import OCRExtractor, OCRResult
from src.evidence.pdf import PDFExtraction, PDFExtractor, PDFPage

__all__ = [
    "DocumentContext",
    "DocumentContextDetector",
    "EvidenceBuilder",
    "EvidenceResult",
    "EvidenceStats",
    "OCRExtractor",
    "OCRResult",
    "PDFExtraction",
    "PDFExtractor",
    "PDFPage",
    "TextBuffer",
    "TextBufferStorage",
]
