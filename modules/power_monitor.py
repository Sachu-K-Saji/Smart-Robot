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

                    logger.debug(f"Battery: {voltage:.2f}V ({percent:.1f}%)")

                    if percent < BATTERY_CRITICAL_THRESHOLD and self._on_critical:
                        self._on_critical(percent)
                    elif percent < BATTERY_LOW_THRESHOLD and self._on_low:
                        self._on_low(percent)

                except Exception as e:
                    logger.error(f"Battery read error: {e}")

            time.sleep(BATTERY_CHECK_INTERVAL)

    def _read_bus_voltage(self) -> float:
        """Read bus voltage from INA219 via I2C."""
        raw = self._bus.read_word_data(UPS_I2C_ADDRESS, self._REG_BUS_VOLTAGE)
        raw = ((raw & 0xFF) << 8) | ((raw >> 8) & 0xFF)
        voltage = ((raw >> 3) * 4) / 1000.0
        return voltage

    @staticmethod
    def _voltage_to_percent(voltage: float) -> float:
        """Convert battery voltage to approximate percentage (2S Li-ion pack)."""
        min_v = 6.0
        max_v = 8.4
        percent = ((voltage - min_v) / (max_v - min_v)) * 100.0
        return max(0.0, min(100.0, percent))
