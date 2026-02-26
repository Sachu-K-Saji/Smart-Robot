"""
Video playback controller using python-vlc.
Plays pre-recorded navigation guide videos.
"""
import logging
import os
import time

from config import VIDEO_DIR, MAX_VIDEO_FILE_SIZE_MB

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

        file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
        if file_size_mb > MAX_VIDEO_FILE_SIZE_MB:
            logger.error(f"Video file too large: {file_size_mb:.1f}MB > {MAX_VIDEO_FILE_SIZE_MB}MB")
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

    def wait_for_completion(self, timeout: float = 300, poll_interval: float = 0.5) -> bool:
        """
        Block until the current video finishes playing.

        Args:
            timeout: Maximum seconds to wait before giving up.
            poll_interval: Seconds between playback status checks.

        Returns:
            True if playback completed normally, False if timed out.
        """
        if self.is_mock:
            return True
        deadline = time.time() + timeout
        while self.is_playing():
            if time.time() >= deadline:
                logger.warning("Video playback timed out")
                self.stop()
                return False
            time.sleep(poll_interval)
        return True

    def close(self):
        """Release VLC resources. Each step is wrapped individually so one failure
        does not prevent cleanup of subsequent resources."""
        try:
            if self._player:
                self._player.stop()
        except Exception as e:
            logger.error(f"Error stopping player: {e}")
        try:
            if self._player:
                self._player.release()
        except Exception as e:
            logger.error(f"Error releasing player: {e}")
        try:
            if self._instance:
                self._instance.release()
        except Exception as e:
            logger.error(f"Error releasing VLC instance: {e}")
