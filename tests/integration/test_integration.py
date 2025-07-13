import pytest
import asyncio
import base64
import json
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from main import app

client = TestClient(app)

@pytest.fixture
def mock_azure_services():
    """Mock all Azure services for integration testing"""
    with patch('main.speech_config'), \
         patch('main.openai_client'), \
         patch('main.search_client'), \
         patch('main.rag_processor'):
        yield

class TestVoiceAIIntegration:
    """Integration tests for the complete voice AI system"""
    
    def test_complete_voice_conversation_flow(self, mock_azure_services):
        """Test the complete voice conversation pipeline"""
        # Mock audio data
        audio_data = base64.b64encode(b"fake audio data").decode('utf-8')
        
        # Mock Azure Speech Services
        with patch('main.SpeechRecognizer') as mock_recognizer, \
             patch('main.SpeechSynthesizer') as mock_synthesizer:
            
            # Mock speech recognition
            mock_recognition_result = Mock()
            mock_recognition_result.text = "What is the weather like?"
            mock_recognition_result.reason.name = "RecognizedSpeech"
            mock_recognizer.return_value.recognize_once.return_value = mock_recognition_result
            
            # Mock speech synthesis
            mock_synthesis_result = Mock()
            mock_synthesis_result.reason.name = "SynthesizingAudioCompleted"
            mock_synthesis_result.audio_data = b"synthesized audio data"
            mock_synthesizer.return_value.speak_text_async.return_value.get.return_value = mock_synthesis_result
            
            # Mock RAG processor
            with patch('main.rag_processor.retrieve_context') as mock_retrieve, \
                 patch('main.rag_processor.generate_response') as mock_generate:
                
                mock_retrieve.return_value = [
                    {
                        "content": "The weather is sunny today.",
                        "title": "Weather Report",
                        "source": "weather_service",
                        "score": 0.95
                    }
                ]
                mock_generate.return_value = "The weather is sunny today with clear skies."
                
                # Test the complete conversation endpoint
                request_data = {
                    "audio_data": audio_data,
                    "session_id": "test_integration_session"
                }
                
                response = client.post("/converse", json=request_data)
                
                assert response.status_code == 200
                data = response.json()
                
                # Verify the complete pipeline worked
                assert data["transcription"] == "What is the weather like?"
                assert data["response"] == "The weather is sunny today with clear skies."
                assert "audio_data" in data
                assert data["session_id"] == "test_integration_session"
                assert "context_sources" in data
    
    def test_session_management(self, mock_azure_services):
        """Test session creation and management"""
        session_id = "test_session_management"
        
        # Test chat with new session
        chat_request = {
            "message": "Hello, this is a test message",
            "session_id": session_id
        }
        
        with patch('main.rag_processor.retrieve_context') as mock_retrieve, \
             patch('main.rag_processor.generate_response') as mock_generate:
            
            mock_retrieve.return_value = []
            mock_generate.return_value = "Hello! How can I help you today?"
            
            response = client.post("/chat", json=chat_request)
            assert response.status_code == 200
            data = response.json()
            assert data["session_id"] == session_id
        
        # Test chat with same session (should maintain context)
        chat_request2 = {
            "message": "What did I just say?",
            "session_id": session_id
        }
        
        with patch('main.rag_processor.retrieve_context') as mock_retrieve, \
             patch('main.rag_processor.generate_response') as mock_generate:
            
            mock_retrieve.return_value = []
            mock_generate.return_value = "You said 'Hello, this is a test message'"
            
            response = client.post("/chat", json=chat_request2)
            assert response.status_code == 200
            data = response.json()
            assert data["session_id"] == session_id
        
        # Test session reset
        reset_response = client.post(f"/reset?session_id={session_id}")
        assert reset_response.status_code == 200
        assert reset_response.json()["message"] == "Session reset successfully"
    
    def test_audio_processing(self, mock_azure_services):
        """Test audio processing utilities"""
        from main import AudioProcessor
        
        # Test base64 encoding/decoding
        original_data = b"test audio data"
        encoded = AudioProcessor.pcm_to_base64(original_data)
        decoded = AudioProcessor.base64_to_pcm(encoded)
        
        assert decoded == original_data
    
    def test_rag_integration(self, mock_azure_services):
        """Test RAG (Retrieval Augmented Generation) integration"""
        query = "What are the benefits of machine learning?"
        
        with patch('main.openai_client.embeddings.create') as mock_embedding, \
             patch('main.search_client.search') as mock_search:
            
            # Mock embedding generation
            mock_embedding_response = Mock()
            mock_embedding_response.data = [Mock()]
            mock_embedding_response.data[0].embedding = [0.1, 0.2, 0.3] * 100  # 300-dim vector
            mock_embedding.return_value = mock_embedding_response
            
            # Mock search results
            mock_search_result = Mock()
            mock_search_result.__iter__ = lambda self: iter([
                {
                    "content": "Machine learning provides automation and pattern recognition capabilities.",
                    "title": "ML Benefits",
                    "source": "ml_guide",
                    "@search.score": 0.95
                }
            ])
            mock_search.return_value = mock_search_result
            
            # Test RAG retrieval
            from main import rag_processor
            context = asyncio.run(rag_processor.retrieve_context(query))
            
            assert len(context) > 0
            assert "content" in context[0]
            assert "title" in context[0]
            assert "source" in context[0]
    
    def test_error_handling(self, mock_azure_services):
        """Test error handling in the system"""
        # Test with invalid audio data
        invalid_request = {
            "audio_data": "invalid_base64_data!@#",
            "session_id": "test_error_session"
        }
        
        response = client.post("/converse", json=invalid_request)
        # Should handle the error gracefully
        assert response.status_code in [400, 500]
    
    def test_websocket_endpoint_availability(self):
        """Test that WebSocket endpoint is available"""
        # This is a basic test to ensure the WebSocket endpoint exists
        # Actual WebSocket testing would require a WebSocket client
        from main import app
        
        # Check if WebSocket route exists
        websocket_routes = [route for route in app.routes if hasattr(route, 'endpoint') and 'websocket' in str(route.endpoint).lower()]
        assert len(websocket_routes) > 0

if __name__ == "__main__":
    pytest.main([__file__]) 