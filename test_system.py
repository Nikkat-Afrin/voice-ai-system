#!/usr/bin/env python3
"""
Voice AI System Test Script

This script tests the basic functionality of the Voice AI system
without requiring actual Azure services (uses mocks).
"""

import asyncio
import base64
import json
import sys
from unittest.mock import Mock, patch

def test_audio_processing():
    """Test audio processing utilities"""
    print("🔧 Testing audio processing...")
    
    # Mock the AudioProcessor class
    from main import AudioProcessor
    
    # Test data
    test_data = b"test audio data for processing"
    
    # Test encoding
    encoded = AudioProcessor.pcm_to_base64(test_data)
    assert isinstance(encoded, str)
    assert len(encoded) > 0
    
    # Test decoding
    decoded = AudioProcessor.base64_to_pcm(encoded)
    assert decoded == test_data
    
    print("✅ Audio processing tests passed")

def test_session_management():
    """Test session management"""
    print("📝 Testing session management...")
    
    from main import ConversationSession
    
    # Create session
    session_id = "test_session_123"
    session = ConversationSession(session_id)
    
    # Test session properties
    assert session.session_id == session_id
    assert len(session.history) == 0
    
    # Add messages
    session.add_message("user", "Hello")
    session.add_message("assistant", "Hi there!")
    
    assert len(session.history) == 2
    assert session.history[0]["role"] == "user"
    assert session.history[0]["content"] == "Hello"
    
    # Test context
    context = session.get_context()
    assert "user: Hello" in context
    assert "assistant: Hi there!" in context
    
    print("✅ Session management tests passed")

def test_websocket_manager():
    """Test WebSocket connection manager"""
    print("🔌 Testing WebSocket manager...")
    
    from main import ConnectionManager
    
    manager = ConnectionManager()
    
    # Test initial state
    assert len(manager.active_connections) == 0
    
    # Test connection tracking
    session_id = "test_ws_session"
    
    # Mock WebSocket
    mock_websocket = Mock()
    mock_websocket.send_text = Mock()
    
    # Test connect (async)
    async def test_connect():
        await manager.connect(mock_websocket, session_id)
        assert session_id in manager.active_connections
        assert manager.active_connections[session_id] == mock_websocket
        
        # Test send message
        test_message = {"type": "test", "data": "hello"}
        await manager.send_message(session_id, test_message)
        mock_websocket.send_text.assert_called_with(json.dumps(test_message))
        
        # Test disconnect
        manager.disconnect(session_id)
        assert session_id not in manager.active_connections
    
    # Run async test
    asyncio.run(test_connect())
    
    print("✅ WebSocket manager tests passed")

def test_rag_processor():
    """Test RAG processor with mocks"""
    print("🔍 Testing RAG processor...")
    
    from main import RAGProcessor
    
    # Mock clients
    mock_search_client = Mock()
    mock_openai_client = Mock()
    
    # Create RAG processor
    rag = RAGProcessor(mock_search_client, mock_openai_client)
    
    # Mock embedding response
    mock_embedding_response = Mock()
    mock_embedding_response.data = [Mock()]
    mock_embedding_response.data[0].embedding = [0.1, 0.2, 0.3] * 100
    mock_openai_client.embeddings.create.return_value = mock_embedding_response
    
    # Mock search results
    mock_search_result = Mock()
    mock_search_result.__iter__ = lambda self: iter([
        {
            "content": "Test content",
            "title": "Test Title",
            "source": "test_source",
            "@search.score": 0.95
        }
    ])
    mock_search_client.search.return_value = mock_search_result
    
    # Test context retrieval
    async def test_retrieve():
        context = await rag.retrieve_context("test query")
        assert len(context) > 0
        assert context[0]["content"] == "Test content"
        assert context[0]["title"] == "Test Title"
    
    asyncio.run(test_retrieve())
    
    print("✅ RAG processor tests passed")

def test_api_endpoints():
    """Test API endpoints with mocked services"""
    print("🌐 Testing API endpoints...")
    
    from fastapi.testclient import TestClient
    from main import app
    
    client = TestClient(app)
    
    # Test health endpoint
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    
    # Test root endpoint (frontend)
    response = client.get("/")
    assert response.status_code == 200
    assert "Voice AI Test" in response.text
    
    print("✅ API endpoint tests passed")

def test_data_models():
    """Test Pydantic data models"""
    print("📊 Testing data models...")
    
    from main import TranscribeRequest, ChatRequest, SpeakRequest, ConverseRequest
    
    # Test TranscribeRequest
    transcribe_req = TranscribeRequest(
        audio_data="dGVzdCBhdWRpbyBkYXRh",
        format="pcm",
        sample_rate=16000
    )
    assert transcribe_req.audio_data == "dGVzdCBhdWRpbyBkYXRh"
    assert transcribe_req.format == "pcm"
    assert transcribe_req.sample_rate == 16000
    
    # Test ChatRequest
    chat_req = ChatRequest(
        message="Hello, how are you?",
        session_id="test_session"
    )
    assert chat_req.message == "Hello, how are you?"
    assert chat_req.session_id == "test_session"
    
    # Test SpeakRequest
    speak_req = SpeakRequest(
        text="Hello world",
        voice="en-US-AriaNeural"
    )
    assert speak_req.text == "Hello world"
    assert speak_req.voice == "en-US-AriaNeural"
    
    # Test ConverseRequest
    converse_req = ConverseRequest(
        audio_data="dGVzdCBhdWRpbyBkYXRh",
        session_id="test_session"
    )
    assert converse_req.audio_data == "dGVzdCBhdWRpbyBkYXRh"
    assert converse_req.session_id == "test_session"
    
    print("✅ Data model tests passed")

def main():
    """Run all tests"""
    print("🚀 Starting Voice AI System Tests...")
    print("=" * 50)
    
    try:
        # Test data models first
        test_data_models()
        
        # Test core components
        test_audio_processing()
        test_session_management()
        test_websocket_manager()
        test_rag_processor()
        
        # Test API endpoints
        test_api_endpoints()
        
        print("=" * 50)
        print("🎉 All tests passed! Voice AI System is ready.")
        print("\nNext steps:")
        print("1. Configure Azure services in .env file")
        print("2. Run: python main.py")
        print("3. Open: http://localhost:8000")
        print("4. Test WebSocket: frontend/index.html")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 