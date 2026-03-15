import logging
from typing import Any

logger = logging.getLogger(__name__)


class OpenAIService:
    # TODO: Implement real OpenAI integration
    # - Chat completions for natural language processing
    # - Whisper API for audio transcription
    # - Function calling for structured command extraction
    # - Token usage tracking

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def chat_completion(self, messages: list[dict[str, str]]) -> str:
        logger.info("STUB: chat_completion(messages=%d)", len(messages))
        return "This is a stub response. OpenAI integration not implemented yet."

    async def transcribe_audio(self, audio_data: bytes) -> str:
        logger.info("STUB: transcribe_audio(size=%d bytes)", len(audio_data))
        return "Transcription not implemented yet."
