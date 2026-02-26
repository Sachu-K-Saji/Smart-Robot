"""
Battery level monitor for Waveshare UPS HAT via I2C.
Reads voltage from INA219 sensor every N seconds.
Stubs out to always-100% on non-Pi platforms.
"""
import logging
import threading
import time
from typing import Optional, Callable

from config import (
    IS_PI, UPS_I2C_ADDRESS,
    BATTERY_CHECK_INTERVAL,
    BATTERY_LOW_THRESHOLD,
    BATTERY_CRITICAL_THRESHOLD,
    BATTERY_STALE_THRESHOLD,
    BATTERY_MAX_READ_FAILURES,
    BATTERY_ALERT_COOLDOWN,
)

logger = logging.getLogger(__name__)

try:
    import smbus2
    SMBUS_AVAILABLE = True
except ImportError:
    SMBUS_AVAILABLE = False


class PowerMonitor:
    """
    Monitor battery level from Waveshare UPS HAT.
    Calls callbacks when battery is low or critical.
    """

    _REG_BUS_VOLTAGE = 0x02
    _REG_CURRENT = 0x04

    # 2S Li-ion pack voltage-to-percent (piecewise linear)
    _DISCHARGE_CURVE = [
        (8.40, 100.0),
        (8.10,  90.0),
        (7.80,  75.0),
        (7.50,  55.0),
        (7.40,  45.0),
        (7.20,  30.0),
        (7.00,  15.0),
        (6.60,   5.0),
        (6.00,   0.0),
    ]

    def __init__(
        self,
        on_low_battery: Optional[Callable[[float], None]] = None,
        on_critical_battery: Optional[Callable[[float], None]] = None,
    ):
        self.is_mock = not (IS_PI and SMBUS_AVAILABLE)
        self._on_low = on_low_battery
        self._on_critical = on_critical_battery
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._battery_percent = 100.0
        self._lock = threading.Lock()

        # Stale data tracking
        self._last_successful_read = time.time()
        self._consecutive_failures = 0

        # Alert debouncing
        self._last_low_alert_time = 0
        self._last_critical_alert_time = 0

        if not self.is_mock:
            self._bus = smbus2.SMBus(1)
        else:
            self._bus = None
            logger.info("PowerMonitor running in mock mode (always 100%).")

    @property
    def battery_percent(self) -> float:
        with self._lock:
            return self._battery_percent

    def start(self):
        """Start the battery monitoring thread."""
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("Power monitor started (mock=%s).", self.is_mock)

    def stop(self):
        """Stop the monitoring thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=BATTERY_CHECK_INTERVAL + 1)

    def _monitor_loop(self):
        """Poll battery voltage every BATTERY_CHECK_INTERVAL seconds."""
        while self._running:
            if self.is_mock:
                with self._lock:
                    self._battery_percent = 100.0
            else:
                try:
                    voltage = self._read_bus_voltage()
                    percent = self._voltage_to_percent(voltage)
                    with self._lock:
                        self._battery_percent = percent

                    # Successful read: reset failure tracking
                    self._consecutive_failures = 0
                    self._last_successful_read = time.time()

                    logger.debug(f"Battery: {voltage:.2f}V ({percent:.1f}%)")

                    now = time.time()
                    if percent < BATTERY_CRITICAL_THRESHOLD and self._on_critical:
                        if now - self._last_critical_alert_time > BATTERY_ALERT_COOLDOWN:
                            self._on_critical(percent)
                            self._last_critical_alert_time = now
                    elif percent < BATTERY_LOW_THRESHOLD and self._on_low:
                        if now - self._last_low_alert_time > BATTERY_ALERT_COOLDOWN:
                            self._on_low(percent)
                            self._last_low_alert_time = now

                except Exception as e:
                    logger.error(f"Battery read error: {e}")
                    self._consecutive_failures += 1

                    if self._consecutive_failures >= BATTERY_MAX_READ_FAILURES:
                        with self._lock:
                            self._battery_percent = -1.0

                    if time.time() - self._last_successful_read > BATTERY_STALE_THRESHOLD:
                        logger.warning(
                            f"Battery data is stale: no successful read for "
                            f"{time.time() - self._last_successful_read:.0f}s"
                        )

            time.sleep(BATTERY_CHECK_INTERVAL)

    def _read_bus_voltage(self) -> float:
        """Read bus voltage from INA219 via I2C."""
        raw = self._bus.read_word_data(UPS_I2C_ADDRESS, self._REG_BUS_VOLTAGE)
        raw = ((raw & 0xFF) << 8) | ((raw >> 8) & 0xFF)
        voltage = ((raw >> 3) * 4) / 1000.0
        return voltage

    @staticmethod
    def _voltage_to_percent(voltage: float) -> float:
        """Convert battery voltage to approximate percentage using a
        piecewise-linear interpolation over the 2S Li-ion discharge curve."""
        curve = PowerMonitor._DISCHARGE_CURVE

        # Above the highest point in the curve
        if voltage >= curve[0][0]:
            return curve[0][1]

        # Below the lowest point in the curve
        if voltage <= curve[-1][0]:
            return curve[-1][1]

        # Find the two surrounding points and interpolate
        for i in range(len(curve) - 1):
            v_high, p_high = curve[i]
            v_low, p_low = curve[i + 1]
            if v_low <= voltage <= v_high:
                # Linear interpolation between the two points
                ratio = (voltage - v_low) / (v_high - v_low)
                return p_low + ratio * (p_high - p_low)

        # Fallback (should not be reached)
        return 0.0
