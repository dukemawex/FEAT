"""
main.py
Entry point for the Multi-Agent Automated Content Pipeline.

Execution order:
  1. Ingestion  – detect & download the latest Mixlr broadcast
  2. Copywriter – transcribe (Groq / whisper-large-v3) + generate social copy
  3. Producer   – render audiogram video with FFmpeg

Outputs are written to the output/ directory; nothing is published to social media.
"""

import logging
import sys
from pathlib import Path

from config import load_config
from agents import ingestion, copywriter, producer

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")


def main() -> int:
    """Run the full content pipeline. Returns 0 on success, 1 on failure."""
    logger.info("=== FEAT Content Pipeline – starting ===")

    # ---------------------------------------------------------------------- #
    # 0. Load configuration                                                    #
    # ---------------------------------------------------------------------- #
    try:
        cfg = load_config()
    except EnvironmentError as exc:
        logger.error("Configuration error: %s", exc)
        return 1

    # Ensure output directory exists
    Path(cfg.output_dir).mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------------- #
    # 1. Ingestion                                                              #
    # ---------------------------------------------------------------------- #
    try:
        audio_path = ingestion.run(cfg)
    except Exception as exc:  # noqa: BLE001
        logger.error("Ingestion agent failed: %s", exc, exc_info=True)
        return 1

    # ---------------------------------------------------------------------- #
    # 2. Copywriter                                                             #
    # ---------------------------------------------------------------------- #
    try:
        copywriter.run(cfg, audio_path)
    except Exception as exc:  # noqa: BLE001
        logger.error("Copywriter agent failed: %s", exc, exc_info=True)
        return 1

    # ---------------------------------------------------------------------- #
    # 3. Producer                                                               #
    # ---------------------------------------------------------------------- #
    try:
        video_path = producer.run(cfg, audio_path)
    except Exception as exc:  # noqa: BLE001
        logger.error("Producer agent failed: %s", exc, exc_info=True)
        return 1

    # ---------------------------------------------------------------------- #
    # Summary                                                                  #
    # ---------------------------------------------------------------------- #
    logger.info("=== Pipeline complete ===")
    logger.info("  Audio      : %s", audio_path)
    logger.info("  Transcript : %s", cfg.output_transcript)
    logger.info("  Social copy: %s", cfg.output_social_copy)
    logger.info("  Video      : %s", video_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
