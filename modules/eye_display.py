"""
Pygame-based animated eye display for the campus robot.
Renders two expressive eyes with blink animations and expression states.
Runs in a dedicated thread at 30 FPS.

On the Pi, this targets a 2.0" SPI TFT (320x240) via the framebuffer.
On Windows, it opens a standard pygame window for development/preview.
"""
import logging
import math
import random
import threading
import time
from enum import Enum

import pygame

from config import (
    DISPLAY_WIDTH, DISPLAY_HEIGHT, DISPLAY_FPS,
    EYE_BG_COLOR, SCLERA_COLOR, IRIS_COLOR, PUPIL_COLOR,
    LEFT_EYE_CENTER, RIGHT_EYE_CENTER,
    SCLERA_WIDTH, SCLERA_HEIGHT, IRIS_RADIUS, PUPIL_RADIUS,
    IS_PI,
)

logger = logging.getLogger(__name__)


class Expression(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"
    SLEEPING = "sleeping"


class EyeDisplay:
    """Animated robot eye display driven by a shared expression state."""

    def __init__(self):
        self._expression = Expression.IDLE
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread = None

        # Animation state
        self._blink_timer = 0.0
        self._blink_duration = 0.15
        self._blink_interval = 3.0
        self._is_blinking = False
        self._blink_progress = 0.0

        self._iris_offset_x = 0.0
        self._iris_offset_y = 0.0
        self._iris_target_x = 0.0
        self._iris_target_y = 0.0
        self._iris_speed = 0.1

        self._time_base = 0.0

    @property
    def expression(self) -> Expression:
        with self._lock:
            return self._expression

    @expression.setter
    def expression(self, value: Expression):
        with self._lock:
            self._expression = value

    def start(self):
        """Start the display thread."""
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Eye display started.")

    def stop(self):
        """Stop the display thread and close pygame."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("Eye display stopped.")

    def _run(self):
        """Main display loop running at DISPLAY_FPS."""
        try:
            pygame.init()
        except pygame.error as e:
            logger.error(f"Failed to initialize pygame: {e}")
            return

        try:
            if IS_PI:
                import os
                os.environ["SDL_FBDEV"] = "/dev/fb1"
                screen = pygame.display.set_mode(
                    (DISPLAY_WIDTH, DISPLAY_HEIGHT), pygame.FULLSCREEN
                )
            else:
                screen = pygame.display.set_mode((DISPLAY_WIDTH, DISPLAY_HEIGHT))
                pygame.display.set_caption("Campus Robot Eyes")
        except pygame.error as e:
            logger.error(f"Failed to create display: {e}")
            pygame.quit()
            return

        clock = pygame.time.Clock()
        self._time_base = time.time()

        while self._running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running = False
                    break
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self._running = False
                    break

            dt = clock.tick(DISPLAY_FPS) / 1000.0
            elapsed = time.time() - self._time_base

            self._update_animation(dt, elapsed)

            screen.fill(EYE_BG_COLOR)
            self._draw_eye(screen, LEFT_EYE_CENTER)
            self._draw_eye(screen, RIGHT_EYE_CENTER)
            pygame.display.flip()

        pygame.quit()

    def _update_animation(self, dt: float, elapsed: float):
        """Update blink, iris position, and expression-specific animations."""
        expr = self.expression

        # ── Blinking ──────────────────────────────────────────
        self._blink_timer += dt
        if expr == Expression.IDLE:
            interval = self._blink_interval + random.uniform(-0.5, 1.0)
        elif expr == Expression.SPEAKING:
            interval = 1.5
        elif expr == Expression.SLEEPING:
            interval = 0.0
        else:
            interval = self._blink_interval

        if not self._is_blinking and self._blink_timer >= interval:
            self._is_blinking = True
            self._blink_progress = 0.0
            self._blink_timer = 0.0

        if self._is_blinking:
            self._blink_progress += dt / self._blink_duration
            if self._blink_progress >= 2.0:
                self._is_blinking = False
                self._blink_progress = 0.0

        # ── Iris movement by expression ───────────────────────
        if expr == Expression.IDLE:
            self._iris_target_x = math.sin(elapsed * 0.5) * 5
            self._iris_target_y = math.cos(elapsed * 0.3) * 3
        elif expr == Expression.LISTENING:
            self._iris_target_x = 0
            self._iris_target_y = 0
        elif expr == Expression.THINKING:
            self._iris_target_x = 6
            self._iris_target_y = -6
        elif expr == Expression.SPEAKING:
            self._iris_target_x = math.sin(elapsed * 2) * 2
            self._iris_target_y = 0
        elif expr == Expression.ERROR:
            self._iris_target_x = random.uniform(-3, 3)
            self._iris_target_y = random.uniform(-3, 3)

        self._iris_offset_x += (self._iris_target_x - self._iris_offset_x) * self._iris_speed
        self._iris_offset_y += (self._iris_target_y - self._iris_offset_y) * self._iris_speed

    def _draw_eye(self, screen: pygame.Surface, center: tuple[int, int]):
        """Draw one eye at the given center position."""
        cx, cy = center
        expr = self.expression

        # ── Sclera (white oval) ───────────────────────────────
        sclera_h = SCLERA_HEIGHT
        if expr == Expression.LISTENING:
            sclera_h = int(SCLERA_HEIGHT * 1.2)
        elif expr == Expression.SLEEPING:
            sclera_h = 4

        if self._is_blinking:
            blink_factor = 1.0 - abs(self._blink_progress - 1.0)
            sclera_h = max(2, int(sclera_h * (1.0 - blink_factor * 0.9)))

        sclera_rect = pygame.Rect(
            cx - SCLERA_WIDTH, cy - sclera_h,
            SCLERA_WIDTH * 2, sclera_h * 2,
        )
        pygame.draw.ellipse(screen, SCLERA_COLOR, sclera_rect)

        if sclera_h < 8:
            return

        # ── Iris (dark circle) ────────────────────────────────
        iris_x = cx + int(self._iris_offset_x)
        iris_y = cy + int(self._iris_offset_y)

        max_offset_x = SCLERA_WIDTH - IRIS_RADIUS - 4
        max_offset_y = sclera_h - IRIS_RADIUS - 4
        iris_x = max(cx - max_offset_x, min(cx + max_offset_x, iris_x))
        iris_y = max(cy - max_offset_y, min(cy + max_offset_y, iris_y))

        iris_color = IRIS_COLOR
        if expr == Expression.ERROR:
            iris_color = (180, 0, 0)

        pygame.draw.circle(screen, iris_color, (iris_x, iris_y), IRIS_RADIUS)

        # ── Pupil (small black circle) ────────────────────────
        pygame.draw.circle(screen, PUPIL_COLOR, (iris_x, iris_y), PUPIL_RADIUS)

        # ── Highlight (specular reflection dot) ───────────────
        highlight_x = iris_x - 4
        highlight_y = iris_y - 4
        pygame.draw.circle(screen, (255, 255, 255), (highlight_x, highlight_y), 3)
