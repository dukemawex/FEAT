"""
agents/producer.py
Uses ffmpeg-python to build a dynamic audiogram video:
  - Static background: assets/background.jpg
  - Animated waveform overlay derived from the audio
  - Output: output/final_video.mp4
"""

import logging
import os
from pathlib import Path

import ffmpeg

from config import Config

logger = logging.getLogger(__name__)

# Visual settings
_WAVEFORM_COLOR = "0x00aaff"        # bright blue waveform bars
_WAVEFORM_BG_COLOR = "0x00000080"   # semi-transparent black backing
_VIDEO_SIZE = "1280x720"
_FPS = 25
_WAVEFORM_HEIGHT = 200              # pixels tall
_WAVEFORM_SCALE = "sqrt"            # amplitude scaling: lin | sqrt | cbrt | log


class ProducerError(RuntimeError):
    """Raised when video production fails."""


def run(cfg: Config, audio_path: str) -> str:
    """
    Main entry point for the producer agent.

    Composites a static background image with a dynamic audio waveform and
    muxes the original audio into a final MP4.

    Args:
        cfg: Pipeline configuration.
        audio_path: Path to the downloaded audio file.

    Returns:
        Path to the produced video file.
    """
    logger.info("Producer agent started.")

    background = cfg.background_image
    output_path = cfg.output_video

    if not Path(background).exists():
        raise ProducerError(
            f"Background image not found: {background}. "
            "Place a JPEG at assets/background.jpg before running the pipeline."
        )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    width, height = _VIDEO_SIZE.split("x")
    waveform_y = int(height) - _WAVEFORM_HEIGHT - 20  # 20px bottom margin

    logger.info(
        "Compositing %s + %s → %s", background, audio_path, output_path
    )

    try:
        # ------------------------------------------------------------------ #
        # Input streams                                                        #
        # ------------------------------------------------------------------ #
        bg = ffmpeg.input(
            background,
            loop=1,
            framerate=_FPS,
        )

        audio = ffmpeg.input(audio_path)

        # ------------------------------------------------------------------ #
        # Waveform filter                                                       #
        # The showwaves filter renders an animated waveform as a video stream. #
        # ------------------------------------------------------------------ #
        waveform = (
            audio.audio.filter(
                "showwaves",
                s=f"{width}x{_WAVEFORM_HEIGHT}",
                mode="cline",          # centre-line bars
                rate=_FPS,
                colors=_WAVEFORM_COLOR,
                scale=_WAVEFORM_SCALE,
            )
        )

        # ------------------------------------------------------------------ #
        # Overlay waveform onto background                                     #
        # ------------------------------------------------------------------ #
        composed = ffmpeg.overlay(
            bg.video,
            waveform,
            x=0,
            y=waveform_y,
            shortest=1,
        )

        # ------------------------------------------------------------------ #
        # Output – copy audio, encode video with libx264                      #
        # ------------------------------------------------------------------ #
        (
            ffmpeg
            .output(
                composed,
                audio.audio,
                output_path,
                vcodec="libx264",
                acodec="aac",
                pix_fmt="yuv420p",
                shortest=None,       # end when shortest input ends
                **{"b:a": "192k"},
            )
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        raise ProducerError(f"FFmpeg failed:\n{stderr}") from exc

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    logger.info("Video produced: %s (%.2f MB)", output_path, size_mb)
    return output_path
