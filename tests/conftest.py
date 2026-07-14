"""Test configuration: provide dummy Azure credentials so main.py can be
imported without a real .env file. No real Azure calls are made in unit tests."""
import os
import sys

os.environ.setdefault("AZURE_SPEECH_KEY", "test-speech-key")
os.environ.setdefault("AZURE_SPEECH_REGION", "eastus")
os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com/")
os.environ.setdefault("AZURE_OPENAI_KEY", "test-openai-key")
os.environ.setdefault("AZURE_SEARCH_ENDPOINT", "https://test.search.windows.net")
os.environ.setdefault("AZURE_SEARCH_KEY", "test-search-key")

# Ensure the project root is importable when running pytest from anywhere
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
