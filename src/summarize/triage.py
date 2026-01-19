"""
Frame Triage with Vision LLM for Trace

Uses gpt-5-nano to classify and score screenshot importance for keyframe selection.
This enables intelligent selection of representative frames for hourly summarization.

Classification categories:
- transition: App/window switch moment
- document: Reading or editing documents/code
- media: Watching video/streaming content
- browsing: Web browsing, social media
- idle: Desktop, screen saver, locked
- communication: Email, chat, video calls
- creative: Design tools, editors
- gaming: Games, entertainment

P5-01: Frame triage with gpt-5-nano
"""

import base64
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from openai import OpenAI

logger = logging.getLogger(__name__)

# Model for frame triage
TRIAGE_MODEL = "gpt-5-nano-2025-08-07"


class FrameCategory(str, Enum):
    """Categories for frame classification."""

    TRANSITION = "transition"
    DOCUMENT = "document"
    MEDIA = "media"
    BROWSING = "browsing"
    IDLE = "idle"
    COMMUNICATION = "communication"
    CREATIVE = "creative"
    GAMING = "gaming"
    OTHER = "other"


@dataclass
class TriageResult:
    """Result of frame triage for a single screenshot."""

    screenshot_id: str
    screenshot_path: Path
    timestamp: datetime
    category: FrameCategory
    importance_score: float  # 0.0 to 1.0
    description: str  # Brief description of visible content
    has_text: bool  # Whether significant text is visible
    has_document: bool  # Whether a document is being viewed
    has_media: bool  # Whether media content is visible
    raw_response: dict | None = None


TRIAGE_SYSTEM_PROMPT = """You are a screenshot classifier for a personal activity tracker.

Analyze the screenshot and provide a JSON response with:
1. category: One of [transition, document, media, browsing, idle, communication, creative, gaming, other]
2. importance_score: 0.0 to 1.0 indicating how representative/important this frame is
3. description: Brief (1-2 sentences) description of what's visible
4. has_text: boolean - is there significant readable text on screen?
5. has_document: boolean - is a document, code file, or PDF being viewed?
6. has_media: boolean - is video/streaming content visible?

Scoring guidelines:
- High (0.8-1.0): Clear activity, transition moment, important content visible
- Medium (0.5-0.7): Normal activity, some useful context
- Low (0.2-0.4): Static content, minimal activity
- Very low (0.0-0.2): Idle, locked screen, screensaver

Respond with valid JSON only."""

TRIAGE_USER_PROMPT = "Classify this screenshot and score its importance."


class FrameTriager:
    """
    Classifies and scores screenshots for keyframe selection.

    Uses vision LLM to understand frame content and assign importance scores,
    enabling intelligent selection of representative frames for summarization.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = TRIAGE_MODEL,
    ):
        """
        Initialize the frame triager.

        Args:
            api_key: OpenAI API key (uses OPENAI_API_KEY env var if not provided)
            model: Vision model to use for triage
        """
        self.model = model
        self._api_key = api_key
        self._client: OpenAI | None = None

    def _get_client(self) -> OpenAI:
        """Get or create the OpenAI client (lazy initialization)."""
        if self._client is None:
            self._client = OpenAI(api_key=self._api_key) if self._api_key else OpenAI()
        return self._client

    def triage(
        self,
        screenshot_id: str,
        screenshot_path: Path | str,
        timestamp: datetime,
        context: dict | None = None,
    ) -> TriageResult | None:
        """
        Triage a single screenshot.

        Args:
            screenshot_id: Unique identifier for the screenshot
            screenshot_path: Path to the screenshot image
            timestamp: When the screenshot was captured
            context: Optional context (app name, window title, etc.)

        Returns:
            TriageResult with classification and score, or None on failure
        """
        screenshot_path = Path(screenshot_path)

        if not screenshot_path.exists():
            logger.error(f"Screenshot not found: {screenshot_path}")
            return None

        # Encode image to base64
        try:
            image_data = self._encode_image(screenshot_path)
        except Exception as e:
            logger.error(f"Failed to encode image {screenshot_path}: {e}")
            return None

        # Build the prompt with optional context
        user_content = [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{image_data}",
                    "detail": "low",  # Use low detail for faster/cheaper triage
                },
            },
            {"type": "text", "text": TRIAGE_USER_PROMPT},
        ]

        if context:
            context_text = f"\nContext: App={context.get('app_name', 'unknown')}, Window={context.get('window_title', 'unknown')}"
            user_content.append({"type": "text", "text": context_text})

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": TRIAGE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                max_completion_tokens=256,
                response_format={"type": "json_object"},
            )

            response_text = response.choices[0].message.content or "{}"
            result = json.loads(response_text)

            # Parse the response
            category_str = result.get("category", "other").lower()
            try:
                category = FrameCategory(category_str)
            except ValueError:
                category = FrameCategory.OTHER

            importance_score = float(result.get("importance_score", 0.5))
            importance_score = max(0.0, min(1.0, importance_score))

            return TriageResult(
                screenshot_id=screenshot_id,
                screenshot_path=screenshot_path,
                timestamp=timestamp,
                category=category,
                importance_score=importance_score,
                description=result.get("description", ""),
                has_text=bool(result.get("has_text", False)),
                has_document=bool(result.get("has_document", False)),
                has_media=bool(result.get("has_media", False)),
                raw_response=result,
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse triage response: {e}")
            return None
        except Exception as e:
            logger.error(f"Triage API call failed for {screenshot_path}: {e}")
            return None

    def triage_batch(
        self,
        screenshots: list[dict],
        max_concurrent: int = 5,
    ) -> list[TriageResult]:
        """
        Triage multiple screenshots.

        Args:
            screenshots: List of dicts with 'screenshot_id', 'path', 'timestamp', optional 'context'
            max_concurrent: Maximum concurrent API calls (for future async implementation)

        Returns:
            List of TriageResults (may be fewer than inputs if some fail)
        """
        results = []
        for ss in screenshots:
            result = self.triage(
                screenshot_id=ss["screenshot_id"],
                screenshot_path=ss["path"],
                timestamp=ss["timestamp"],
                context=ss.get("context"),
            )
            if result:
                results.append(result)
        return results

    def _encode_image(self, image_path: Path) -> str:
        """Encode image to base64 string."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")


# Simple heuristic-based fallback triager for when API is unavailable
class HeuristicTriager:
    """
    Fallback triager using simple heuristics when API is unavailable.

    Uses app name, window title, and diff score to estimate importance.
    """

    # App categories by bundle ID prefix
    APP_CATEGORIES = {
        "com.apple.Preview": FrameCategory.DOCUMENT,
        "com.adobe.Reader": FrameCategory.DOCUMENT,
        "com.microsoft.Word": FrameCategory.DOCUMENT,
        "com.microsoft.Excel": FrameCategory.DOCUMENT,
        "com.microsoft.PowerPoint": FrameCategory.DOCUMENT,
        "com.apple.Safari": FrameCategory.BROWSING,
        "com.google.Chrome": FrameCategory.BROWSING,
        "org.mozilla.firefox": FrameCategory.BROWSING,
        "com.apple.mail": FrameCategory.COMMUNICATION,
        "com.microsoft.Outlook": FrameCategory.COMMUNICATION,
        "com.tinyspeck.slackmacgap": FrameCategory.COMMUNICATION,
        "com.apple.MobileSMS": FrameCategory.COMMUNICATION,
        "us.zoom.xos": FrameCategory.COMMUNICATION,
        "com.spotify.client": FrameCategory.MEDIA,
        "com.apple.Music": FrameCategory.MEDIA,
        "com.apple.TV": FrameCategory.MEDIA,
        "tv.plex.": FrameCategory.MEDIA,
        "com.apple.Xcode": FrameCategory.CREATIVE,
        "com.microsoft.VSCode": FrameCategory.CREATIVE,
        "com.jetbrains.": FrameCategory.CREATIVE,
        "com.figma.Desktop": FrameCategory.CREATIVE,
        "com.adobe.Photoshop": FrameCategory.CREATIVE,
        "com.valvesoftware.steam": FrameCategory.GAMING,
        "com.apple.finder": FrameCategory.OTHER,
        "com.apple.Terminal": FrameCategory.CREATIVE,
    }

    def triage(
        self,
        screenshot_id: str,
        screenshot_path: Path | str,
        timestamp: datetime,
        app_id: str | None = None,
        window_title: str | None = None,
        diff_score: float = 0.5,
    ) -> TriageResult:
        """
        Triage using heuristics only.

        Args:
            screenshot_id: Unique identifier for the screenshot
            screenshot_path: Path to the screenshot image
            timestamp: When the screenshot was captured
            app_id: Bundle ID of the foreground app
            window_title: Window title
            diff_score: Perceptual difference from previous frame (0-1)

        Returns:
            TriageResult based on heuristics
        """
        screenshot_path = Path(screenshot_path)

        # Determine category from app
        category = FrameCategory.OTHER
        if app_id:
            for prefix, cat in self.APP_CATEGORIES.items():
                if app_id.startswith(prefix):
                    category = cat
                    break

        # Estimate importance from diff score and category
        # High diff = likely transition or important moment
        importance_score = diff_score * 0.6 + 0.2  # Base importance

        # Boost for certain categories
        if category in (FrameCategory.DOCUMENT, FrameCategory.CREATIVE):
            importance_score += 0.1
        if category == FrameCategory.TRANSITION:
            importance_score = max(importance_score, 0.8)

        importance_score = max(0.0, min(1.0, importance_score))

        # Guess content flags
        has_document = category == FrameCategory.DOCUMENT
        has_media = category == FrameCategory.MEDIA
        has_text = category in (
            FrameCategory.DOCUMENT,
            FrameCategory.BROWSING,
            FrameCategory.COMMUNICATION,
            FrameCategory.CREATIVE,
        )

        # Build description
        app_name = app_id.split(".")[-1] if app_id else "Unknown"
        description = f"{app_name}"
        if window_title:
            description += f" - {window_title[:50]}"

        return TriageResult(
            screenshot_id=screenshot_id,
            screenshot_path=screenshot_path,
            timestamp=timestamp,
            category=category,
            importance_score=importance_score,
            description=description,
            has_text=has_text,
            has_document=has_document,
            has_media=has_media,
            raw_response=None,
        )


if __name__ == "__main__":
    import fire

    def triage_single(
        screenshot_path: str,
        screenshot_id: str = "test",
        use_heuristic: bool = False,
        app_id: str | None = None,
        window_title: str | None = None,
    ):
        """Triage a single screenshot."""
        path = Path(screenshot_path)
        if not path.exists():
            return {"error": f"Screenshot not found: {screenshot_path}"}

        timestamp = datetime.now()

        if use_heuristic:
            triager = HeuristicTriager()
            result = triager.triage(
                screenshot_id=screenshot_id,
                screenshot_path=path,
                timestamp=timestamp,
                app_id=app_id,
                window_title=window_title,
                diff_score=0.5,
            )
        else:
            triager = FrameTriager()
            context = {}
            if app_id:
                context["app_name"] = app_id
            if window_title:
                context["window_title"] = window_title

            result = triager.triage(
                screenshot_id=screenshot_id,
                screenshot_path=path,
                timestamp=timestamp,
                context=context if context else None,
            )

        if result is None:
            return {"error": "Triage failed"}

        return {
            "screenshot_id": result.screenshot_id,
            "category": result.category.value,
            "importance_score": result.importance_score,
            "description": result.description,
            "has_text": result.has_text,
            "has_document": result.has_document,
            "has_media": result.has_media,
        }

    fire.Fire({"triage": triage_single})
