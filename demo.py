"""Offline demo mode: no Azure account needed.

Set ``DEMO_MODE=1`` and the app runs fully locally:

  * chat        - a small rule-based assistant that answers questions about
                  this project (architecture, latency, RAG, tech stack), so
                  the demo conversation is actually informative
  * speech out  - neural TTS via `piper-tts <https://github.com/OHF-Voice/piper1-gpl>`_
                  if a voice model is available (see below), otherwise a clean
                  spoken-cadence placeholder tone so the audio path still works
  * speech in   - cloud STT is disabled offline; the demo UI uses the text box

To enable real neural TTS in the demo::

    pip install piper-tts
    python -m piper.download_voices en_US-lessac-low --data-dir voices
    export PIPER_VOICE=voices/en_US-lessac-low.onnx

No cloud calls are made anywhere in demo mode.
"""

from __future__ import annotations

import io
import math
import os
import re
import struct
import wave

_PIPER_VOICE = os.getenv("PIPER_VOICE", "")

_FAQ = [
    (r"\b(hi|hello|hey)\b",
     "Hello! I am the demo assistant for this voice AI system. Ask me about the "
     "architecture, the latency budget, RAG, or the tech stack."),
    (r"\b(architecture|how.*work|pipeline)\b",
     "The pipeline has four stages: speech to text, retrieval over your documents, "
     "a large language model that writes the reply, and neural text to speech. "
     "In production each stage is an Azure service; in this demo everything runs locally."),
    (r"\b(latency|fast|slow|speed)\b",
     "Latency is tracked per stage with rolling percentiles. The metrics endpoint "
     "reports p fifty, p ninety five and p ninety nine for speech recognition, "
     "retrieval, the language model and speech synthesis, so you can see exactly "
     "where the round trip budget goes."),
    (r"\b(rag|retrieval|document|search)\b",
     "Retrieval augmented generation grounds every answer in your uploaded documents. "
     "The production build uses hybrid keyword plus vector search in Azure AI Search "
     "with embeddings from text embedding ada."),
    (r"\b(stack|tech|built|framework)\b",
     "The backend is FastAPI with WebSockets, containerized with Docker and deployed "
     "to Azure Container Apps through Bicep infrastructure as code. Tests run in "
     "GitHub Actions on every push."),
    (r"\b(metrics|monitor|observab)\b",
     "Every conversation records stage latencies into rolling windows. Hit the "
     "slash metrics endpoint to see percentiles and live session counts."),
    (r"\b(demo|offline|azure|cost\w*|price|money|free)\b",
     "You are in demo mode right now: no Azure account, no cloud calls, no cost. "
     "The voice you hear is Piper, an open neural text to speech model running locally."),
    (r"\b(who|author|made)\b",
     "This system was built by Nikkat Afrin as a production style real time "
     "voice assistant on Azure."),
    (r"\b(bye|goodbye|thanks|thank you)\b",
     "You are welcome! Check the readme for the full architecture and the live "
     "metrics endpoint. Goodbye!"),
]

_FALLBACK = ("Good question. In the full build that answer would come from GPT four o "
             "grounded in your documents. In this offline demo I know about the "
             "architecture, latency, RAG, metrics, and the tech stack - try one of those.")


def demo_reply(message: str, history_text: str = "") -> str:
    msg = message.lower()
    for pattern, reply in _FAQ:
        if re.search(pattern, msg):
            return reply
    return _FALLBACK


def _placeholder_wav(text: str, rate: int = 16000) -> bytes:
    """Speech-cadence tone so the audio path works without any TTS model."""
    words = max(len(text.split()), 1)
    duration = min(0.28 * words, 6.0)
    n = int(rate * duration)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        frames = bytearray()
        for i in range(n):
            t = i / rate
            syllable = math.sin(2 * math.pi * 3.2 * t) ** 2          # cadence
            f = 165 + 40 * math.sin(2 * math.pi * 0.6 * t)           # pitch drift
            amp = 0.25 * syllable * (1 if i < n - rate * 0.2 else max(0, (n - i) / (rate * 0.2)))
            frames += struct.pack("<h", int(32767 * amp * math.sin(2 * math.pi * f * t)))
        w.writeframes(bytes(frames))
    return buf.getvalue()


def demo_tts(text: str) -> bytes:
    """Return WAV bytes for the reply, using Piper when available."""
    if _PIPER_VOICE and os.path.exists(_PIPER_VOICE):
        try:
            from piper import PiperVoice
            voice = PiperVoice.load(_PIPER_VOICE)
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                voice.synthesize_wav(text, w)
            return buf.getvalue()
        except Exception:
            pass
    return _placeholder_wav(text)
