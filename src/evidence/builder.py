"""
Evidence Builder Orchestrator for Trace

Coordinates evidence extraction from various sources:
- Detects document contexts (PDF viewers, editors)
- Triggers PDF text extraction when file path is known
- Triggers OCR for screenshots when viewing documents
- Manages text buffer storage with event linking

The evidence builder can be triggered:
- On capture tick (checks document context)
- On demand for specific screenshots
- For batch processing of past data

P4-05: Evidence builder orchestrator
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.capture.foreground import ForegroundApp
from src.evidence.buffers import TextBuffer, TextBufferStorage
from src.evidence.detector import DocumentContext, DocumentContextDetector
from src.evidence.ocr import OCRExtractor, OCRResult
from src.evidence.pdf import PDFExtraction, PDFExtractor

logger = logging.getLogger(__name__)

# Maximum tokens to extract from a single document
MAX_DOCUMENT_TOKENS = 8000

# Maximum tokens to extract via OCR per screenshot
MAX_OCR_TOKENS = 4000


@dataclass
class EvidenceResult:
    """Result of evidence extraction."""

    timestamp: datetime
    context: DocumentContext
    extraction_type: str | None  # 'pdf', 'ocr', or None
    text_buffer: TextBuffer | None
    success: bool
    error: str | None


@dataclass
class EvidenceStats:
    """Statistics about evidence building."""

    total_processed: int
    documents_detected: int
    pdf_extractions: int
    ocr_extractions: int
    total_tokens: int
    errors: int


class EvidenceBuilder:
    """
    Orchestrates evidence extraction from documents and screenshots.

    Workflow:
    1. Detect document context from foreground app info
    2. If PDF with known file path -> extract text directly
    3. If document without file path -> trigger OCR on screenshot
    4. Store extracted text in text buffers linked to events

    The builder maintains state to avoid re-extracting from the same
    document within a session (using file path or content hash).
    """

    def __init__(
        self,
        pdf_extractor: PDFExtractor | None = None,
        ocr_extractor: OCRExtractor | None = None,
        buffer_storage: TextBufferStorage | None = None,
        detector: DocumentContextDetector | None = None,
        db_path: Path | str | None = None,
    ):
        """
        Initialize the evidence builder.

        Args:
            pdf_extractor: PDF extractor (creates default if None)
            ocr_extractor: OCR extractor (creates default if None)
            buffer_storage: Text buffer storage (creates default if None)
            detector: Document context detector (creates default if None)
            db_path: Path to SQLite database
        """
        self._pdf_extractor = pdf_extractor or PDFExtractor()
        self._ocr_extractor = ocr_extractor or OCRExtractor()
        self._buffer_storage = buffer_storage or TextBufferStorage(db_path)
        self._detector = detector or DocumentContextDetector()

        # Track recently processed documents to avoid redundant extraction
        # Maps file_path -> (extraction_timestamp, text_id)
        self._recent_pdfs: dict[str, tuple[datetime, str]] = {}

        # Statistics
        self._stats = EvidenceStats(
            total_processed=0,
            documents_detected=0,
            pdf_extractions=0,
            ocr_extractions=0,
            total_tokens=0,
            errors=0,
        )

        # Configurable limits
        self.max_document_tokens = MAX_DOCUMENT_TOKENS
        self.max_ocr_tokens = MAX_OCR_TOKENS

        # Minimum time between re-extractions of same document (seconds)
        self.reextract_interval = 300  # 5 minutes

    def process_foreground(
        self,
        foreground: ForegroundApp,
        screenshot_path: Path | None = None,
        event_id: str | None = None,
    ) -> EvidenceResult:
        """
        Process a foreground app capture for evidence extraction.

        Args:
            foreground: Foreground app information
            screenshot_path: Optional screenshot to OCR if document detected
            event_id: Event ID to link extracted text to

        Returns:
            EvidenceResult with extraction status
        """
        self._stats.total_processed += 1
        timestamp = foreground.timestamp

        # Detect document context
        context = self._detector.detect(
            bundle_id=foreground.bundle_id,
            app_name=foreground.app_name,
            window_title=foreground.window_title,
        )

        if not context.is_document:
            return EvidenceResult(
                timestamp=timestamp,
                context=context,
                extraction_type=None,
                text_buffer=None,
                success=True,
                error=None,
            )

        self._stats.documents_detected += 1

        # Try PDF extraction if we have a file path
        if context.document_type == "pdf" and context.file_path:
            result = self._extract_pdf(context, event_id, timestamp)
            if result.success and result.text_buffer:
                return result

        # Fall back to OCR if we have a screenshot
        if screenshot_path:
            return self._extract_ocr(
                context=context,
                screenshot_path=screenshot_path,
                event_id=event_id,
                timestamp=timestamp,
            )

        # Document detected but no extraction possible
        return EvidenceResult(
            timestamp=timestamp,
            context=context,
            extraction_type=None,
            text_buffer=None,
            success=True,
            error=None,
        )

    def extract_from_pdf(
        self,
        file_path: Path | str,
        event_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> EvidenceResult:
        """
        Extract text from a PDF file directly.

        Args:
            file_path: Path to the PDF file
            event_id: Event ID to link extracted text to
            timestamp: Extraction timestamp

        Returns:
            EvidenceResult with extraction status
        """
        file_path = Path(file_path)
        timestamp = timestamp or datetime.now()

        # Create a synthetic context
        context = DocumentContext(
            is_document=True,
            document_type="pdf",
            file_path=file_path,
            file_name=file_path.name,
            app_bundle_id=None,
            app_name=None,
            window_title=None,
            confidence=1.0,
        )

        return self._extract_pdf(context, event_id, timestamp)

    def extract_from_screenshot(
        self,
        screenshot_path: Path | str,
        event_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> EvidenceResult:
        """
        Extract text from a screenshot using OCR.

        Args:
            screenshot_path: Path to the screenshot
            event_id: Event ID to link extracted text to
            timestamp: Extraction timestamp

        Returns:
            EvidenceResult with extraction status
        """
        screenshot_path = Path(screenshot_path)
        timestamp = timestamp or datetime.now()

        # Create a synthetic context
        context = DocumentContext(
            is_document=True,
            document_type="screenshot",
            file_path=screenshot_path,
            file_name=screenshot_path.name,
            app_bundle_id=None,
            app_name=None,
            window_title=None,
            confidence=1.0,
        )

        return self._extract_ocr(
            context=context,
            screenshot_path=screenshot_path,
            event_id=event_id,
            timestamp=timestamp,
        )

    def _extract_pdf(
        self,
        context: DocumentContext,
        event_id: str | None,
        timestamp: datetime,
    ) -> EvidenceResult:
        """Extract text from a PDF file."""
        if not context.file_path or not context.file_path.exists():
            return EvidenceResult(
                timestamp=timestamp,
                context=context,
                extraction_type=None,
                text_buffer=None,
                success=False,
                error="PDF file not found",
            )

        file_path_str = str(context.file_path)

        # Check if recently extracted
        if file_path_str in self._recent_pdfs:
            last_time, text_id = self._recent_pdfs[file_path_str]
            time_diff = (timestamp - last_time).total_seconds()
            if time_diff < self.reextract_interval:
                # Return reference to existing buffer
                existing_buffer = self._buffer_storage.get(text_id)
                if existing_buffer:
                    logger.debug(f"Using cached PDF extraction for {context.file_name}")
                    return EvidenceResult(
                        timestamp=timestamp,
                        context=context,
                        extraction_type="pdf_cached",
                        text_buffer=existing_buffer,
                        success=True,
                        error=None,
                    )

        # Extract text from PDF
        try:
            extraction: PDFExtraction | None = self._pdf_extractor.extract(
                context.file_path,
                max_tokens=self.max_document_tokens,
            )
        except Exception as e:
            logger.error(f"PDF extraction failed: {e}")
            self._stats.errors += 1
            return EvidenceResult(
                timestamp=timestamp,
                context=context,
                extraction_type="pdf",
                text_buffer=None,
                success=False,
                error=str(e),
            )

        if extraction is None or not extraction.full_text:
            return EvidenceResult(
                timestamp=timestamp,
                context=context,
                extraction_type="pdf",
                text_buffer=None,
                success=False,
                error="No text extracted from PDF",
            )

        # Store the text buffer
        try:
            buffer = self._buffer_storage.store(
                text=extraction.full_text,
                source_type="pdf_extract",
                ref=file_path_str,
                event_id=event_id,
                timestamp=timestamp,
            )
        except Exception as e:
            logger.error(f"Failed to store PDF text buffer: {e}")
            self._stats.errors += 1
            return EvidenceResult(
                timestamp=timestamp,
                context=context,
                extraction_type="pdf",
                text_buffer=None,
                success=False,
                error=str(e),
            )

        # Update tracking
        self._recent_pdfs[file_path_str] = (timestamp, buffer.text_id)
        self._stats.pdf_extractions += 1
        self._stats.total_tokens += buffer.token_estimate

        logger.info(f"Extracted {buffer.token_estimate} tokens from PDF: {context.file_name}")

        return EvidenceResult(
            timestamp=timestamp,
            context=context,
            extraction_type="pdf",
            text_buffer=buffer,
            success=True,
            error=None,
        )

    def _extract_ocr(
        self,
        context: DocumentContext,
        screenshot_path: Path,
        event_id: str | None,
        timestamp: datetime,
    ) -> EvidenceResult:
        """Extract text from a screenshot using OCR."""
        if not screenshot_path.exists():
            return EvidenceResult(
                timestamp=timestamp,
                context=context,
                extraction_type=None,
                text_buffer=None,
                success=False,
                error="Screenshot file not found",
            )

        # Run OCR
        try:
            ocr_result: OCRResult | None = self._ocr_extractor.extract(
                screenshot_path,
                max_tokens=self.max_ocr_tokens,
            )
        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            self._stats.errors += 1
            return EvidenceResult(
                timestamp=timestamp,
                context=context,
                extraction_type="ocr",
                text_buffer=None,
                success=False,
                error=str(e),
            )

        if ocr_result is None or not ocr_result.text:
            return EvidenceResult(
                timestamp=timestamp,
                context=context,
                extraction_type="ocr",
                text_buffer=None,
                success=False,
                error="No text extracted via OCR",
            )

        # Store the text buffer
        try:
            buffer = self._buffer_storage.store(
                text=ocr_result.text,
                source_type="ocr",
                ref=str(screenshot_path),
                event_id=event_id,
                timestamp=timestamp,
            )
        except Exception as e:
            logger.error(f"Failed to store OCR text buffer: {e}")
            self._stats.errors += 1
            return EvidenceResult(
                timestamp=timestamp,
                context=context,
                extraction_type="ocr",
                text_buffer=None,
                success=False,
                error=str(e),
            )

        self._stats.ocr_extractions += 1
        self._stats.total_tokens += buffer.token_estimate

        logger.info(
            f"Extracted {buffer.token_estimate} tokens via OCR from: {screenshot_path.name}"
        )

        return EvidenceResult(
            timestamp=timestamp,
            context=context,
            extraction_type="ocr",
            text_buffer=buffer,
            success=True,
            error=None,
        )

    def get_stats(self) -> EvidenceStats:
        """Get evidence building statistics."""
        return self._stats

    def reset_stats(self) -> None:
        """Reset statistics."""
        self._stats = EvidenceStats(
            total_processed=0,
            documents_detected=0,
            pdf_extractions=0,
            ocr_extractions=0,
            total_tokens=0,
            errors=0,
        )

    def clear_cache(self) -> None:
        """Clear the recent documents cache."""
        self._recent_pdfs.clear()


if __name__ == "__main__":
    import fire

    from src.db.migrations import init_database

    def process_pdf(
        file_path: str,
        event_id: str | None = None,
    ):
        """Extract evidence from a PDF file."""
        init_database()
        builder = EvidenceBuilder()
        result = builder.extract_from_pdf(file_path, event_id)

        return {
            "success": result.success,
            "extraction_type": result.extraction_type,
            "error": result.error,
            "buffer": {
                "text_id": result.text_buffer.text_id if result.text_buffer else None,
                "tokens": result.text_buffer.token_estimate if result.text_buffer else 0,
                "preview": (
                    result.text_buffer.text[:300] + "..."
                    if result.text_buffer and len(result.text_buffer.text) > 300
                    else result.text_buffer.text
                    if result.text_buffer
                    else None
                ),
            }
            if result.text_buffer
            else None,
        }

    def process_screenshot(
        screenshot_path: str,
        event_id: str | None = None,
    ):
        """Extract evidence from a screenshot using OCR."""
        init_database()
        builder = EvidenceBuilder()
        result = builder.extract_from_screenshot(screenshot_path, event_id)

        return {
            "success": result.success,
            "extraction_type": result.extraction_type,
            "error": result.error,
            "buffer": {
                "text_id": result.text_buffer.text_id if result.text_buffer else None,
                "tokens": result.text_buffer.token_estimate if result.text_buffer else 0,
                "preview": (
                    result.text_buffer.text[:300] + "..."
                    if result.text_buffer and len(result.text_buffer.text) > 300
                    else result.text_buffer.text
                    if result.text_buffer
                    else None
                ),
            }
            if result.text_buffer
            else None,
        }

    def detect(
        bundle_id: str | None = None,
        app_name: str | None = None,
        window_title: str | None = None,
    ):
        """Detect document context."""
        builder = EvidenceBuilder()
        context = builder._detector.detect(bundle_id, app_name, window_title)

        return {
            "is_document": context.is_document,
            "document_type": context.document_type,
            "file_path": str(context.file_path) if context.file_path else None,
            "file_name": context.file_name,
            "confidence": context.confidence,
        }

    def stats():
        """Show evidence building statistics."""
        builder = EvidenceBuilder()
        s = builder.get_stats()
        return {
            "total_processed": s.total_processed,
            "documents_detected": s.documents_detected,
            "pdf_extractions": s.pdf_extractions,
            "ocr_extractions": s.ocr_extractions,
            "total_tokens": s.total_tokens,
            "errors": s.errors,
        }

    fire.Fire(
        {
            "pdf": process_pdf,
            "screenshot": process_screenshot,
            "detect": detect,
            "stats": stats,
        }
    )
