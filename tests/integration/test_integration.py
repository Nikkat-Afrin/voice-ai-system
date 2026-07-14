"""Integration tests for the voice pipeline.

All Azure calls are mocked; what these tests exercise is the wiring between
endpoints: STT -> RAG -> LLM -> TTS, session handling, and error paths.
"""

import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from azure.cognitiveservices.speech import ResultReason
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


@pytest.fixture
def mock_azure_services():
    """Mock the module-level Azure clients."""
    with patch('main.speech_config'), \
         patch('main.openai_client'), \
         patch('main.search_client'):
        yield


def _recognized(text: str) -> Mock:
    result = Mock()
    result.text = text
    result.reason = ResultReason.RecognizedSpeech  # real enum: == comparisons work
    return result


def _synthesized(audio: bytes) -> Mock:
    result = Mock()
    result.reason = ResultReason.SynthesizingAudioCompleted
    result.audio_data = audio
    return result


class TestVoiceAIIntegration:
    """Integration tests for the complete voice AI system."""

    def test_complete_voice_conversation_flow(self, mock_azure_services):
        """STT -> RAG -> LLM -> TTS through /converse, with latency breakdown."""
        audio_data = base64.b64encode(b"\x00\x00" * 1600).decode('utf-8')

        with patch('main.SpeechRecognizer') as mock_recognizer, \
             patch('main.SpeechSynthesizer') as mock_synthesizer, \
             patch('main.rag_processor.retrieve_context', new_callable=AsyncMock) as mock_retrieve, \
             patch('main.rag_processor.generate_response', new_callable=AsyncMock) as mock_generate:

            mock_recognizer.return_value.recognize_once.return_value = \
                _recognized("What is the weather like?")
            mock_synthesizer.return_value.speak_text_async.return_value.get.return_value = \
                _synthesized(b"synthesized audio data")
            mock_retrieve.return_value = [{
                "content": "The weather is sunny today.",
                "title": "Weather Report",
                "source": "weather_service",
                "score": 0.95,
            }]
            mock_generate.return_value = "The weather is sunny today with clear skies."

            response = client.post("/converse", json={
                "audio_data": audio_data,
                "session_id": "test_integration_session",
            })

            assert response.status_code == 200
            data = response.json()
            assert data["transcription"] == "What is the weather like?"
            assert data["response"] == "The weather is sunny today with clear skies."
            assert "audio_data" in data
            assert data["session_id"] == "test_integration_session"
            assert data["context_sources"] == ["weather_service"]

            # New: per-stage latency breakdown
            latency = data["latency_seconds"]
            assert set(latency) == {"stt", "chat", "tts", "total"}
            assert latency["total"] >= 0

    def test_converse_updates_pipeline_metrics(self, mock_azure_services):
        """A successful /converse round trip should show up in /metrics."""
        audio_data = base64.b64encode(b"\x00\x00" * 1600).decode('utf-8')

        with patch('main.SpeechRecognizer') as mock_recognizer, \
             patch('main.SpeechSynthesizer') as mock_synthesizer, \
             patch('main.rag_processor.retrieve_context', new_callable=AsyncMock, return_value=[]), \
             patch('main.rag_processor.generate_response', new_callable=AsyncMock, return_value="Hi."):

            mock_recognizer.return_value.recognize_once.return_value = _recognized("Hello")
            mock_synthesizer.return_value.speak_text_async.return_value.get.return_value = \
                _synthesized(b"audio")

            before = client.get("/metrics").json()["stages"]["converse"]["requests"]
            assert client.post("/converse", json={"audio_data": audio_data}).status_code == 200
            after = client.get("/metrics").json()["stages"]["converse"]["requests"]
            assert after == before + 1

    def test_session_management(self, mock_azure_services):
        """Session creation, reuse, and reset."""
        session_id = "test_session_management"

        with patch('main.rag_processor.retrieve_context', new_callable=AsyncMock, return_value=[]), \
             patch('main.rag_processor.generate_response', new_callable=AsyncMock) as mock_generate:

            mock_generate.return_value = "Hello! How can I help you today?"
            response = client.post("/chat", json={
                "message": "Hello, this is a test message",
                "session_id": session_id,
            })
            assert response.status_code == 200
            assert response.json()["session_id"] == session_id

            # Second turn in the same session: history must reach the LLM prompt
            mock_generate.return_value = "You said 'Hello, this is a test message'"
            response = client.post("/chat", json={
                "message": "What did I just say?",
                "session_id": session_id,
            })
            assert response.status_code == 200
            history_arg = mock_generate.call_args.args[2]
            assert "Hello, this is a test message" in history_arg

        reset_response = client.post(f"/reset?session_id={session_id}")
        assert reset_response.status_code == 200
        assert reset_response.json()["message"] == "Session reset successfully"

    def test_audio_processing(self, mock_azure_services):
        from main import AudioProcessor

        original_data = b"test audio data"
        encoded = AudioProcessor.pcm_to_base64(original_data)
        decoded = AudioProcessor.base64_to_pcm(encoded)
        assert decoded == original_data

    def test_rag_integration(self, mock_azure_services):
        """RAGProcessor against mocked OpenAI-embeddings and Search clients."""
        from main import RAGProcessor

        mock_openai = MagicMock()
        embedding_response = Mock()
        embedding_response.data = [Mock(embedding=[0.1, 0.2, 0.3] * 100)]
        mock_openai.embeddings.create.return_value = embedding_response

        mock_search = MagicMock()
        mock_search.search.return_value = iter([{
            "content": "Machine learning provides automation and pattern recognition.",
            "title": "ML Benefits",
            "source": "ml_guide",
            "@search.score": 0.95,
        }])

        processor = RAGProcessor(mock_search, mock_openai)
        context = asyncio.run(
            processor.retrieve_context("What are the benefits of machine learning?")
        )

        assert len(context) == 1
        assert context[0]["title"] == "ML Benefits"
        assert context[0]["source"] == "ml_guide"
        mock_openai.embeddings.create.assert_called_once()
        mock_search.search.assert_called_once()

    def test_error_handling(self, mock_azure_services):
        """Invalid base64 audio should produce a clean HTTP error, not a hang."""
        response = client.post("/converse", json={
            "audio_data": "invalid_base64_data!@#",
            "session_id": "test_error_session",
        })
        assert response.status_code in [400, 500]

    def test_websocket_endpoint_availability(self):
        from main import app as main_app

        websocket_routes = [
            route for route in main_app.routes
            if hasattr(route, 'endpoint') and 'websocket' in str(route.endpoint).lower()
        ]
        assert len(websocket_routes) > 0
