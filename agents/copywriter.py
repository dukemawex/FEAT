"""
agents/copywriter.py
1. Transcribes the downloaded audio with OpenAI Whisper (whisper-1).
2. Sends the transcript to OpenRouter (google/gemini-pro) to generate:
   - YouTube Title & Description
   - Facebook Post
   - WhatsApp Broadcast Message
3. Saves all outputs to output/social_copy.txt and returns the transcript text.
"""

import logging
import os
import textwrap
from pathlib import Path

import openai
import requests

from config import Config

logger = logging.getLogger(__name__)

# Maximum tokens for the social-copy LLM response
_MAX_TOKENS = 1024

_SYSTEM_PROMPT = textwrap.dedent(
    """\
    You are an expert social media copywriter for a church / ministry broadcast.
    Given a transcript of an audio broadcast, generate optimised copy for three
    platforms. Follow the formatting instructions exactly.
    """
)

_USER_PROMPT_TEMPLATE = textwrap.dedent(
    """\
    Here is the transcript of the latest broadcast:

    ---
    {transcript}
    ---

    Please generate the following, using the EXACT section headers shown:

    ## YouTube Title
    (A compelling, SEO-friendly title, max 100 characters)

    ## YouTube Description
    (3-5 sentences summarising the message, include relevant hashtags)

    ## Facebook Post
    (Engaging post suitable for a Facebook page, 2-4 paragraphs, include emojis
    where appropriate, end with 3-5 relevant hashtags)

    ## WhatsApp Broadcast
    (A formatted WhatsApp message announcing the broadcast. Use *bold* for
    emphasis where Mixlr-style markdown is available. Keep it under 300 words.)
    """
)


class CopywriterError(RuntimeError):
    """Raised when transcription or copy generation fails."""


def _transcribe(audio_path: str, api_key: str) -> str:
    """
    Use OpenAI Whisper (whisper-1) to transcribe the audio file.
    Returns the full transcript text.
    """
    client = openai.OpenAI(api_key=api_key)

    logger.info("Transcribing audio: %s", audio_path)
    with open(audio_path, "rb") as audio_file:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="text",
        )

    # The SDK returns the transcript as a plain string when response_format="text"
    transcript = response if isinstance(response, str) else response.text
    logger.info(
        "Transcription complete. Length: %d characters", len(transcript)
    )
    return transcript


def _generate_copy(transcript: str, cfg: Config) -> str:
    """
    Call OpenRouter to generate social-media copy from the transcript.
    Returns the raw LLM response text.
    """
    headers = {
        "Authorization": f"Bearer {cfg.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/dukemawex/FEAT",
        "X-Title": "FEAT Content Pipeline",
    }

    payload = {
        "model": cfg.openrouter_model,
        "max_tokens": _MAX_TOKENS,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _USER_PROMPT_TEMPLATE.format(transcript=transcript),
            },
        ],
    }

    url = f"{cfg.openrouter_api_base}/chat/completions"
    logger.info("Sending transcript to OpenRouter model: %s", cfg.openrouter_model)

    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    if not resp.ok:
        raise CopywriterError(
            f"OpenRouter API error {resp.status_code}: {resp.text[:500]}"
        )

    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise CopywriterError(
            f"Unexpected OpenRouter response structure: {data}"
        ) from exc

    logger.info("Copy generation complete.")
    return content


def _save_outputs(
    transcript: str,
    social_copy: str,
    transcript_path: str,
    social_copy_path: str,
) -> None:
    """Persist the transcript and generated copy to disk."""
    Path(transcript_path).parent.mkdir(parents=True, exist_ok=True)
    Path(social_copy_path).parent.mkdir(parents=True, exist_ok=True)

    Path(transcript_path).write_text(transcript, encoding="utf-8")
    logger.info("Transcript saved → %s", transcript_path)

    Path(social_copy_path).write_text(social_copy, encoding="utf-8")
    logger.info("Social copy saved → %s", social_copy_path)


def run(cfg: Config, audio_path: str) -> str:
    """
    Main entry point for the copywriter agent.

    Args:
        cfg: Pipeline configuration.
        audio_path: Path to the downloaded audio file.

    Returns:
        The full transcript text (used downstream by the producer agent).
    """
    logger.info("Copywriter agent started.")

    # Step 1 – Transcribe
    transcript = _transcribe(audio_path, cfg.openai_api_key)

    # Step 2 – Generate social copy
    social_copy = _generate_copy(transcript, cfg)

    # Step 3 – Persist
    _save_outputs(transcript, social_copy, cfg.output_transcript, cfg.output_social_copy)

    return transcript
