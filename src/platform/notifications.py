"""
macOS Notification Support for Trace

Provides native macOS notifications for service status updates,
errors, and important events.

Uses NSUserNotificationCenter for compatibility without requiring
special entitlements.
"""

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class NotificationType(str, Enum):
    """Types of notifications."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"


def send_notification(
    title: str,
    message: str,
    subtitle: str | None = None,
    sound: bool = True,
    notification_type: NotificationType = NotificationType.INFO,
) -> bool:
    """
    Send a macOS notification.

    Args:
        title: Notification title
        message: Main notification message
        subtitle: Optional subtitle
        sound: Whether to play notification sound
        notification_type: Type of notification (for logging)

    Returns:
        True if notification was sent successfully, False otherwise
    """
    try:
        # Import here to avoid issues on non-macOS platforms
        from Foundation import NSUserNotification, NSUserNotificationCenter

        notification = NSUserNotification.alloc().init()
        notification.setTitle_(title)
        notification.setInformativeText_(message)

        if subtitle:
            notification.setSubtitle_(subtitle)

        if sound:
            notification.setSoundName_("default")

        center = NSUserNotificationCenter.defaultUserNotificationCenter()
        center.deliverNotification_(notification)

        logger.debug(f"Notification sent: {title} - {message}")
        return True

    except ImportError:
        logger.warning("NSUserNotification not available - notifications disabled")
        return False
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
        return False


def send_error_notification(error: str, context: str | None = None) -> bool:
    """
    Send an error notification.

    Args:
        error: Error message
        context: Optional context about where the error occurred

    Returns:
        True if notification was sent successfully
    """
    title = "Trace Error"
    message = error
    subtitle = context

    logger.error(f"Error notification: {error} (context: {context})")

    return send_notification(
        title=title,
        message=message,
        subtitle=subtitle,
        sound=True,
        notification_type=NotificationType.ERROR,
    )


def send_service_notification(service: str, status: str, details: str | None = None) -> bool:
    """
    Send a service status notification.

    Args:
        service: Service name (e.g., 'capture', 'hourly', 'daily')
        status: Status message (e.g., 'started', 'stopped', 'failed')
        details: Optional additional details

    Returns:
        True if notification was sent successfully
    """
    title = f"Trace - {service.title()}"
    message = status.title()

    # Determine notification type based on status
    if "fail" in status.lower() or "error" in status.lower():
        notification_type = NotificationType.ERROR
    elif "start" in status.lower() or "success" in status.lower():
        notification_type = NotificationType.SUCCESS
    elif "stop" in status.lower() or "warn" in status.lower():
        notification_type = NotificationType.WARNING
    else:
        notification_type = NotificationType.INFO

    return send_notification(
        title=title,
        message=message,
        subtitle=details,
        sound=notification_type == NotificationType.ERROR,
        notification_type=notification_type,
    )


def send_backfill_notification(hours_count: int, status: str = "started") -> bool:
    """
    Send a notification about backfill operation.

    Args:
        hours_count: Number of hours being backfilled
        status: 'started' or 'completed'

    Returns:
        True if notification was sent successfully
    """
    if status == "started":
        title = "Trace - Backfill Started"
        message = f"Generating {hours_count} missing note{'s' if hours_count > 1 else ''}"
    else:
        title = "Trace - Backfill Complete"
        message = f"Generated {hours_count} note{'s' if hours_count > 1 else ''}"

    return send_notification(
        title=title,
        message=message,
        sound=False,
        notification_type=NotificationType.INFO,
    )


def send_critical_notification(title: str, message: str) -> bool:
    """
    Send a critical notification that requires attention.

    Args:
        title: Notification title
        message: Critical message

    Returns:
        True if notification was sent successfully
    """
    logger.critical(f"Critical notification: {title} - {message}")

    return send_notification(
        title=f"Trace - {title}",
        message=message,
        sound=True,
        notification_type=NotificationType.ERROR,
    )


if __name__ == "__main__":
    import fire

    def test():
        """Test notification sending."""
        print("Sending test notification...")
        result = send_notification(
            title="Trace Test",
            message="This is a test notification",
            subtitle="Testing notifications",
            sound=True,
        )
        print(f"Result: {result}")
        return {"success": result}

    def error(message: str = "Test error"):
        """Test error notification."""
        result = send_error_notification(message, "Test context")
        return {"success": result}

    def service(name: str = "capture", status: str = "started"):
        """Test service notification."""
        result = send_service_notification(name, status)
        return {"success": result}

    fire.Fire({"test": test, "error": error, "service": service})
