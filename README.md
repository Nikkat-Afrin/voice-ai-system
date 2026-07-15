# Azure Real-Time Voice Conversational AI System 🎙️🤖

**A low-latency, full-duplex voice assistant on Microsoft Azure: speech in → understanding → LLM response → speech out, streamed in real time for natural back-and-forth conversation.**

[![CI](https://github.com/Nikkat-Afrin/voice-ai-system/actions/workflows/ci.yml/badge.svg)](https://github.com/Nikkat-Afrin/voice-ai-system/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) ![Azure](https://img.shields.io/badge/Azure-Speech%20%7C%20OpenAI%20%7C%20AI%20Search-0078D4?logo=microsoftazure&logoColor=white) ![Python](https://img.shields.io/badge/Python-FastAPI-3776AB?logo=python&logoColor=white) ![Type](https://img.shields.io/badge/Type-Real--time%20Voice%20AI-purple) ![Status](https://img.shields.io/badge/Architecture-Production--style-green)

---

## 🧭 What it does

The system holds a **spoken conversation** with a user in real time:

1. **Listen** - captures microphone audio (PCM 16 kHz mono) and streams it to the backend over WebSocket.
2. **Transcribe** - Azure AI Speech converts speech to text.
3. **Reason** - the transcript, conversation history, and retrieved documents (RAG via Azure AI Search) are sent to Azure OpenAI (GPT-4o) to generate a context-aware, grounded reply.
4. **Speak** - Azure neural Text-to-Speech synthesizes the reply and streams it back for playback.

## 🏗️ Architecture

<img width="1600" height="522" alt="image" src="https://github.com/user-attachments/assets/a9b72fcb-7ece-4b0a-b85b-88411197f89a" />

```
🎤 Mic / client ──audio (WebSocket)──► FastAPI backend
                                          │
                                          ├─► Azure AI Speech (STT)
                                          │        │ transcript
                                          ▼        ▼
                                   Conversation orchestrator ──► Azure OpenAI (GPT-4o)
                                          │                          ▲
                                          │            RAG context   │
                                          │       Azure AI Search ───┘
                                          ▼
                                   Azure AI Speech (neural TTS)
                                          │ synthesized audio
                                          ▼
                                      🔊 client playback
```

**Core Azure services**
- **Azure AI Speech** - Speech-to-Text and neural Text-to-Speech (en-US-AriaNeural by default).
- **Azure OpenAI Service** - GPT-4o for response generation, text-embedding-ada-002 for embeddings.
- **Azure AI Search** - hybrid (keyword + vector) retrieval over uploaded documents.
- **Hosting** - FastAPI + WebSocket, containerized (Docker) and deployed to Azure Container Apps via Bicep IaC and GitHub Actions CI/CD.

## ▶️ Quick Start

### Prerequisites

- Python 3.10+
- An Azure subscription with Speech, OpenAI, and AI Search resources
- Azure CLI and Docker (for deployment only)

### Run locally

```bash
git clone https://github.com/Nikkat-Afrin/azure-voice-conversational-ai.git
cd azure-voice-conversational-ai
pip install -r requirements.txt

cp .env.example .env   # fill in your Azure keys/endpoints (never commit .env)

python main.py         # open http://localhost:8000 and speak to the assistant
```

### Deploy to Azure

```bash
chmod +x deploy.sh
./deploy.sh
```

## 📡 API Endpoints

### REST

- `POST /transcribe` - audio (base64 PCM) → text
- `POST /chat` - text conversation with RAG context
- `POST /speak` - text → audio (base64 WAV)
- `POST /converse` - end-to-end voice pipeline (STT → RAG+LLM → TTS)
- `POST /reset` - clear conversation memory
- `POST /upload_rag_docs` - upload documents for RAG indexing
- `GET /health` - health check
- `GET /metrics` - per-stage latency percentiles (p50/p95/p99 for STT, RAG retrieval, LLM, TTS, end-to-end) + live session stats

### WebSocket

- `WS /ws/voice/{session_id}` - real-time voice conversation

**Client → server**

```json
{ "type": "audio_chunk", "data": "<base64 PCM 16 kHz 16-bit mono>" }
```

**Server → client**

```json
{ "type": "audio_response", "audio_data": "<base64 WAV>", "text": "reply", "sources": ["doc1"] }
```

## 🔐 Configuration

```bash
# .env.example - copy to .env and fill in (do NOT commit real keys)
AZURE_SPEECH_KEY=...
AZURE_SPEECH_REGION=eastus
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_KEY=...
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-ada-002
AZURE_SEARCH_ENDPOINT=...
AZURE_SEARCH_KEY=...
AZURE_SEARCH_INDEX=rag-index
```

**Audio format:** PCM, 16-bit, mono, 16 kHz, base64-encoded for transport.

## ⚙️ Production-style design considerations

- **Non-blocking pipeline:** all Azure SDK calls (STT, TTS, OpenAI, Search) run off the event loop (`asyncio.to_thread`) so concurrent WebSocket sessions don't stall each other.
- **State & context:** rolling conversation history per session with RAG grounding for domain answers.
- **Resilience:** startup fails fast with a clear message if configuration is missing; recognition and synthesis results are validated (NoMatch/Canceled handled explicitly).
- **Security:** secrets via environment variables / Azure Key Vault - never committed; `.env.example` template provided.
- **Observability:** built-in `/metrics` endpoint with rolling-window latency percentiles (p50/p95/p99) per pipeline stage - STT, RAG retrieval, LLM, TTS, and the end-to-end round trip; `/converse` responses include a per-stage latency breakdown so clients and load tests can see exactly where the budget goes.
- **Bounded memory:** conversation sessions live in a TTL + LRU-capped store (`session_store.py`), so a long-running server can't leak history; limits are tunable via `SESSION_TTL_SECONDS` / `SESSION_MAX_COUNT`.
- **Scaling:** Azure Container Apps auto-scaling (1-10 instances) defined in Bicep.

## 🧪 Testing

```bash
pytest tests/                 # unit tests
pytest tests/integration/     # integration tests
pytest --cov=main tests/      # coverage
python test_system.py         # live system test against a running server
```

## 📁 Project Structure

```
azure-voice-conversational-ai/
├── main.py                   # FastAPI application (STT, RAG, TTS, WebSocket)
├── frontend/index.html       # Browser test client (PCM capture + playback)
├── requirements.txt          # Python dependencies
├── .env.example              # Environment template
├── Dockerfile                # Container build
├── deploy.sh                 # Azure deployment script
├── bicep/main.bicep          # Infrastructure as Code
├── .github/workflows/        # CI/CD pipeline
├── tests/                    # Unit + integration tests
└── scripts/                  # Setup and post-deploy scripts
```

## 🚀 Possible extensions

- Streaming (continuous) recognition with interim results and barge-in during pl