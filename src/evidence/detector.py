"""
Document Context Detector for Trace

Detects when the user is viewing or editing documents based on:
- Application bundle ID (PDF viewers, document editors)
- Window title patterns (file extensions, document names)
- File path extraction from window titles

P4-01: Document context detector
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DocumentContext:
    """Information about a detected document context."""

    is_document: bool
    document_type: str | None  # 'pdf', 'word', 'pages', 'text', 'code', 'spreadsheet', etc.
    file_path: Path | None
    file_name: str | None
    app_bundle_id: str | None
    app_name: str | None
    window_title: str | None
    confidence: float  # 0.0 to 1.0


# Apps that are primarily document viewers/editors
DOCUMENT_APPS: dict[str, str] = {
    # PDF Viewers
    "com.apple.Preview": "pdf",
    "com.adobe.Reader": "pdf",
    "com.adobe.Acrobat.Pro": "pdf",
    "com.readdle.PDFExpert-Mac": "pdf",
    "net.sourceforge.skim-app.skim": "pdf",
    "com.qoppa.pdfstudio": "pdf",
    # Word Processors
    "com.apple.iWork.Pages": "pages",
    "com.microsoft.Word": "word",
    "com.google.Chrome": None,  # Special handling for Google Docs
    # Spreadsheets
    "com.apple.iWork.Numbers": "spreadsheet",
    "com.microsoft.Excel": "spreadsheet",
    # Presentations
    "com.apple.iWork.Keynote": "presentation",
    "com.microsoft.Powerpoint": "presentation",
    # Text Editors
    "com.apple.TextEdit": "text",
    "com.sublimetext.4": "code",
    "com.sublimetext.3": "code",
    "com.microsoft.VSCode": "code",
    "com.jetbrains.intellij": "code",
    "com.jetbrains.pycharm": "code",
    "com.jetbrains.webstorm": "code",
    "com.panic.Nova": "code",
    "com.barebones.bbedit": "code",
    "io.brackets.appshell": "code",
    "com.github.atom": "code",
    "abnerworks.Typora": "markdown",
    "com.electron.obsidian": "markdown",
    "md.obsidian": "markdown",
    "net.ia.writer": "markdown",
    "com.typora": "markdown",
    # E-readers
    "com.apple.iBooksX": "ebook",
    "com.amazon.Kindle": "ebook",
}

# Window title patterns that indicate documents
WINDOW_TITLE_PATTERNS: list[tuple[str, str]] = [
    # File extensions
    (r"\.pdf(\s|$|\]|\))", "pdf"),
    (r"\.docx?(\s|$|\]|\))", "word"),
    (r"\.xlsx?(\s|$|\]|\))", "spreadsheet"),
    (r"\.pptx?(\s|$|\]|\))", "presentation"),
    (r"\.pages(\s|$|\]|\))", "pages"),
    (r"\.numbers(\s|$|\]|\))", "spreadsheet"),
    (r"\.key(\s|$|\]|\))", "presentation"),
    (r"\.txt(\s|$|\]|\))", "text"),
    (r"\.md(\s|$|\]|\))", "markdown"),
    (r"\.rtf(\s|$|\]|\))", "text"),
    (r"\.(py|js|ts|jsx|tsx|java|c|cpp|h|rs|go|rb|php|swift|kt)(\s|$|\]|\))", "code"),
    (r"\.epub(\s|$|\]|\))", "ebook"),
    # Google Docs patterns
    (r"Google Docs$", "gdoc"),
    (r"Google Sheets$", "gsheet"),
    (r"Google Slides$", "gslides"),
]

# Patterns for extracting file paths from window titles
FILE_PATH_PATTERNS: list[str] = [
    # Absolute paths starting with /
    r"(/(?:Users|Volumes|private|tmp)[^\s\[\]]+)",
    # ~/path format
    r"(~/[^\s\[\]]+)",
    # App-specific patterns: "filename.ext - AppName"
    r"^([^-\[\]]+\.[a-zA-Z]{2,5})\s*[-\u2014]\s*",
    # "AppName - filename.ext"
    r"[-\u2014]\s*([^-\[\]]+\.[a-zA-Z]{2,5})$",
    # Just filename with extension
    r"^([^/\\\s\[\]]+\.[a-zA-Z]{2,5})$",
]


class DocumentContextDetector:
    """
    Detects document viewing/editing contexts from foreground app info.

    Uses bundle IDs, window titles, and file path patterns to determine
    if the user is interacting with a document.
    """

    def __init__(self):
        """Initialize the document context detector."""
        # Compile regex patterns
        self._title_patterns = [
            (re.compile(pattern, re.IGNORECASE), doc_type)
            for pattern, doc_type in WINDOW_TITLE_PATTERNS
        ]
        self._path_patterns = [re.compile(pattern) for pattern in FILE_PATH_PATTERNS]

    def detect(
        self,
        bundle_id: str | None,
        app_name: str | None,
        window_title: str | None,
    ) -> DocumentContext:
        """
        Detect document context from foreground app information.

        Args:
            bundle_id: Application bundle ID (e.g., com.apple.Preview)
            app_name: Application name (e.g., Preview)
            window_title: Current window title

        Returns:
            DocumentContext with detection results
        """
        doc_type: str | None = None
        file_path: Path | None = None
        file_name: str | None = None
        confidence: float = 0.0

        # Check if app is a known document app
        if bundle_id and bundle_id in DOCUMENT_APPS:
            doc_type = DOCUMENT_APPS[bundle_id]
            confidence = 0.8

        # Analyze window title for document patterns
        if window_title:
            # Check title patterns for document type
            detected_type = self._detect_type_from_title(window_title)
            if detected_type:
                if doc_type is None:
                    doc_type = detected_type
                confidence = max(confidence, 0.7)

            # Try to extract file path
            extracted_path = self._extract_file_path(window_title)
            if extracted_path:
                file_path = extracted_path
                file_name = extracted_path.name
                confidence = max(confidence, 0.9)

                # Infer type from extension if not already known
                if doc_type is None:
                    doc_type = self._type_from_extension(extracted_path.suffix)

            # Extract filename from title if no path found
            if file_name is None and window_title:
                extracted_name = self._extract_filename(window_title)
                if extracted_name:
                    file_name = extracted_name

        # Special handling for browsers with Google Docs
        if bundle_id in ("com.google.Chrome", "com.apple.Safari", "org.mozilla.firefox"):
            google_type = self._detect_google_docs(window_title)
            if google_type:
                doc_type = google_type
                confidence = 0.85

        is_document = doc_type is not None and confidence >= 0.5

        return DocumentContext(
            is_document=is_document,
            document_type=doc_type,
            file_path=file_path,
            file_name=file_name,
            app_bundle_id=bundle_id,
            app_name=app_name,
            window_title=window_title,
            confidence=confidence,
        )

    def _detect_type_from_title(self, title: str) -> str | None:
        """Detect document type from window title patterns."""
        for pattern, doc_type in self._title_patterns:
            if pattern.search(title):
                return doc_type
        return None

    def _extract_file_path(self, title: str) -> Path | None:
        """Extract file path from window title."""
        for pattern in self._path_patterns:
            match = pattern.search(title)
            if match:
                path_str = match.group(1)
                # Expand ~ to home directory
                if path_str.startswith("~"):
                    path_str = str(Path.home()) + path_str[1:]
                # Clean up common suffixes
                path_str = path_str.rstrip(" -\u2014")
                try:
                    path = Path(path_str)
                    # Verify it looks like a valid path
                    if path.suffix and len(path.suffix) <= 10:
                        return path
                except Exception:
                    continue
        return None

    def _extract_filename(self, title: str) -> str | None:
        """Extract just the filename from window title."""
        # Pattern for "filename.ext" possibly with app name
        patterns = [
            r"^([^-\u2014\[\]]+\.[a-zA-Z]{2,5})\s*[-\u2014]",  # "file.ext - App"
            r"[-\u2014]\s*([^-\u2014\[\]]+\.[a-zA-Z]{2,5})$",  # "App - file.ext"
            r"^([^/\\\s]+\.[a-zA-Z]{2,5})$",  # Just "file.ext"
        ]

        for pattern in patterns:
            match = re.search(pattern, title.strip())
            if match:
                return match.group(1).strip()
        return None

    def _type_from_extension(self, ext: str) -> str | None:
        """Map file extension to document type."""
        ext = ext.lower().lstrip(".")
        extension_map = {
            "pdf": "pdf",
            "doc": "word",
            "docx": "word",
            "xls": "spreadsheet",
            "xlsx": "spreadsheet",
            "ppt": "presentation",
            "pptx": "presentation",
            "pages": "pages",
            "numbers": "spreadsheet",
            "key": "presentation",
            "txt": "text",
            "md": "markdown",
            "rtf": "text",
            "epub": "ebook",
            # Code files
            "py": "code",
            "js": "code",
            "ts": "code",
            "jsx": "code",
            "tsx": "code",
            "java": "code",
            "c": "code",
            "cpp": "code",
            "h": "code",
            "rs": "code",
            "go": "code",
            "rb": "code",
            "php": "code",
            "swift": "code",
            "kt": "code",
        }
        return extension_map.get(ext)

    def _detect_google_docs(self, title: str | None) -> str | None:
        """Detect Google Docs/Sheets/Slides from window title."""
        if not title:
            return None

        title_lower = title.lower()
        if "google docs" in title_lower:
            return "gdoc"
        if "google sheets" in title_lower:
            return "gsheet"
        if "google slides" in title_lower:
            return "gslides"
        return None

    def is_pdf_context(self, context: DocumentContext) -> bool:
        """Check if the context is a PDF document."""
        return context.is_document and context.document_type == "pdf"

    def is_extractable_document(self, context: DocumentContext) -> bool:
        """Check if text can be directly extracted from the document."""
        # PDFs with known file paths can have text extracted directly
        if context.document_type == "pdf" and context.file_path:
            return context.file_path.exists()
        return False


if __name__ == "__main__":
    import fire

    def detect(
        bundle_id: str | None = None,
        app_name: str | None = None,
        window_title: str | None = None,
    ):
        """Detect document context from app info."""
        detector = DocumentContextDetector()
        result = detector.detect(bundle_id, app_name, window_title)
        return {
            "is_document": result.is_document,
            "document_type": result.document_type,
            "file_path": str(result.file_path) if result.file_path else None,
            "file_name": result.file_name,
            "confidence": result.confidence,
        }

    def test_examples():
        """Test with example window titles."""
        detector = DocumentContextDetector()

        examples = [
            ("com.apple.Preview", "Preview", "document.pdf"),
            ("com.apple.Preview", "Preview", "/Users/jun/Documents/report.pdf - Preview"),
            ("com.microsoft.Word", "Word", "thesis.docx - Microsoft Word"),
            ("com.google.Chrome", "Chrome", "My Document - Google Docs"),
            ("com.apple.TextEdit", "TextEdit", "notes.txt"),
            ("com.microsoft.VSCode", "Code", "main.py - project - Visual Studio Code"),
            ("com.apple.Safari", "Safari", "GitHub - home"),
        ]

        results = []
        for bundle_id, app_name, window_title in examples:
            result = detector.detect(bundle_id, app_name, window_title)
            results.append(
                {
                    "input": {"app": app_name, "title": window_title},
                    "output": {
                        "is_document": result.is_document,
                        "type": result.document_type,
                        "confidence": result.confidence,
                    },
                }
            )
        return results

    fire.Fire(
        {
            "detect": detect,
            "test": test_examples,
        }
    )
