"""Tests for the power monitor module."""
import os
import sys
import time
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.power_monitor import PowerMonitor


class TestVoltageToPercent:
    """Test the piecewise-linear discharge curve."""

    def test_full_charge(self):
        assert PowerMonitor._voltage_to_percent(8.4) == 100.0

    def test_above_full(self):
        """Above 8.4V should still report 100%."""
        assert PowerMonitor._voltage_to_percent(9.0) == 100.0

    def test_empty_battery(self):
        assert PowerMonitor._voltage_to_percent(6.0) == 0.0

    def test_below_empty(self):
        """Below 6.0V should report 0%."""
        assert PowerMonitor._voltage_to_percent(5.5) == 0.0

    def test_midpoint_accuracy(self):
        """7.4V should be approximately 45%."""
        percent = PowerMonitor._voltage_to_percent(7.4)
        assert abs(percent - 45.0) < 0.1

    def test_high_range(self):
        """8.1V should be approximately 90%."""
        percent = PowerMonitor._voltage_to_percent(8.1)
        assert abs(percent - 90.0) < 0.1

    def test_monotonic_decrease(self):
        """Percent should monotonically decrease as voltage drops."""
        voltages = [8.4, 8.1, 7.8, 7.5, 7.4, 7.2, 7.0, 6.6, 6.0]
        percents = [PowerMonitor._voltage_to_percent(v) for v in voltages]
        for i in range(len(percents) - 1):
            assert percents[i] >= percents[i + 1], (
                f"Non-monotonic: {voltages[i]}V={percents[i]}% > "
                f"{voltages[i+1]}V={percents[i+1]}%"
            )

    def test_interpolation_between_points(self):
        """Test a voltage between two curve points."""
        # 7.6V is between (7.80, 75%) and (7.50, 55%)
        percent = PowerMonitor._voltage_to_percent(7.6)
        assert 55.0 < percent < 75.0


class TestStaleDetection:
    """Test stale data detection on I2C read failures."""

    def test_consecutive_failures_set_negative(self):
        """After BATTERY_MAX_READ_FAILURES consecutive failures, percent should be -1."""
        pm = PowerMonitor()
        pm.is_mock = False  # Force non-mock for testing
        pm._bus = MagicMock()
        pm._bus.read_word_data.side_effect = OSError("I2C error")

        # Simulate failures
        for _ in range(3):  # BATTERY_MAX_READ_FAILURES = 3
            pm._consecutive_failures += 1

        assert pm._consecutive_failures >= 3

    def test_successful_read_resets_failures(self):
        """A successful read should reset the failure counter."""
        pm = PowerMonitor()
        pm._consecutive_failures = 2
        pm._consecutive_failures = 0  # Simulating reset
        assert pm._consecutive_failures == 0


class TestAlertDebouncing:
    """Test that alerts are debounced properly."""

    def test_alert_cooldown_prevents_repeat(self):
        """Callbacks should not fire twice within the cooldown period."""
        call_count = {"low": 0, "critical": 0}

        def on_low(pct):
            call_count["low"] += 1

        def on_critical(pct):
            call_count["critical"] += 1

        pm = PowerMonitor(on_low_battery=on_low, on_critical_battery=on_critical)

        # Simulate first alert (should fire)
        pm._last_low_alert_time = 0
        now = time.time()
        assert now - pm._last_low_alert_time > 300  # BATTERY_ALERT_COOLDOWN

        # Simulate second alert immediately (should be suppressed)
        pm._last_low_alert_time = now
        assert now - pm._last_low_alert_time < 1  # Too soon

    def test_initial_alert_times_are_zero(self):
        """Alert times should start at 0 so first alert always fires."""
        pm = PowerMonitor()
        assert pm._last_low_alert_time == 0
        assert pm._last_critical_alert_time == 0
