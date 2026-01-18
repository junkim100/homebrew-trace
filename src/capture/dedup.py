"""
Screenshot Deduplication for Trace

Uses perceptual hashing to detect near-duplicate screenshots.
This allows skipping storage of screenshots that are essentially identical
to the previous frame, saving disk space and processing time.

P3-02: Screenshot deduplication
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import imagehash
from PIL import Image

logger = logging.getLogger(__name__)

# Default threshold for considering images as duplicates.
# imagehash returns a hash object that can be compared using hamming distance.
# Lower values mean stricter matching (images must be more similar).
# Typical values: 0 = exact match, 1-5 = very similar, 10+ = different images
DEFAULT_SIMILARITY_THRESHOLD = 5


@dataclass
class HashResult:
    """Result of computing a perceptual hash."""

    hash_str: str
    hash_value: imagehash.ImageHash


@dataclass
class DuplicateCheckResult:
    """Result of checking for duplicate images."""

    is_duplicate: bool
    current_hash: str
    previous_hash: str | None
    hamming_distance: int | None


def compute_perceptual_hash(
    image_or_path: Image.Image | Path | str,
    hash_size: int = 16,
) -> HashResult:
    """
    Compute a perceptual hash for an image.

    Uses the difference hash (dHash) algorithm which is robust to:
    - Minor color adjustments
    - Scaling
    - Aspect ratio changes

    Args:
        image_or_path: PIL Image object or path to image file
        hash_size: Size of the hash (larger = more precise but slower)

    Returns:
        HashResult with string and ImageHash representations
    """
    if isinstance(image_or_path, (str, Path)):
        image = Image.open(image_or_path)
    else:
        image = image_or_path

    # Use difference hash (dHash) for better robustness
    hash_value = imagehash.dhash(image, hash_size=hash_size)

    return HashResult(
        hash_str=str(hash_value),
        hash_value=hash_value,
    )


def compute_hamming_distance(
    hash1: str | imagehash.ImageHash,
    hash2: str | imagehash.ImageHash,
) -> int:
    """
    Compute the Hamming distance between two hashes.

    The Hamming distance is the number of positions at which the
    corresponding bits differ. A distance of 0 means identical hashes.

    Args:
        hash1: First hash (string or ImageHash)
        hash2: Second hash (string or ImageHash)

    Returns:
        Integer hamming distance
    """
    if isinstance(hash1, str):
        hash1 = imagehash.hex_to_hash(hash1)
    if isinstance(hash2, str):
        hash2 = imagehash.hex_to_hash(hash2)

    return hash1 - hash2


def is_duplicate(
    current_hash: str | imagehash.ImageHash,
    previous_hash: str | imagehash.ImageHash | None,
    threshold: int = DEFAULT_SIMILARITY_THRESHOLD,
) -> DuplicateCheckResult:
    """
    Check if the current image is a duplicate of the previous one.

    Args:
        current_hash: Hash of the current image
        previous_hash: Hash of the previous image (or None if no previous)
        threshold: Maximum hamming distance to consider as duplicate

    Returns:
        DuplicateCheckResult with duplicate status and details
    """
    if isinstance(current_hash, imagehash.ImageHash):
        current_hash_str = str(current_hash)
    else:
        current_hash_str = current_hash

    if previous_hash is None:
        return DuplicateCheckResult(
            is_duplicate=False,
            current_hash=current_hash_str,
            previous_hash=None,
            hamming_distance=None,
        )

    if isinstance(previous_hash, imagehash.ImageHash):
        previous_hash_str = str(previous_hash)
    else:
        previous_hash_str = previous_hash

    distance = compute_hamming_distance(current_hash, previous_hash)

    return DuplicateCheckResult(
        is_duplicate=distance <= threshold,
        current_hash=current_hash_str,
        previous_hash=previous_hash_str,
        hamming_distance=distance,
    )


class DuplicateTracker:
    """
    Tracks screenshot hashes per monitor for deduplication.

    Maintains the most recent hash for each monitor to enable
    per-monitor duplicate detection.
    """

    def __init__(self, threshold: int = DEFAULT_SIMILARITY_THRESHOLD):
        """
        Initialize the duplicate tracker.

        Args:
            threshold: Hamming distance threshold for duplicate detection
        """
        self.threshold = threshold
        self._last_hashes: dict[int, str] = {}

    def check_and_update(
        self,
        monitor_id: int,
        image_or_path: Image.Image | Path | str,
    ) -> DuplicateCheckResult:
        """
        Check if an image is a duplicate and update the tracker.

        Args:
            monitor_id: ID of the monitor the screenshot is from
            image_or_path: Image or path to check

        Returns:
            DuplicateCheckResult with duplicate status
        """
        hash_result = compute_perceptual_hash(image_or_path)
        previous_hash = self._last_hashes.get(monitor_id)

        result = is_duplicate(
            current_hash=hash_result.hash_str,
            previous_hash=previous_hash,
            threshold=self.threshold,
        )

        # Always update the hash, even for duplicates
        # This allows for gradual drift detection
        self._last_hashes[monitor_id] = hash_result.hash_str

        return result

    def get_last_hash(self, monitor_id: int) -> str | None:
        """Get the last hash for a monitor."""
        return self._last_hashes.get(monitor_id)

    def clear(self, monitor_id: int | None = None) -> None:
        """
        Clear tracked hashes.

        Args:
            monitor_id: Specific monitor to clear, or None for all
        """
        if monitor_id is None:
            self._last_hashes.clear()
        else:
            self._last_hashes.pop(monitor_id, None)


def compute_diff_score(
    hash1: str | imagehash.ImageHash,
    hash2: str | imagehash.ImageHash,
) -> float:
    """
    Compute a normalized difference score between two hashes.

    Returns a value between 0.0 (identical) and 1.0 (completely different).
    This is useful for storing as a metric in the database.

    Args:
        hash1: First hash
        hash2: Second hash

    Returns:
        Float between 0.0 and 1.0
    """
    distance = compute_hamming_distance(hash1, hash2)

    # For a 16x16 hash, max distance is 256 bits
    # Normalize to 0-1 range
    max_distance = 256  # 16 * 16 bits
    return min(distance / max_distance, 1.0)


if __name__ == "__main__":
    import fire

    def hash_image(path: str):
        """Compute perceptual hash for an image."""
        result = compute_perceptual_hash(path)
        return {"hash": result.hash_str}

    def compare(path1: str, path2: str, threshold: int = DEFAULT_SIMILARITY_THRESHOLD):
        """Compare two images for similarity."""
        hash1 = compute_perceptual_hash(path1)
        hash2 = compute_perceptual_hash(path2)
        distance = compute_hamming_distance(hash1.hash_str, hash2.hash_str)
        diff_score = compute_diff_score(hash1.hash_str, hash2.hash_str)

        return {
            "hash1": hash1.hash_str,
            "hash2": hash2.hash_str,
            "hamming_distance": distance,
            "diff_score": diff_score,
            "is_duplicate": distance <= threshold,
            "threshold": threshold,
        }

    fire.Fire(
        {
            "hash": hash_image,
            "compare": compare,
        }
    )
