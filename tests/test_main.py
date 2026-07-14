import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock, patch
import base64

from azure.cognitiveservices.speech import ResultReason

from main import app

client = TestClient(app)

@pytest.fixture
def mock_azure_services():
    with patch('main.speech_config'), \
         patch('main.openai_client'), \
         patch('main.search_client'):
        yield

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_transcribe_endpoint(mock_azure_services):
    # 0.1s of silence as fake PCM 16-bit mono @ 16kHz
    audio_data = base64.b64encode(b"\x00\x00" * 1600).decode('utf-8')

    request_data = {
        "audio_data": audio_data,
        "format": "pcm",
        "sample_rate": 16000
    }

    with patch('main.SpeechRecognizer') as mock_recognizer:
        mock_result = Mock()
        mock_result.text = "Hello world"
        mock_result.reason = ResultReason.RecognizedSpeech
        mock_recognizer.return_value.recognize_once.return_value = mock_result

        response = client.post("/transcribe", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["transcription"] == "Hello world"
        assert "processing_time_seconds" in data

def test_transcribe_no_match(mock_azure_services):
    audio_data = base64.b64encode(b"\x00\x00" * 1600).decode('utf-8')

    with patch('main.SpeechRecognizer') as mock_recognizer:
        mock_result = Mock()
        mock_result.reason = ResultReason.NoMatch
        mock_recognizer.return_value.recognize_once.return_value = mock_result

        response = client.post("/transcribe", json={"audio_data": audio_data})

        assert response.status_code == 200
        assert response.json()["transcription"] == ""

def test_chat_endpoint(mock_azure_services):
    request_data = {
        "message": "What is the weather like?",
        "session_id": "test_session"
    }

    with patch('main.rag_processor.retrieve_context', new_callable=AsyncMock) as mock_retrieve, \
         patch('main.rag_processor.generate_response', new_callable=AsyncMock) as mock_generate:

        mock_retrieve.return_value = []
        mock_generate.return_value = "I don't have weather information."

        response = client.post("/chat", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert data["session_id"] == "test_session"

def test_speak_endpoint(mock_azure_services):
    request_data = {
        "text": "Hello world",
        "voice": "en-US-AriaNeural"
    }

    with patch('main.SpeechSynthesizer') as mock_synthesizer, \
         patch('main.SpeechConfig'):
        mock_result = Mock()
        mock_result.reason = ResultReason.SynthesizingAudioCompleted
        mock_result.audio_data = b"fake audio data"
        mock_synthesizer.return_value.speak_text_async.return_value.get.return_value = mock_result

        response = client.post("/speak", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert "audio_data" in data
        assert data["voice"] == "en-US-AriaNeural"

def test_converse_endpoint(mock_azure_services):
    audio_data = base64.b64encode(b"\x00\x00" * 1600).decode('utf-8')
    request_data = {
        "audio_data": audio_data,
        "session_id": "test_session"
    }

    with patch('main.transcribe_audio', new_callable=AsyncMock) as mock_transcribe, \
         patch('main.chat', new_callable=AsyncMock) as mock_chat, \
         patch('main.speak_text', new_callable=AsyncMock) as mock_speak:

        mock_transcribe.return_value = {"transcription": "Hello", "reason": "RecognizedSpeech"}
        mock_chat.return_value = {"response": "Hi there!", "context_sources": []}
        mock_speak.return_value = {"audio_data": audio_data}

        response = client.post("/converse", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["transcription"] == "Hello"
        assert data["response"] == "Hi there!"
        assert "audio_data" in data

def test_reset_session():
    response = client.post("/reset?session_id=test_session")
    assert response.status_code == 200
    assert response.json()["message"] == "Session reset successfully"

if __name__ == "__main__":
    pytest.main([__file__])
