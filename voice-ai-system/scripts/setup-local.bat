@echo off
echo 🚀 Setting up Voice AI System for local development...

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed. Please install Python 3.12+ first.
    pause
    exit /b 1
)

REM Check Python version
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo ✅ Python version: %PYTHON_VERSION%

REM Create virtual environment
echo 📦 Creating virtual environment...
python -m venv venv

REM Activate virtual environment
echo 🔧 Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo ⬆️ Upgrading pip...
python -m pip install --upgrade pip

REM Install dependencies
echo 📚 Installing dependencies...
pip install -r requirements.txt

REM Create .env file if it doesn't exist
if not exist ".env" (
    echo 📝 Creating .env file from template...
    copy env.example .env
    echo ⚠️  Please edit .env file with your Azure service keys
) else (
    echo ✅ .env file already exists
)

REM Create logs directory
if not exist "logs" mkdir logs

echo ✅ Local development setup complete!
echo.
echo Next steps:
echo 1. Edit .env file with your Azure service keys
echo 2. Activate virtual environment: venv\Scripts\activate.bat
echo 3. Run the application: python main.py
echo 4. Open http://localhost:8000 in your browser
echo 5. For WebSocket testing, open frontend/index.html
echo.
echo Happy coding! 🎉
pause 