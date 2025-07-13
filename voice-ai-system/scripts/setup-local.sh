#!/bin/bash

echo "🚀 Setting up Voice AI System for local development..."

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.12+ first."
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "✅ Python version: $PYTHON_VERSION"

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️ Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📚 Installing dependencies..."
pip install -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file from template..."
    cp env.example .env
    echo "⚠️  Please edit .env file with your Azure service keys"
else
    echo "✅ .env file already exists"
fi

# Create logs directory
mkdir -p logs

echo "✅ Local development setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your Azure service keys"
echo "2. Activate virtual environment: source venv/bin/activate"
echo "3. Run the application: python main.py"
echo "4. Open http://localhost:8000 in your browser"
echo "5. For WebSocket testing, open frontend/index.html"
echo ""
echo "Happy coding! 🎉" 