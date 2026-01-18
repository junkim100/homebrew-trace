"""
Tests for macOS permission management.
"""

import sys
from unittest import mock

import pytest

from src.platform.permissions import (
    AllPermissionsState,
    Permission,
    PermissionState,
    PermissionStatus,
    check_all_permissions,
    check_permission,
    get_permission_instructions,
)


class TestPermission:
    """Tests for Permission enum."""

    def test_permission_values(self):
        """Test that permission values are correct."""
        assert Permission.SCREEN_RECORDING.value == "screen_recording"
        assert Permission.ACCESSIBILITY.value == "accessibility"
        assert Permission.LOCATION.value == "location"

    def test_permission_from_string(self):
        """Test creating Permission from string."""
        assert Permission("screen_recording") == Permission.SCREEN_RECORDING
        assert Permission("accessibility") == Permission.ACCESSIBILITY
        assert Permission("location") == Permission.LOCATION

    def test_invalid_permission(self):
        """Test that invalid permission raises ValueError."""
        with pytest.raises(ValueError):
            Permission("invalid")


class TestPermissionStatus:
    """Tests for PermissionStatus enum."""

    def test_status_values(self):
        """Test that status values are correct."""
        assert PermissionStatus.GRANTED.value == "granted"
        assert PermissionStatus.DENIED.value == "denied"
        assert PermissionStatus.NOT_DETERMINED.value == "not_determined"
        assert PermissionStatus.RESTRICTED.value == "restricted"


class TestPermissionState:
    """Tests for PermissionState model."""

    def test_permission_state_creation(self):
        """Test creating a PermissionState."""
        state = PermissionState(
            permission=Permission.SCREEN_RECORDING,
            status=PermissionStatus.GRANTED,
            required=True,
            can_request=False,
        )
        assert state.permission == Permission.SCREEN_RECORDING
        assert state.status == PermissionStatus.GRANTED
        assert state.required is True
        assert state.can_request is False

    def test_permission_state_defaults(self):
        """Test PermissionState default values."""
        state = PermissionState(
            permission=Permission.LOCATION,
            status=PermissionStatus.NOT_DETERMINED,
        )
        assert state.required is True
        assert state.can_request is True


class TestCheckPermission:
    """Tests for check_permission function."""

    def test_check_permission_returns_state(self):
        """Test that check_permission returns a PermissionState."""
        state = check_permission(Permission.SCREEN_RECORDING)
        assert isinstance(state, PermissionState)
        assert state.permission == Permission.SCREEN_RECORDING
        assert isinstance(state.status, PermissionStatus)

    def test_check_all_permissions_returns_all_states(self):
        """Test that check_all_permissions returns AllPermissionsState."""
        state = check_all_permissions()
        assert isinstance(state, AllPermissionsState)
        assert isinstance(state.screen_recording, PermissionState)
        assert isinstance(state.accessibility, PermissionState)
        assert isinstance(state.location, PermissionState)
        assert isinstance(state.all_granted, bool)

    def test_location_is_not_required(self):
        """Test that location permission is marked as not required."""
        state = check_permission(Permission.LOCATION)
        assert state.required is False

    def test_screen_recording_is_required(self):
        """Test that screen recording permission is marked as required."""
        state = check_permission(Permission.SCREEN_RECORDING)
        assert state.required is True

    def test_accessibility_is_required(self):
        """Test that accessibility permission is marked as required."""
        state = check_permission(Permission.ACCESSIBILITY)
        assert state.required is True


class TestGetPermissionInstructions:
    """Tests for get_permission_instructions function."""

    def test_screen_recording_instructions(self):
        """Test getting screen recording instructions."""
        instructions = get_permission_instructions(Permission.SCREEN_RECORDING)
        assert "title" in instructions
        assert "description" in instructions
        assert "steps" in instructions
        assert "system_preferences_url" in instructions
        assert instructions["requires_restart"] is True

    def test_accessibility_instructions(self):
        """Test getting accessibility instructions."""
        instructions = get_permission_instructions(Permission.ACCESSIBILITY)
        assert "title" in instructions
        assert "description" in instructions
        assert "steps" in instructions
        assert "system_preferences_url" in instructions
        assert instructions["requires_restart"] is False

    def test_location_instructions(self):
        """Test getting location instructions."""
        instructions = get_permission_instructions(Permission.LOCATION)
        assert "title" in instructions
        assert "description" in instructions
        assert "steps" in instructions
        assert "system_preferences_url" in instructions
        assert instructions["requires_restart"] is False

    def test_instructions_have_steps(self):
        """Test that instructions include steps."""
        for permission in Permission:
            instructions = get_permission_instructions(permission)
            assert isinstance(instructions.get("steps"), list)
            assert len(instructions["steps"]) > 0


class TestAllPermissionsState:
    """Tests for AllPermissionsState model."""

    def test_all_granted_when_required_granted(self):
        """Test all_granted is True when screen_recording and accessibility are granted."""
        state = AllPermissionsState(
            screen_recording=PermissionState(
                permission=Permission.SCREEN_RECORDING,
                status=PermissionStatus.GRANTED,
            ),
            accessibility=PermissionState(
                permission=Permission.ACCESSIBILITY,
                status=PermissionStatus.GRANTED,
            ),
            location=PermissionState(
                permission=Permission.LOCATION,
                status=PermissionStatus.DENIED,  # Location can be denied
            ),
            all_granted=True,
        )
        # Check that model validates the all_granted field
        assert state.all_granted is True

    def test_all_granted_false_when_screen_denied(self):
        """Test all_granted is False when screen_recording is denied."""
        state = AllPermissionsState(
            screen_recording=PermissionState(
                permission=Permission.SCREEN_RECORDING,
                status=PermissionStatus.DENIED,
            ),
            accessibility=PermissionState(
                permission=Permission.ACCESSIBILITY,
                status=PermissionStatus.GRANTED,
            ),
            location=PermissionState(
                permission=Permission.LOCATION,
                status=PermissionStatus.GRANTED,
            ),
            all_granted=False,
        )
        assert state.all_granted is False
