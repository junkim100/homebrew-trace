"""
Location Capture for Trace

Captures the device's current location using macOS CoreLocation framework.
Location is stored as human-readable text (city, area) rather than raw coordinates.

P3-07: Location capture
"""

import json
import logging
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

# Timeout for location requests (seconds)
LOCATION_TIMEOUT = 10


@dataclass
class Location:
    """Captured location information."""

    timestamp: datetime
    latitude: float | None
    longitude: float | None
    altitude: float | None
    horizontal_accuracy: float | None
    location_text: str | None  # Human-readable location (city, area)
    source: str  # "corelocation"

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(
            {
                "timestamp": self.timestamp.isoformat(),
                "latitude": self.latitude,
                "longitude": self.longitude,
                "altitude": self.altitude,
                "horizontal_accuracy": self.horizontal_accuracy,
                "location_text": self.location_text,
                "source": self.source,
            }
        )

    @classmethod
    def from_json(cls, json_str: str) -> "Location":
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            altitude=data.get("altitude"),
            horizontal_accuracy=data.get("horizontal_accuracy"),
            location_text=data.get("location_text"),
            source=data.get("source", "corelocation"),
        )


def _reverse_geocode_sync(latitude: float, longitude: float) -> str | None:
    """
    Perform reverse geocoding to get a human-readable location.

    Args:
        latitude: Latitude in degrees
        longitude: Longitude in degrees

    Returns:
        Human-readable location string or None
    """
    if sys.platform != "darwin":
        return None

    try:
        from CoreLocation import CLGeocoder, CLLocation

        geocoder = CLGeocoder.alloc().init()
        location = CLLocation.alloc().initWithLatitude_longitude_(latitude, longitude)

        # Use a semaphore to wait for the async result
        result = {"location_text": None, "done": False}
        lock = threading.Lock()

        def completion_handler(placemarks, error):
            with lock:
                if error:
                    logger.debug(f"Reverse geocode error: {error}")
                elif placemarks and len(placemarks) > 0:
                    placemark = placemarks[0]
                    parts = []

                    # Build location string from components
                    if placemark.subLocality():
                        parts.append(placemark.subLocality())
                    if placemark.locality():
                        parts.append(placemark.locality())
                    if placemark.administrativeArea():
                        parts.append(placemark.administrativeArea())

                    if parts:
                        result["location_text"] = ", ".join(parts)
                result["done"] = True

        geocoder.reverseGeocodeLocation_completionHandler_(location, completion_handler)

        # Wait for completion with timeout
        timeout = 5
        start = time.time()
        while not result["done"] and (time.time() - start) < timeout:
            time.sleep(0.1)

        return result["location_text"]

    except ImportError:
        logger.warning("CoreLocation not available")
        return None
    except Exception as e:
        logger.error(f"Reverse geocoding failed: {e}")
        return None


class LocationCapture:
    """
    Captures device location using CoreLocation.

    Provides both raw coordinates and reverse-geocoded location text.
    Includes caching to avoid excessive location lookups.
    """

    def __init__(self, min_interval_seconds: float = 60.0):
        """
        Initialize the location capturer.

        Args:
            min_interval_seconds: Minimum time between location updates
        """
        self.min_interval_seconds = min_interval_seconds
        self._last_location: Location | None = None
        self._last_capture_time: datetime | None = None
        self._location_manager = None
        self._delegate = None

    def _ensure_location_manager(self):
        """Ensure the location manager is initialized."""
        if sys.platform != "darwin":
            return

        if self._location_manager is not None:
            return

        try:
            from CoreLocation import CLLocationManager

            self._location_manager = CLLocationManager.alloc().init()
            # Request desired accuracy
            from CoreLocation import kCLLocationAccuracyHundredMeters

            self._location_manager.setDesiredAccuracy_(kCLLocationAccuracyHundredMeters)

        except ImportError:
            logger.warning("CoreLocation not available")
        except Exception as e:
            logger.error(f"Failed to initialize location manager: {e}")

    def capture(self, timestamp: datetime | None = None) -> Location | None:
        """
        Capture the current location.

        Args:
            timestamp: Timestamp for the capture (defaults to now)

        Returns:
            Location information or None if unavailable
        """
        if timestamp is None:
            timestamp = datetime.now()

        # Check if we need to update (respect min interval)
        if self._last_capture_time is not None:
            elapsed = (timestamp - self._last_capture_time).total_seconds()
            if elapsed < self.min_interval_seconds and self._last_location is not None:
                # Return cached location with updated timestamp
                return Location(
                    timestamp=timestamp,
                    latitude=self._last_location.latitude,
                    longitude=self._last_location.longitude,
                    altitude=self._last_location.altitude,
                    horizontal_accuracy=self._last_location.horizontal_accuracy,
                    location_text=self._last_location.location_text,
                    source=self._last_location.source,
                )

        return self._fetch_location(timestamp)

    def _fetch_location(self, timestamp: datetime) -> Location | None:
        """Fetch fresh location data."""
        if sys.platform != "darwin":
            return None

        self._ensure_location_manager()

        if self._location_manager is None:
            return None

        try:
            # Get the last known location (faster than requesting new one)
            location = self._location_manager.location()

            if location is None:
                # Try requesting a new location
                self._location_manager.startUpdatingLocation()
                time.sleep(0.5)  # Brief wait for location update
                location = self._location_manager.location()
                self._location_manager.stopUpdatingLocation()

            if location is None:
                return None

            latitude = location.coordinate().latitude
            longitude = location.coordinate().longitude
            altitude = location.altitude()
            horizontal_accuracy = location.horizontalAccuracy()

            # Reverse geocode to get human-readable location
            location_text = _reverse_geocode_sync(latitude, longitude)

            result = Location(
                timestamp=timestamp,
                latitude=latitude,
                longitude=longitude,
                altitude=altitude if altitude > -1 else None,  # -1 means invalid
                horizontal_accuracy=horizontal_accuracy if horizontal_accuracy >= 0 else None,
                location_text=location_text,
                source="corelocation",
            )

            self._last_location = result
            self._last_capture_time = timestamp

            return result

        except Exception as e:
            logger.error(f"Failed to get location: {e}")
            return None

    def get_last_location(self) -> Location | None:
        """Get the last captured location."""
        return self._last_location

    def force_refresh(self, timestamp: datetime | None = None) -> Location | None:
        """
        Force a fresh location capture, ignoring the cache.

        Args:
            timestamp: Timestamp for the capture (defaults to now)

        Returns:
            Fresh location information
        """
        if timestamp is None:
            timestamp = datetime.now()

        return self._fetch_location(timestamp)


def check_location_permission() -> bool:
    """
    Check if location permission is granted.

    Returns:
        True if location services are enabled and authorized
    """
    if sys.platform != "darwin":
        return False

    try:
        from CoreLocation import CLLocationManager

        if not CLLocationManager.locationServicesEnabled():
            return False

        status = CLLocationManager.authorizationStatus()
        # 3 = kCLAuthorizationStatusAuthorizedAlways
        # 4 = kCLAuthorizationStatusAuthorizedWhenInUse
        return status in (3, 4)

    except ImportError:
        return False
    except Exception:
        return False


if __name__ == "__main__":
    import fire

    def capture():
        """Capture current location."""
        capturer = LocationCapture()
        result = capturer.capture()
        if result:
            return json.loads(result.to_json())
        return {"error": "Location not available"}

    def check_permission():
        """Check location permission status."""
        return {"granted": check_location_permission()}

    def watch(interval: float = 30.0, count: int = 10):
        """Watch location changes."""
        capturer = LocationCapture(min_interval_seconds=0)  # Disable caching

        for i in range(count):
            result = capturer.capture()
            if result:
                print(f"[{i + 1}/{count}] {result.location_text or 'Unknown'}")
                print(f"  Lat: {result.latitude}, Lon: {result.longitude}")
                print(f"  Accuracy: {result.horizontal_accuracy}m")
            else:
                print(f"[{i + 1}/{count}] Location unavailable")
            time.sleep(interval)

    fire.Fire(
        {
            "capture": capture,
            "check": check_permission,
            "watch": watch,
        }
    )
