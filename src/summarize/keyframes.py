"""
Keyframe Selection Algorithm for Trace

Selects representative screenshots (keyframes) for hourly summarization.
Uses a multi-factor selection strategy:
1. Transition frames (app/window changes)
2. High diff-score frames (significant visual changes)
3. Periodic anchors (ensure coverage during long sessions)
4. Importance score from triage (when available)

P5-02: Keyframe selection algorithm
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from src.summarize.triage import FrameCategory, TriageResult

logger = logging.getLogger(__name__)

# Selection parameters
DEFAULT_MAX_KEYFRAMES = 15  # Maximum keyframes per hour
DEFAULT_TRANSITION_WEIGHT = 1.0  # Weight for transition frames
DEFAULT_DIFF_WEIGHT = 0.6  # Weight for high-diff frames
DEFAULT_ANCHOR_INTERVAL_SECONDS = 300  # 5 minutes between anchors
DEFAULT_MIN_IMPORTANCE = 0.3  # Minimum importance to consider
DEFAULT_DIVERSITY_WINDOW_SECONDS = 30  # Minimum seconds between selected frames


@dataclass
class SelectedKeyframe:
    """A screenshot selected as a keyframe for summarization."""

    screenshot_id: str
    screenshot_path: Path
    timestamp: datetime
    selection_reason: str  # 'transition', 'high_diff', 'anchor', 'importance'
    combined_score: float  # Final selection score
    triage_result: TriageResult | None = None

    # Source metadata
    app_id: str | None = None
    app_name: str | None = None
    window_title: str | None = None
    monitor_id: int | None = None
    diff_score: float = 0.0


@dataclass
class ScreenshotCandidate:
    """A screenshot candidate for keyframe selection."""

    screenshot_id: str
    screenshot_path: Path
    timestamp: datetime
    monitor_id: int
    diff_score: float
    fingerprint: str

    # Optional metadata
    app_id: str | None = None
    app_name: str | None = None
    window_title: str | None = None

    # From triage (if performed)
    triage_result: TriageResult | None = None

    # Derived flags
    is_transition: bool = False  # App/window changed from previous


class KeyframeSelector:
    """
    Selects representative keyframes from screenshot candidates.

    Uses a multi-factor scoring system to ensure good coverage:
    - Transition frames capture context switches
    - High diff frames capture significant changes
    - Periodic anchors ensure long sessions are represented
    - Triage importance boosts visually interesting frames
    """

    def __init__(
        self,
        max_keyframes: int = DEFAULT_MAX_KEYFRAMES,
        transition_weight: float = DEFAULT_TRANSITION_WEIGHT,
        diff_weight: float = DEFAULT_DIFF_WEIGHT,
        anchor_interval_seconds: int = DEFAULT_ANCHOR_INTERVAL_SECONDS,
        min_importance: float = DEFAULT_MIN_IMPORTANCE,
        diversity_window_seconds: int = DEFAULT_DIVERSITY_WINDOW_SECONDS,
    ):
        """
        Initialize the keyframe selector.

        Args:
            max_keyframes: Maximum number of keyframes to select
            transition_weight: Score weight for transition frames
            diff_weight: Score weight for high-diff frames
            anchor_interval_seconds: Minimum interval for periodic anchors
            min_importance: Minimum triage importance to consider
            diversity_window_seconds: Minimum time gap between selected frames
        """
        self.max_keyframes = max_keyframes
        self.transition_weight = transition_weight
        self.diff_weight = diff_weight
        self.anchor_interval_seconds = anchor_interval_seconds
        self.min_importance = min_importance
        self.diversity_window_seconds = diversity_window_seconds

    def select(
        self,
        candidates: list[ScreenshotCandidate],
    ) -> list[SelectedKeyframe]:
        """
        Select keyframes from a list of screenshot candidates.

        Args:
            candidates: List of screenshot candidates for the hour

        Returns:
            List of selected keyframes, ordered by timestamp
        """
        if not candidates:
            return []

        # Sort by timestamp
        sorted_candidates = sorted(candidates, key=lambda c: c.timestamp)

        # Phase 1: Identify transitions
        self._mark_transitions(sorted_candidates)

        # Phase 2: Score all candidates
        scored = self._score_candidates(sorted_candidates)

        # Phase 3: Select with diversity constraint
        selected = self._select_with_diversity(scored)

        # Phase 4: Add periodic anchors if needed
        selected = self._add_anchors(selected, sorted_candidates)

        # Sort final selection by timestamp
        selected.sort(key=lambda k: k.timestamp)

        return selected[: self.max_keyframes]

    def _mark_transitions(self, candidates: list[ScreenshotCandidate]) -> None:
        """Mark candidates that represent app/window transitions."""
        prev_app = None
        prev_window = None

        for candidate in candidates:
            # Check for app change
            if candidate.app_id != prev_app:
                candidate.is_transition = True
            # Check for significant window change
            elif candidate.window_title != prev_window and prev_window is not None:
                candidate.is_transition = True

            prev_app = candidate.app_id
            prev_window = candidate.window_title

    def _score_candidates(
        self, candidates: list[ScreenshotCandidate]
    ) -> list[tuple[ScreenshotCandidate, float, str]]:
        """
        Score all candidates for selection.

        Returns list of (candidate, score, primary_reason) tuples.
        """
        scored = []

        for candidate in candidates:
            score = 0.0
            reason = "base"

            # Transition bonus
            if candidate.is_transition:
                score += self.transition_weight
                reason = "transition"

            # Diff score contribution
            diff_contribution = candidate.diff_score * self.diff_weight
            score += diff_contribution
            if diff_contribution > 0.4 and reason == "base":
                reason = "high_diff"

            # Triage importance contribution
            if candidate.triage_result:
                triage = candidate.triage_result
                importance = triage.importance_score

                if importance >= self.min_importance:
                    score += importance * 0.5

                    # Category bonuses
                    if triage.category == FrameCategory.DOCUMENT:
                        score += 0.2
                    elif triage.category == FrameCategory.CREATIVE:
                        score += 0.15

                    if importance > 0.7 and reason not in ("transition",):
                        reason = "importance"

            scored.append((candidate, score, reason))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _select_with_diversity(
        self, scored: list[tuple[ScreenshotCandidate, float, str]]
    ) -> list[SelectedKeyframe]:
        """
        Select keyframes while maintaining temporal diversity.

        Ensures minimum time gap between selected frames.
        """
        selected = []
        selected_times: list[datetime] = []

        for candidate, score, reason in scored:
            if len(selected) >= self.max_keyframes:
                break

            # Check diversity constraint
            too_close = False
            for selected_time in selected_times:
                time_diff = abs((candidate.timestamp - selected_time).total_seconds())
                if time_diff < self.diversity_window_seconds:
                    too_close = True
                    break

            if too_close:
                continue

            # Create keyframe
            keyframe = SelectedKeyframe(
                screenshot_id=candidate.screenshot_id,
                screenshot_path=candidate.screenshot_path,
                timestamp=candidate.timestamp,
                selection_reason=reason,
                combined_score=score,
                triage_result=candidate.triage_result,
                app_id=candidate.app_id,
                app_name=candidate.app_name,
                window_title=candidate.window_title,
                monitor_id=candidate.monitor_id,
                diff_score=candidate.diff_score,
            )

            selected.append(keyframe)
            selected_times.append(candidate.timestamp)

        return selected

    def _add_anchors(
        self,
        selected: list[SelectedKeyframe],
        candidates: list[ScreenshotCandidate],
    ) -> list[SelectedKeyframe]:
        """
        Add periodic anchor frames to ensure coverage.

        If there are gaps larger than anchor_interval, add frames to fill them.
        """
        if not candidates or len(selected) >= self.max_keyframes:
            return selected

        # Build set of already selected IDs
        selected_ids = {k.screenshot_id for k in selected}

        # Find time range
        start_time = candidates[0].timestamp
        end_time = candidates[-1].timestamp

        # Identify gaps that need anchors
        anchor_interval = timedelta(seconds=self.anchor_interval_seconds)

        # Sort existing keyframes by time
        sorted_selected = sorted(selected, key=lambda k: k.timestamp)

        # Check gaps
        check_points = [start_time]
        for kf in sorted_selected:
            check_points.append(kf.timestamp)
        check_points.append(end_time)

        for i in range(len(check_points) - 1):
            gap_start = check_points[i]
            gap_end = check_points[i + 1]
            gap_duration = gap_end - gap_start

            if gap_duration > anchor_interval:
                # Find best candidate in the middle of the gap
                gap_middle = gap_start + gap_duration / 2
                best_candidate = None
                best_distance = float("inf")

                for candidate in candidates:
                    if candidate.screenshot_id in selected_ids:
                        continue
                    if candidate.timestamp < gap_start or candidate.timestamp > gap_end:
                        continue

                    distance = abs((candidate.timestamp - gap_middle).total_seconds())
                    if distance < best_distance:
                        best_distance = distance
                        best_candidate = candidate

                if best_candidate and len(selected) < self.max_keyframes:
                    keyframe = SelectedKeyframe(
                        screenshot_id=best_candidate.screenshot_id,
                        screenshot_path=best_candidate.screenshot_path,
                        timestamp=best_candidate.timestamp,
                        selection_reason="anchor",
                        combined_score=0.3,  # Base anchor score
                        triage_result=best_candidate.triage_result,
                        app_id=best_candidate.app_id,
                        app_name=best_candidate.app_name,
                        window_title=best_candidate.window_title,
                        monitor_id=best_candidate.monitor_id,
                        diff_score=best_candidate.diff_score,
                    )
                    selected.append(keyframe)
                    selected_ids.add(best_candidate.screenshot_id)

        return selected

    def select_from_db(
        self,
        screenshots: list[dict],
        events: list[dict] | None = None,
        triage_results: dict[str, TriageResult] | None = None,
    ) -> list[SelectedKeyframe]:
        """
        Select keyframes from database query results.

        Args:
            screenshots: List of screenshot dicts from database
            events: Optional list of event dicts to get app/window info
            triage_results: Optional dict mapping screenshot_id to TriageResult

        Returns:
            List of selected keyframes
        """
        # Build event lookup by time range
        event_lookup: dict[str, dict] = {}
        if events:
            for event in events:
                # Index events by ID for lookup
                event_lookup[event.get("event_id", "")] = event

        # Convert to candidates
        candidates = []
        for ss in screenshots:
            screenshot_id = ss.get("screenshot_id", "")
            ts_str = ss.get("ts", "")
            path_str = ss.get("path", "")

            try:
                timestamp = datetime.fromisoformat(ts_str)
            except (ValueError, TypeError):
                logger.warning(f"Invalid timestamp for screenshot {screenshot_id}")
                continue

            candidate = ScreenshotCandidate(
                screenshot_id=screenshot_id,
                screenshot_path=Path(path_str),
                timestamp=timestamp,
                monitor_id=ss.get("monitor_id", 0),
                diff_score=ss.get("diff_score", 0.0),
                fingerprint=ss.get("fingerprint", ""),
                app_id=ss.get("app_id"),
                app_name=ss.get("app_name"),
                window_title=ss.get("window_title"),
            )

            # Add triage result if available
            if triage_results and screenshot_id in triage_results:
                candidate.triage_result = triage_results[screenshot_id]

            candidates.append(candidate)

        return self.select(candidates)


if __name__ == "__main__":
    import fire

    def demo():
        """Demo the keyframe selector with synthetic data."""
        import random
        from datetime import datetime, timedelta

        # Create synthetic candidates
        candidates = []
        base_time = datetime.now().replace(minute=0, second=0, microsecond=0)

        apps = [
            ("com.apple.Safari", "Safari", "GitHub - Project"),
            ("com.microsoft.VSCode", "VSCode", "main.py - Project"),
            ("com.apple.Preview", "Preview", "document.pdf"),
            ("com.spotify.client", "Spotify", "Now Playing"),
        ]

        current_app_idx = 0
        for i in range(60):  # One frame per minute
            timestamp = base_time + timedelta(minutes=i)

            # Occasional app switches
            if random.random() < 0.15:
                current_app_idx = (current_app_idx + 1) % len(apps)

            app_id, app_name, window_title = apps[current_app_idx]

            candidate = ScreenshotCandidate(
                screenshot_id=f"ss_{i:03d}",
                screenshot_path=Path(f"/tmp/screenshots/frame_{i:03d}.jpg"),
                timestamp=timestamp,
                monitor_id=0,
                diff_score=random.uniform(0.1, 0.9),
                fingerprint=f"hash_{i:03d}",
                app_id=app_id,
                app_name=app_name,
                window_title=window_title,
            )
            candidates.append(candidate)

        # Run selection
        selector = KeyframeSelector(max_keyframes=10)
        keyframes = selector.select(candidates)

        result = []
        for kf in keyframes:
            result.append(
                {
                    "screenshot_id": kf.screenshot_id,
                    "timestamp": kf.timestamp.isoformat(),
                    "reason": kf.selection_reason,
                    "score": round(kf.combined_score, 2),
                    "app": kf.app_name,
                    "window": kf.window_title,
                }
            )

        return {
            "total_candidates": len(candidates),
            "selected": len(keyframes),
            "keyframes": result,
        }

    fire.Fire({"demo": demo})
