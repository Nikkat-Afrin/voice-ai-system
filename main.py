import asyncio
import base64
import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

import azure.cognitiveservices.speech as speechsdk
from azure.cognitiveservices.speech import SpeechConfig, SpeechSynthesizer, SpeechRecognizer, ResultReason
from azure.cognitiveservices.speech.audio import AudioConfig, PushAudioInputStream, AudioStreamFormat
from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

from demo import demo_reply, demo_tts
from metrics import pipeline_metrics
from session_store import SessionStore

# Load environment variables from .env (no-op if the file doesn't exist)
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "eastus")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002")
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX", "rag-index")

# Offline demo mode: run the whole app locally with no Azure account
DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"

# Fail fast with a clear message if required configuration is missing
_REQUIRED_ENV = {
    "AZURE_SPEECH_KEY": AZURE_SPEECH_KEY,
    "AZURE_OPENAI_ENDPOINT": AZURE_OPENAI_ENDPOINT,
    "AZURE_OPENAI_KEY": AZURE_OPENAI_KEY,
    "AZURE_SEARCH_ENDPOINT": AZURE_SEARCH_ENDPOINT,
    "AZURE_SEARCH_KEY": AZURE_SEARCH_KEY,
}
_missing = [name for name, value in _REQUIRED_ENV.items() if not value]
if _missing and not DEMO_MODE:
    raise RuntimeError(
        f"Missing required environment variables: {', '.join(_missing)}. "
        "Copy .env.example to .env and fill in your Azure credentials, "
        "or run with DEMO_MODE=1 for a fully local demo."
    )

if DEMO_MODE:
    logger.info("DEMO_MODE=1 - running fully locally, no Azure calls")
    # Harmless local placeholders so client construction below succeeds
    AZURE_SPEECH_KEY = AZURE_SPEECH_KEY or "demo"
    AZURE_OPENAI_ENDPOINT = AZURE_OPENAI_ENDPOINT or "https://demo.local"
    AZURE_OPENAI_KEY = AZURE_OPENAI_KEY or "demo"
    AZURE_SEARCH_ENDPOINT = AZURE_SEARCH_ENDPOINT or "https://demo.local"
    AZURE_SEARCH_KEY = AZURE_SEARCH_KEY or "demo"

# Initialize Azure clients
try:
    # Azure OpenAI client
    openai_client = AzureOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_KEY,
        api_version="2024-12-01-preview"
    )

    # Azure AI Search client
    search_client = SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=AZURE_SEARCH_INDEX,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY)
    )

    # Azure Speech Services
    speech_config = SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION)
    speech_config.speech_synthesis_voice_name = "en-US-AriaNeural"
    speech_config.speech_recognition_language = "en-US"

except Exception as e:
    logger.error(f"Failed to initialize Azure services: {e}")
    raise

# FastAPI app
app = FastAPI(
    title="Real-Time Voice AI",
    description="Azure-based real-time voice conversational AI with WebSocket support",
    version="1.0.0"
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data models
class TranscribeRequest(BaseModel):
    audio_data: str  # Base64 encoded audio
    format: str = "pcm"
    sample_rate: int = 16000

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class SpeakRequest(BaseModel):
    text: str
    voice: str = "en-US-AriaNeural"

class ConverseRequest(BaseModel):
    audio_data: str
    session_id: Optional[str] = None

# Session management
class ConversationSession:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.history: List[Dict] = []
        self.created_at = datetime.now()

    def add_message(self, role: str, content: str):
        self.history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })

    def get_context(self) -> str:
        return "\n".join([f"{msg['role']}: {msg['content']}" for msg in self.history[-10:]])

# Bounded session storage with TTL eviction (swap for Redis when scaling out).
# Sessions idle for an hour are expired lazily; at most 1000 live sessions.
SESSION_TTL_SECONDS = float(os.getenv("SESSION_TTL_SECONDS", "3600"))
SESSION_MAX_COUNT = int(os.getenv("SESSION_MAX_COUNT", "1000"))
sessions = SessionStore(ttl_seconds=SESSION_TTL_SECONDS, max_sessions=SESSION_MAX_COUNT)

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"WebSocket connected: {session_id}")

    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            logger.info(f"WebSocket disconnected: {session_id}")

    async def send_message(self, session_id: str, message: dict):
        if session_id in self.active_connections:
            await self.active_connections[session_id].send_text(json.dumps(message))

manager = ConnectionManager()

# Audio processing utilities
class AudioProcessor:
    @staticmethod
    def base64_to_pcm(audio_data: str) -> bytes:
        """Convert base64 audio to PCM bytes"""
        return base64.b64decode(audio_data)

    @staticmethod
    def pcm_to_base64(pcm_data: bytes) -> str:
        """Convert PCM bytes to base64"""
        return base64.b64encode(pcm_data).decode('utf-8')

# RAG implementation
class RAGProcessor:
    def __init__(self, search_client: SearchClient, openai_client: AzureOpenAI):
        self.search_client = search_client
        self.openai_client = openai_client

    async def retrieve_context(self, query: str, top_k: int = 3) -> List[Dict]:
        """Retrieve relevant context from Azure AI Search"""
        try:
            # Generate query embedding (run sync SDK call off the event loop)
            embedding_response = await asyncio.to_thread(
                self.openai_client.embeddings.create,
                model=AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
                input=query
            )
            query_vector = embedding_response.data[0].embedding

            # Perform hybrid search
            vector_query = VectorizedQuery(
                vector=query_vector,
                k_nearest_neighbors=top_k,
                fields="content_vector"
            )

            results = await asyncio.to_thread(
                lambda: list(self.search_client.search(
                    search_text=query,
                    vector_queries=[vector_query],
                    select=["content", "title", "source"],
                    top=top_k
                ))
            )

            return [
                {
                    "content": result["content"],
                    "title": result.get("title", ""),
                    "source": result.get("source", ""),
                    "score": result.get("@search.score", 0)
                }
                for result in results
            ]
        except Exception as e:
            logger.error(f"RAG retrieval error: {e}")
            return []

    async def generate_response(self, query: str, context: List[Dict], conversation_history: str) -> str:
        """Generate response using RAG context"""
        try:
            # Format context
            context_text = "\n".join([
                f"Source: {item['title']}\nContent: {item['content']}"
                for item in context
            ])

            # Create system prompt
            system_prompt = f"""You are a helpful AI assistant with access to relevant documents.
            Use the provided context to answer questions accurately and cite sources when possible.

            Context:
            {context_text}

            Recent conversation:
            {conversation_history}

            Provide helpful, accurate responses based on the context. If the context doesn't contain
            relevant information, say so clearly."""

            # Generate response (run sync SDK call off the event loop)
            response = await asyncio.to_thread(
                self.openai_client.chat.completions.create,
                model=AZURE_OPENAI_DEPLOYMENT,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                max_tokens=1000,
                temperature=0.7
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"Response generation error: {e}")
            return "I apologize, but I'm having trouble generating a response right now."

rag_processor = RAGProcessor(search_client, openai_client)

# REST API Endpoints
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat(),
            "mode": "demo" if DEMO_MODE else "live"}

@app.get("/metrics")
async def get_metrics():
    """Latency percentiles (p50/p95/p99) per pipeline stage plus session stats.

    Stages: stt, rag_retrieval, llm, tts, and the end-to-end converse pipeline.
    """
    summary = pipeline_metrics.summary()
    summary["sessions"] = sessions.stats()
    return summary

@app.post("/transcribe")
async def transcribe_audio(request: TranscribeRequest):
    """Convert audio to text using Azure Speech STT"""
    try:
        start_time = datetime.now()

        if DEMO_MODE:
            return {
                "transcription": "",
                "reason": "DemoMode",
                "processing_time_seconds": 0.0,
                "note": "Cloud STT is disabled in DEMO_MODE - use the text box in the demo UI."
            }

        # Convert base64 to PCM
        audio_data = AudioProcessor.base64_to_pcm(request.audio_data)

        # Feed the uploaded audio to the recognizer via a push stream
        # (16 kHz, 16-bit, mono PCM)
        stream_format = AudioStreamFormat(
            samples_per_second=request.sample_rate,
            bits_per_sample=16,
            channels=1
        )
        push_stream = PushAudioInputStream(stream_format=stream_format)
        push_stream.write(audio_data)
        push_stream.close()

        audio_config = AudioConfig(stream=push_stream)

        # Create recognizer
        recognizer = SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config
        )

        # Perform recognition off the event loop (recognize_once is blocking)
        result = await asyncio.to_thread(recognizer.recognize_once)

        processing_time = (datetime.now() - start_time).total_seconds()

        if result.reason == ResultReason.RecognizedSpeech:
            transcription = result.text
        elif result.reason == ResultReason.NoMatch:
            transcription = ""
        else:  # Canceled or other failure
            details = getattr(result, "cancellation_details", None)
            pipeline_metrics.record_error("stt")
            raise HTTPException(
                status_code=500,
                detail=f"Speech recognition failed: {details.reason if details else result.reason}"
            )

        pipeline_metrics.record("stt", processing_time)

        return {
            "transcription": transcription,
            "reason": result.reason.name,
            "processing_time_seconds": processing_time
        }

    except HTTPException:
        raise
    except Exception as e:
        pipeline_metrics.record_error("stt")
        logger.error(f"Transcription error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
async def chat(request: ChatRequest):
    """Text-based chat with RAG context"""
    try:
        session_id = request.session_id or str(uuid.uuid4())

        # Get or create session
        if session_id not in sessions:
            sessions[session_id] = ConversationSession(session_id)

        session = sessions[session_id]

        if DEMO_MODE:
            context = []
            with pipeline_metrics.track("llm"):
                response = demo_reply(request.message, session.get_context())
        else:
            # Retrieve RAG context
            with pipeline_metrics.track("rag_retrieval"):
                context = await rag_processor.retrieve_context(request.message)

            # Generate response
            with pipeline_metrics.track("llm"):
                response = await rag_processor.generate_response(
                    request.message,
                    context,
                    session.get_context()
                )

        # Update session
        session.add_message("user", request.message)
        session.add_message("assistant", response)

        return {
            "response": response,
            "session_id": session_id,
            "context_sources": [item["source"] for item in context]
        }

    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/speak")
async def speak_text(request: SpeakRequest):
    """Convert text to speech using Azure Speech TTS"""
    try:
        start_time = datetime.now()

        if DEMO_MODE:
            audio = await asyncio.to_thread(demo_tts, request.text)
            processing_time = (datetime.now() - start_time).total_seconds()
            pipeline_metrics.record("tts", processing_time)
            return {
                "audio_data": AudioProcessor.pcm_to_base64(audio),
                "processing_time_seconds": processing_time,
                "voice": "piper-local (demo)"
            }

        # Per-request config so concurrent requests can't overwrite each
        # other's voice (the global speech_config must not be mutated here)
        tts_config = SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION)
        tts_config.speech_synthesis_voice_name = request.voice

        # Create synthesizer
        synthesizer = SpeechSynthesizer(
            speech_config=tts_config,
            audio_config=None
        )

        # Synthesize speech off the event loop (.get() is blocking)
        result = await asyncio.to_thread(
            lambda: synthesizer.speak_text_async(request.text).get()
        )

        processing_time = (datetime.now() - start_time).total_seconds()

        if result.reason == ResultReason.SynthesizingAudioCompleted:
            pipeline_metrics.record("tts", processing_time)
            audio_base64 = AudioProcessor.pcm_to_base64(result.audio_data)
            return {
                "audio_data": audio_base64,
                "processing_time_seconds": processing_time,
                "voice": request.voice
            }
        else:
            details = getattr(result, "cancellation_details", None)
            pipeline_metrics.record_error("tts")
            raise HTTPException(
                status_code=500,
                detail=f"Speech synthesis failed: {details.error_details if details else result.reason}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Speech synthesis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/converse")
async def converse(request: ConverseRequest):
    """End-to-end voice conversation pipeline"""
    try:
        pipeline_start = datetime.now()
        session_id = request.session_id or str(uuid.uuid4())

        # Step 1: Speech to Text
        transcribe_req = TranscribeRequest(audio_data=request.audio_data)
        transcription_result = await transcribe_audio(transcribe_req)
        stt_done = datetime.now()

        # Step 2: Process with RAG
        chat_req = ChatRequest(
            message=transcription_result["transcription"],
            session_id=session_id
        )
        chat_result = await chat(chat_req)
        chat_done = datetime.now()

        # Step 3: Text to Speech
        speak_req = SpeakRequest(text=chat_result["response"])
        speech_result = await speak_text(speak_req)
        tts_done = datetime.now()

        total_seconds = (tts_done - pipeline_start).total_seconds()
        pipeline_metrics.record("converse", total_seconds)

        return {
            "transcription": transcription_result["transcription"],
            "response": chat_result["response"],
            "audio_data": speech_result["audio_data"],
            "session_id": session_id,
            "context_sources": chat_result["context_sources"],
            # Per-stage latency breakdown so clients (and load tests) can see
            # exactly where the round-trip budget goes.
            "latency_seconds": {
                "stt": round((stt_done - pipeline_start).total_seconds(), 4),
                "chat": round((chat_done - stt_done).total_seconds(), 4),
                "tts": round((tts_done - chat_done).total_seconds(), 4),
                "total": round(total_seconds, 4),
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Conversation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/reset")
async def reset_session(session_id: str):
    """Clear conversation memory"""
    if session_id in sessions:
        del sessions[session_id]
    return {"message": "Session reset successfully"}

@app.post("/upload_rag_docs")
async def upload_rag_documents(files: List[UploadFile] = File(...)):
    """Upload documents for RAG indexing"""
    try:
        processed_files = []

        for file in files:
            content = await file.read()

            # Process document (simplified - in production, use Azure AI Search indexer)
            document = {
                "id": str(uuid.uuid4()),
                "title": file.filename,
                "content": content.decode('utf-8'),
                "source": file.filename,
                "upload_date": datetime.now().isoformat()
            }

            # Generate embedding
            embedding_response = await asyncio.to_thread(
                openai_client.embeddings.create,
                model=AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
                input=document["content"]
            )
            document["content_vector"] = embedding_response.data[0].embedding

            # Upload to search index
            await asyncio.to_thread(search_client.upload_documents, [document])
            processed_files.append(file.filename)

        return {
            "message": f"Successfully uploaded {len(processed_files)} documents",
            "files": processed_files
        }

    except Exception as e:
        logger.error(f"Document upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# WebSocket endpoint for real-time voice conversation
@app.websocket("/ws/voice/{session_id}")
async def websocket_voice_endpoint(websocket: WebSocket, session_id: str):
    """Real-time voice conversation WebSocket"""
    await manager.connect(websocket, session_id)

    # Initialize session
    if session_id not in sessions:
        sessions[session_id] = ConversationSession(session_id)

    try:
        # Send conversation initiation metadata
        await manager.send_message(session_id, {
            "type": "conversation_initiation_metadata",
            "session_id": session_id,
            "supported_formats": ["pcm"],
            "sample_rate": 16000,
            "channels": 1
        })

        while True:
            # Receive WebSocket message
            message = await websocket.receive_text()
            data = json.loads(message)

            if data["type"] == "audio_chunk":
                # Process audio chunk
                audio_data = data["data"]

                # Transcribe audio
                transcription = await transcribe_audio(
                    TranscribeRequest(audio_data=audio_data)
                )

                if transcription["transcription"].strip():
                    # Send transcription event
                    await manager.send_message(session_id, {
                        "type": "transcription",
                        "text": transcription["transcription"],
                        "reason": transcription["reason"]
                    })

                    # Generate response with RAG
                    chat_response = await chat(ChatRequest(
                        message=transcription["transcription"],
                        session_id=session_id
                    ))

                    # Convert response to speech
                    speech_response = await speak_text(SpeakRequest(
                        text=chat_response["response"]
                    ))

                    # Send audio response
                    await manager.send_message(session_id, {
                        "type": "audio_response",
                        "audio_data": speech_response["audio_data"],
                        "text": chat_response["response"],
                        "sources": chat_response["context_sources"]
                    })

            elif data["type"] == "interrupt":
                # Handle interruption
                await manager.send_message(session_id, {
                    "type": "interruption_acknowledged",
                    "timestamp": datetime.now().isoformat()
                })

    except WebSocketDisconnect:
        manager.disconnect(session_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await manager.send_message(session_id, {
            "type": "error",
            "message": str(e)
        })

# Serve the test frontend (single source of truth: frontend/index.html)
@app.get("/")
async def get_frontend():
    frontend_path = os.path.join(os.path.dirname(__file__), "frontend", "index.html")
    try:
        with open(frontend_path, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        return HTMLResponse("<h1>Voice AI</h1><p>frontend/index.html not found.</p>", status_code=404)

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
