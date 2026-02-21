"""
Video playback controller using python-vlc.
Plays pre-recorded navigation guide videos.
"""
import logging
import os
import time

from config import VIDEO_DIR

logger = logging.getLogger(__name__)

try:
    import vlc
    VLC_AVAILABLE = True
except (ImportError, OSError):
    VLC_AVAILABLE = False
    logger.warning("python-vlc not available or VLC not installed. Video playback disabled.")


class VideoPlayer:
    """Wrapper around python-vlc for playing navigation guide videos."""

    def __init__(self):
        self.is_mock = not VLC_AVAILABLE
        self._instance = None
        self._player = None

        if not self.is_mock:
            self._instance = vlc.Instance("--no-xlib")
            self._player = self._instance.media_player_new()

    def play(self, video_filename: str, fullscreen: bool = True) -> bool:
        """
        Play a video file.

        Args:
            video_filename: Filename relative to VIDEO_DIR, or absolute path.
            fullscreen: Whether to play in fullscreen mode.

        Returns:
            True if playback started successfully, False otherwise.
        """
        if self.is_mock:
            logger.info(f"[MOCK VIDEO] Would play: {video_filename}")
            print(f"[MOCK VIDEO]: Playing {video_filename}")
            return True

        if not os.path.isabs(video_filename):
            video_path = os.path.join(VIDEO_DIR, video_filename)
        else:
            video_path = video_filename

        if not os.path.exists(video_path):
            logger.error(f"Video file not found: {video_path}")
            return False

        media = self._instance.media_new(video_path)
        self._player.set_media(media)
        self._player.set_fullscreen(fullscreen)
        self._player.play()
        logger.info(f"Playing video: {video_path}")
        return True

    def stop(self):
        """Stop the currently playing video."""
        if not self.is_mock and self._player:
            self._player.stop()

    def is_playing(self) -> bool:
        """Check if a video is currently playing."""
        if self.is_mock:
            return False
        if self._player:
            return self._player.is_playing() == 1
        return False

    def wait_for_completion(self, poll_interval: float = 0.5):
        """Block until the current video finishes playing."""
        if self.is_mock:
            return
        while self.is_playing():
            time.sleep(poll_interval)

    def close(self):
        """Release VLC resources."""
        if self._player:
            self._player.stop()
            self._player.release()
        if self._instance:
            self._instance.release()
