"""
config.py
Centralized loading of environment variables for the content pipeline.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    mixlr_target_url: str
    groq_api_key: str
    openrouter_api_key: str

    # OpenRouter model to use (free / low-cost)
    openrouter_model: str = "google/gemini-pro"
    openrouter_api_base: str = "https://openrouter.ai/api/v1"
    assets_dir: str = "assets"
    output_dir: str = "output"
    background_image: str = "assets/background.jpg"
    output_audio: str = "output/broadcast.mp3"
    output_transcript: str = "output/transcript.txt"
    output_social_copy: str = "output/social_copy.txt"
    output_video: str = "output/final_video.mp4"

    # Groq API (whisper-large-v3 transcription)
    groq_api_base: str = "https://api.groq.com/openai/v1"
    groq_whisper_model: str = "whisper-large-v3"


def load_config() -> Config:
    """Load and validate all required environment variables."""
    required = {
        "MIXLR_TARGET_URL": os.getenv("MIXLR_TARGET_URL"),
        "GROQ_API_KEY": os.getenv("GROQ_API_KEY"),
        "OPENROUTER_API_KEY": os.getenv("OPENROUTER_API_KEY"),
    }

    missing = [k for k, v in required.items() if not v]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    return Config(
        mixlr_target_url=required["MIXLR_TARGET_URL"],
        groq_api_key=required["GROQ_API_KEY"],
        openrouter_api_key=required["OPENROUTER_API_KEY"],
        openrouter_model=os.getenv("OPENROUTER_MODEL", "google/gemini-pro"),
    )
