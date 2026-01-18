"""
PDF Text Extraction for Trace

Extracts text content from PDF files using PyMuPDF (fitz).
Supports:
- Full text extraction
- Page-by-page extraction
- Metadata extraction
- Token estimation for LLM context budgeting

P4-02: PDF text extraction
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
import tiktoken

logger = logging.getLogger(__name__)

# Default encoding for token estimation
DEFAULT_ENCODING = "cl100k_base"

# Maximum pages to extract (for very large documents)
MAX_PAGES_DEFAULT = 100


@dataclass
class PDFPage:
    """Extracted content from a single PDF page."""

    page_number: int  # 1-indexed
    text: str
    token_count: int


@dataclass
class PDFExtraction:
    """Result of PDF text extraction."""

    file_path: Path
    total_pages: int
    extracted_pages: int
    title: str | None
    author: str | None
    subject: str | None
    pages: list[PDFPage]
    full_text: str
    total_tokens: int
    truncated: bool


class PDFExtractor:
    """
    Extracts text content from PDF files.

    Uses PyMuPDF for fast and accurate text extraction.
    Includes token counting for LLM context budget management.
    """

    def __init__(self, max_pages: int = MAX_PAGES_DEFAULT):
        """
        Initialize the PDF extractor.

        Args:
            max_pages: Maximum number of pages to extract
        """
        self.max_pages = max_pages
        try:
            self._encoding = tiktoken.get_encoding(DEFAULT_ENCODING)
        except Exception:
            logger.warning("Failed to load tiktoken encoding, using estimation")
            self._encoding = None

    def extract(
        self,
        file_path: Path | str,
        max_tokens: int | None = None,
        page_range: tuple[int, int] | None = None,
    ) -> PDFExtraction | None:
        """
        Extract text from a PDF file.

        Args:
            file_path: Path to the PDF file
            max_tokens: Maximum tokens to extract (stops when reached)
            page_range: Optional (start, end) page range (1-indexed, inclusive)

        Returns:
            PDFExtraction with extracted content, or None if extraction fails
        """
        file_path = Path(file_path)

        if not file_path.exists():
            logger.error(f"PDF file not found: {file_path}")
            return None

        if not file_path.suffix.lower() == ".pdf":
            logger.error(f"Not a PDF file: {file_path}")
            return None

        try:
            doc = fitz.open(str(file_path))
        except Exception as e:
            logger.error(f"Failed to open PDF {file_path}: {e}")
            return None

        try:
            # Extract metadata
            metadata = doc.metadata or {}
            title = metadata.get("title") or None
            author = metadata.get("author") or None
            subject = metadata.get("subject") or None

            total_pages = len(doc)

            # Determine page range
            start_page = 0
            end_page = min(total_pages, self.max_pages)

            if page_range:
                start_page = max(0, page_range[0] - 1)  # Convert to 0-indexed
                end_page = min(total_pages, page_range[1])

            # Extract pages
            pages: list[PDFPage] = []
            total_tokens = 0
            truncated = False

            for page_num in range(start_page, end_page):
                try:
                    page = doc[page_num]
                    text = page.get_text()

                    # Clean up text
                    text = self._clean_text(text)

                    # Count tokens
                    token_count = self._count_tokens(text)

                    # Check token limit
                    if max_tokens and total_tokens + token_count > max_tokens:
                        # Truncate this page's text to fit
                        remaining_tokens = max_tokens - total_tokens
                        if remaining_tokens > 0:
                            text = self._truncate_to_tokens(text, remaining_tokens)
                            token_count = remaining_tokens
                            pages.append(
                                PDFPage(
                                    page_number=page_num + 1,
                                    text=text,
                                    token_count=token_count,
                                )
                            )
                            total_tokens += token_count
                        truncated = True
                        break

                    pages.append(
                        PDFPage(
                            page_number=page_num + 1,
                            text=text,
                            token_count=token_count,
                        )
                    )
                    total_tokens += token_count

                except Exception as e:
                    logger.warning(f"Failed to extract page {page_num + 1}: {e}")
                    continue

            # Build full text
            full_text = "\n\n".join(page.text for page in pages)

            # Check if we hit max pages limit
            if end_page < total_pages and not truncated:
                truncated = True

            return PDFExtraction(
                file_path=file_path,
                total_pages=total_pages,
                extracted_pages=len(pages),
                title=title,
                author=author,
                subject=subject,
                pages=pages,
                full_text=full_text,
                total_tokens=total_tokens,
                truncated=truncated,
            )

        finally:
            doc.close()

    def extract_page(self, file_path: Path | str, page_number: int) -> PDFPage | None:
        """
        Extract a single page from a PDF.

        Args:
            file_path: Path to the PDF file
            page_number: Page number (1-indexed)

        Returns:
            PDFPage or None if extraction fails
        """
        result = self.extract(file_path, page_range=(page_number, page_number))
        if result and result.pages:
            return result.pages[0]
        return None

    def get_page_count(self, file_path: Path | str) -> int | None:
        """
        Get the total page count of a PDF without extracting text.

        Args:
            file_path: Path to the PDF file

        Returns:
            Number of pages or None if file cannot be opened
        """
        file_path = Path(file_path)

        if not file_path.exists():
            return None

        try:
            doc = fitz.open(str(file_path))
            count = len(doc)
            doc.close()
            return count
        except Exception as e:
            logger.error(f"Failed to get page count for {file_path}: {e}")
            return None

    def _clean_text(self, text: str) -> str:
        """Clean extracted text."""
        # Remove excessive whitespace
        lines = text.split("\n")
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if line:
                cleaned_lines.append(line)

        # Join with single newlines
        text = "\n".join(cleaned_lines)

        # Remove excessive newlines (more than 2 in a row)
        while "\n\n\n" in text:
            text = text.replace("\n\n\n", "\n\n")

        return text

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        if self._encoding:
            return len(self._encoding.encode(text))
        # Fallback: rough estimation (4 chars per token)
        return len(text) // 4

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to approximately max_tokens."""
        if self._encoding:
            tokens = self._encoding.encode(text)
            if len(tokens) <= max_tokens:
                return text
            truncated_tokens = tokens[:max_tokens]
            return self._encoding.decode(truncated_tokens)

        # Fallback: rough estimation
        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "..."


if __name__ == "__main__":
    import fire

    def extract(
        file_path: str,
        max_tokens: int | None = None,
        start_page: int | None = None,
        end_page: int | None = None,
    ):
        """Extract text from a PDF file."""
        extractor = PDFExtractor()

        page_range = None
        if start_page or end_page:
            page_range = (start_page or 1, end_page or 9999)

        result = extractor.extract(file_path, max_tokens=max_tokens, page_range=page_range)

        if result is None:
            return {"error": "Failed to extract PDF"}

        return {
            "file_path": str(result.file_path),
            "total_pages": result.total_pages,
            "extracted_pages": result.extracted_pages,
            "title": result.title,
            "author": result.author,
            "total_tokens": result.total_tokens,
            "truncated": result.truncated,
            "text_preview": result.full_text[:500] + "..."
            if len(result.full_text) > 500
            else result.full_text,
        }

    def page(file_path: str, page_number: int):
        """Extract a single page from a PDF."""
        extractor = PDFExtractor()
        result = extractor.extract_page(file_path, page_number)

        if result is None:
            return {"error": f"Failed to extract page {page_number}"}

        return {
            "page_number": result.page_number,
            "token_count": result.token_count,
            "text": result.text,
        }

    def info(file_path: str):
        """Get PDF info without extracting text."""
        extractor = PDFExtractor()
        page_count = extractor.get_page_count(file_path)

        if page_count is None:
            return {"error": "Failed to read PDF"}

        return {
            "file_path": file_path,
            "page_count": page_count,
        }

    fire.Fire(
        {
            "extract": extract,
            "page": page,
            "info": info,
        }
    )
