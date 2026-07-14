# Azure Real-Time Voice Conversational AI System 🎙️🤖

**A low-latency, full-duplex voice assistant on Microsoft Azure: speech in → understanding → LLM response → speech out, streamed in real time for natural back-and-forth conversation.**

![Azure](https://img.shields.io/badge/Azure-Speech%20%7C%20OpenAI-0078D4?logo=microsoftazure&logoColor=white) ![Type](https://img.shields.io/badge/Type-Real--time%20Voice%20AI-purple) ![Status](https://img.shields.io/badge/Architecture-Production--style-green)

---


## 🧭 What it does
The system holds a **spoken conversation** with a user in real time:
1. **Listen** — captures microphone audio and streams it to speech recognition.
2. **Transcribe** — converts speech to text continuously (interim + final results) so the assistant can respond the moment the user stops talking.
3. **Reason** — sends the transcript (plus conversation history) to a large language model to generate a context-aware reply.
4. **Speak** — synthesizes the reply to natural speech and streams it back, enabling barge-in / low-latency turn-taking.

## 🏗️ Architecture

```
🎤 Mic / client  ──audio stream──►  Azure Speech-to-Text (streaming recognition)
                                            │ transcript (interim + final)
                                            ▼
                                   Conversation orchestrator  ──►  Azure OpenAI (LLM)  ‹confirm model›
                                            │ assistant text                     │ (system prompt + history + RAG ‹if used›)
                                            ▼                                     │
                                   Azure Text-to-Speech (neural voice)  ◄─────────┘
                                            │ synthesized audio stream
                                            ▼
                                        🔊 client playback
```

**Core Azure services**
- **Azure AI Speech** — streaming Speech-to-Text and neural Text-to-Speech (SSML for prosody/voice control).
- **Azure OpenAI Service** — the conversational LLM (`‹confirm model, e.g. gpt-4o / gpt-4o-mini›`) for response generation.
- **Orchestration / hosting** — `‹confirm: Python service, FastAPI/Flask, WebSocket, Azure App Service / Functions / Container Apps›`.

## ⚙️ Production-style design considerations
- **Latency budget:** streaming STT + token-streaming from the LLM + chunked TTS to minimize time-to-first-audio (target sub-second perceived response).
- **Turn-taking & barge-in:** endpointing on STT finals; allow the user to interrupt playback.
- **State & context:** rolling conversation history with a token budget; optional retrieval (RAG) for grounded answers `‹if implemented›`.
- **Resilience:** retries/back-off on service calls, graceful degradation if a service is unavailable.
- **Security:** secrets (Speech key, Azure OpenAI key/endpoint) via environment variables / Azure Key Vault — **never committed**. Use a `.env.example` template.
- **Observability:** log latency per stage (STT, LLM, TTS) to find bottlenecks.

## 🔐 Configuration (example)
```bash
# .env.example — copy to .env and fill in (do NOT commit real keys)
AZURE_SPEECH_KEY=...
AZURE_SPEECH_REGION=...
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_KEY=...
AZURE_OPENAI_DEPLOYMENT=...   # e.g. gpt-4o
```

## ▶️ Run (summary — reconcile with repo)
```bash
pip install -r requirements.txt      # ‹confirm›
cp .env.example .env                 # add your Azure credentials
python app.py                        # ‹confirm entrypoint›  -> speak to the assistant
```

## 🛠️ Tech stack
`Azure AI Speech (STT/TTS)` · `Azure OpenAI` · `Python` · `WebSocket / streaming` · `‹FastAPI/Flask›` · `SSML`

## 🚀 Possible extensions
- Voice-activity detection for cleaner endpointing; multilingual STT/TTS.
- RAG over a knowledge base for grounded, domain-specific answers.
- Containerize + deploy to Azure Container Apps with autoscaling; add telemetry dashboards.

---
*Real-time voice AI on Azure. Portfolio-facing overview of this system; implementation details marked `‹confirm›` should be reconciled with the code in this repository.*
