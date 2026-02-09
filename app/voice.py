"""
Voice pipeline - STT/TTS for phone call scenario
This is roadmap/optional for MVP, as per brief: if only WhatsApp text is done, explicitly say voice is roadmap

STT: Whisper API or Twilio transcription
TTS: OpenAI TTS or ElevenLabs
"""

import logging
from pathlib import Path
from typing import Optional

from .config import OPENAI_API_KEY, OPENAI_MODEL, USE_MOCK_LLM

logger = logging.getLogger(__name__)

# --- STT (Speech to Text) ---

def transcribe_audio_whisper(audio_path: Path) -> str:
    """
    Transcribe audio using OpenAI Whisper API
    """
    if USE_MOCK_LLM:
        logger.info("Mock STT - returning placeholder")
        return "Hello, I would like to book a wellness appointment for tomorrow at 11 AM"
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="en"
            )
        return transcript.text
    
    except Exception as e:
        logger.error(f"Whisper STT failed: {e}")
        return ""

def transcribe_twilio_recording(recording_url: str, twilio_auth: tuple) -> str:
    """
    Transcribe Twilio recording - Twilio can do built-in transcription
    Or download and use Whisper
    """
    # In real implementation, you'd download recording from Twilio URL
    # For demo, return mock
    logger.info(f"Mock transcribing Twilio recording {recording_url}")
    return "I want to book an appointment tomorrow at 11"

# --- TTS (Text to Speech) ---

def synthesize_speech_openai(text: str, output_path: Path, voice: str = "alloy") -> Path:
    """
    Synthesize speech using OpenAI TTS
    """
    if USE_MOCK_LLM:
        logger.info(f"Mock TTS - would synthesize: {text[:50]}...")
        # Create empty file as placeholder
        output_path.write_text(f"[MOCK TTS] {text}")
        return output_path
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text
        )
        
        response.stream_to_file(str(output_path))
        logger.info(f"TTS saved to {output_path}")
        return output_path
    
    except Exception as e:
        logger.error(f"OpenAI TTS failed: {e}")
        return output_path

def synthesize_speech_elevenlabs(text: str, output_path: Path, voice_id: str = "21m00Tcm4TlvDq8ikWAM") -> Path:
    """
    Synthesize using ElevenLabs (optional)
    Requires ELEVENLABS_API_KEY
    """
    import os
    eleven_key = os.getenv("ELEVENLABS_API_KEY")
    if not eleven_key:
        return synthesize_speech_openai(text, output_path)
    
    try:
        import httpx
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {"xi-api-key": eleven_key, "Content-Type": "application/json"}
        payload = {"text": text, "model_id": "eleven_monolingual_v1"}
        
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            output_path.write_bytes(resp.content)
            return output_path
    except Exception as e:
        logger.error(f"ElevenLabs TTS failed: {e}")
        return synthesize_speech_openai(text, output_path)

# --- Voice webhook for Twilio Voice ---

def handle_voice_call(transcribed_text: str, caller_id: str, caller_name: str = "") -> tuple[str, Optional[Path]]:
    """
    Handle voice call: STT text -> agent -> TTS audio
    Returns (response_text, audio_path)
    """
    from .agent import handle_message
    
    # Agent handles transcribed text same as WhatsApp
    result = handle_message(
        user_id=caller_id,
        message=transcribed_text,
        user_name=caller_name,
        client_timezone="Europe/Tallinn"
    )
    
    response_text = result["response"]
    
    # Synthesize response to audio
    output_path = Path(f"/tmp/voice_response_{caller_id}.mp3")
    audio_path = synthesize_speech_openai(response_text, output_path)
    
    return response_text, audio_path

# Roadmap note
ROADMAP_NOTE = """
Voice scenario is currently ROADMAP, not fully tested in production.

MVP is WhatsApp text only (faster and more reliable for portfolio).

Voice would require:
- Twilio Voice webhook to receive calls
- Twilio <Record> or <Gather> to get audio
- Whisper STT to transcribe
- Same agent logic as WhatsApp
- TTS to generate audio response
- Twilio <Play> to play audio back to caller

This is documented as roadmap in README, not shown as ready if not tested.
"""

if __name__ == "__main__":
    print(ROADMAP_NOTE)
    # Test mock STT/TTS
    print("\nTest mock STT/TTS:")
    text, audio = handle_voice_call("I want to book tomorrow at 11", "caller_123", "Anna")
    print(f"Response: {text}")
    print(f"Audio: {audio}")
