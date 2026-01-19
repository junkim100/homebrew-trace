"""
LLM-based OCR for Screenshots for Trace

Uses OpenAI's vision API to extract text from screenshots.
Optimized for document content, code, and on-screen text.

Features:
- Extracts visible text content
- Preserves formatting where possible
- Token counting for budget management
- Caching to avoid re-processing identical images

P4-03: LLM-based OCR for screenshots
"""

import base64
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import tiktoken
from openai import OpenAI

from src.core.paths import ensure_daily_cache_dirs

logger = logging.getLogger(__name__)

# Default model for OCR
DEFAULT_OCR_MODEL = "gpt-5-nano-2025-08-07"

# Default encoding for token estimation
DEFAULT_ENCODING = "cl100k_base"

# OCR system prompt
OCR_SYSTEM_PROMPT = """You are an OCR assistant that extracts text from screenshots.

Your task is to extract ALL visible text from the provided screenshot accurately.

Guidelines:
1. Extract text in reading order (top to bottom, left to right)
2. Preserve paragraph structure with blank lines between sections
3. For code or technical content, preserve indentation and formatting
4. For UI elements, indicate context in brackets like [Button: Submit] or [Menu: File > Save]
5. Ignore decorative elements, icons without text labels
6. If text is partially obscured or unclear, indicate with [unclear: possible text]
7. For tables, preserve structure using spaces or | characters

Output ONLY the extracted text content, nothing else."""

# Maximum image size (bytes) for API
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB


@dataclass
class OCRResult:
    """Result of OCR extraction from a screenshot."""

    screenshot_path: Path
    text: str
    token_count: int
    model: str
    timestamp: datetime
    cached: bool
    image_hash: str


class OCRExtractor:
    """
    Extracts text from screenshots using OpenAI's vision API.

    Caches results to avoid redundant API calls for identical images.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_OCR_MODEL,
        cache_results: bool = True,
    ):
        """
        Initialize the OCR extractor.

        Args:
            api_key: OpenAI API key (uses OPENAI_API_KEY env var if not provided)
            model: Vision model to use for OCR
            cache_results: Whether to cache OCR results
        """
        self.model = model
        self.cache_results = cache_results
        self._api_key = api_key

        # Lazy initialize OpenAI client (to allow creation without API key)
        self._client: OpenAI | None = None

        # Token encoder for counting
        try:
            self._encoding = tiktoken.get_encoding(DEFAULT_ENCODING)
        except Exception:
            logger.warning("Failed to load tiktoken encoding")
            self._encoding = None

    def _get_client(self) -> OpenAI:
        """Get or create the OpenAI client (lazy initialization)."""
        if self._client is None:
            self._client = OpenAI(api_key=self._api_key) if self._api_key else OpenAI()
        return self._client

    def extract(
        self,
        image_path: Path | str,
        max_tokens: int | None = None,
        use_cache: bool = True,
    ) -> OCRResult | None:
        """
        Extract text from a screenshot using vision LLM.

        Args:
            image_path: Path to the screenshot image
            max_tokens: Maximum tokens for the response
            use_cache: Whether to check/use cached results

        Returns:
            OCRResult with extracted text, or None if extraction fails
        """
        image_path = Path(image_path)

        if not image_path.exists():
            logger.error(f"Image not found: {image_path}")
            return None

        # Check file size
        if image_path.stat().st_size > MAX_IMAGE_SIZE:
            logger.error(f"Image too large for OCR: {image_path}")
            return None

        # Compute image hash for caching
        image_hash = self._compute_hash(image_path)

        # Check cache
        if use_cache and self.cache_results:
            cached = self._load_from_cache(image_hash)
            if cached:
                logger.debug(f"OCR cache hit for {image_path.name}")
                return OCRResult(
                    screenshot_path=image_path,
                    text=cached["text"],
                    token_count=cached["token_count"],
                    model=cached["model"],
                    timestamp=datetime.fromisoformat(cached["timestamp"]),
                    cached=True,
                    image_hash=image_hash,
                )

        # Encode image to base64
        try:
            image_data = self._encode_image(image_path)
        except Exception as e:
            logger.error(f"Failed to encode image {image_path}: {e}")
            return None

        # Call OpenAI Vision API
        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": OCR_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_data}",
                                    "detail": "high",
                                },
                            },
                            {
                                "type": "text",
                                "text": "Extract all visible text from this screenshot.",
                            },
                        ],
                    },
                ],
                max_completion_tokens=max_tokens or 4096,
            )

            text = response.choices[0].message.content or ""
            token_count = self._count_tokens(text)
            timestamp = datetime.now()

            result = OCRResult(
                screenshot_path=image_path,
                text=text,
                token_count=token_count,
                model=self.model,
                timestamp=timestamp,
                cached=False,
                image_hash=image_hash,
            )

            # Cache the result
            if self.cache_results:
                self._save_to_cache(image_hash, result)

            return result

        except Exception as e:
            logger.error(f"OCR API call failed for {image_path}: {e}")
            return None

    def extract_batch(
        self,
        image_paths: list[Path | str],
        max_tokens_per_image: int | None = None,
    ) -> list[OCRResult]:
        """
        Extract text from multiple screenshots.

        Args:
            image_paths: List of paths to screenshot images
            max_tokens_per_image: Maximum tokens per image response

        Returns:
            List of OCRResults (may be fewer than inputs if some fail)
        """
        results = []
        for path in image_paths:
            result = self.extract(path, max_tokens=max_tokens_per_image)
            if result:
                results.append(result)
        return results

    def _encode_image(self, image_path: Path) -> str:
        """Encode image to base64 string."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _compute_hash(self, image_path: Path) -> str:
        """Compute SHA256 hash of image file."""
        sha256 = hashlib.sha256()
        with open(image_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()[:16]  # Use first 16 chars

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        if self._encoding:
            return len(self._encoding.encode(text))
        return len(text) // 4

    def _get_cache_path(self, image_hash: str) -> Path:
        """Get the cache file path for an image hash."""
        # Ensure daily cache directories exist
        cache_dirs = ensure_daily_cache_dirs()
        cache_dir = cache_dirs["ocr"]
        return cache_dir / f"{image_hash}.json"

    def _load_from_cache(self, image_hash: str) -> dict | None:
        """Load cached OCR result."""
        cache_path = self._get_cache_path(image_hash)
        if cache_path.exists():
            try:
                with open(cache_path) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load OCR cache: {e}")
        return None

    def _save_to_cache(self, image_hash: str, result: OCRResult) -> None:
        """Save OCR result to cache."""
        cache_path = self._get_cache_path(image_hash)
        try:
            cache_data = {
                "text": result.text,
                "token_count": result.token_count,
                "model": result.model,
                "timestamp": result.timestamp.isoformat(),
            }
            with open(cache_path, "w") as f:
                json.dump(cache_data, f)
        except Exception as e:
            logger.warning(f"Failed to save OCR cache: {e}")

    def clear_cache(self, date: datetime | None = None) -> int:
        """
        Clear OCR cache for a specific date.

        Args:
            date: Date to clear cache for (defaults to today)

        Returns:
            Number of cache files deleted
        """
        cache_dirs = ensure_daily_cache_dirs(date)
        cache_dir = cache_dirs["ocr"]

        if not cache_dir.exists():
            return 0

        count = 0
        for cache_file in cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
                count += 1
            except Exception as e:
                logger.warning(f"Failed to delete cache file {cache_file}: {e}")

        return count


if __name__ == "__main__":
    import fire

    def extract(image_path: str, max_tokens: int | None = None):
        """Extract text from a screenshot."""
        extractor = OCRExtractor()
        result = extractor.extract(image_path, max_tokens=max_tokens)

        if result is None:
            return {"error": "Failed to extract text from image"}

        return {
            "screenshot": str(result.screenshot_path),
            "token_count": result.token_count,
            "model": result.model,
            "cached": result.cached,
            "text_preview": result.text[:500] + "..." if len(result.text) > 500 else result.text,
        }

    def batch(image_dir: str, pattern: str = "*.jpg"):
        """Extract text from all images in a directory."""
        from pathlib import Path

        dir_path = Path(image_dir)
        if not dir_path.exists():
            return {"error": f"Directory not found: {image_dir}"}

        image_paths = list(dir_path.glob(pattern))
        if not image_paths:
            return {"error": f"No images found matching {pattern}"}

        extractor = OCRExtractor()
        results = extractor.extract_batch(image_paths)

        return {
            "total_images": len(image_paths),
            "successful": len(results),
            "total_tokens": sum(r.token_count for r in results),
            "cached": sum(1 for r in results if r.cached),
        }

    def clear_cache(date: str | None = None):
        """Clear OCR cache for a date."""
        from datetime import datetime

        dt = datetime.fromisoformat(date) if date else None
        extractor = OCRExtractor()
        count = extractor.clear_cache(dt)
        return {"deleted": count}

    fire.Fire(
        {
            "extract": extract,
            "batch": batch,
            "clear-cache": clear_cache,
        }
    )
