@echo off
echo ====================================
echo Visual Product Matcher Setup
echo ====================================
echo.

echo Step 1: Creating virtual environment...
python -m venv venv
if %errorlevel% neq 0 (
    echo Error: Failed to create virtual environment
    pause
    exit /b 1
)
echo Virtual environment created successfully!
echo.

echo Step 2: Activating virtual environment...
call venv\Scripts\activate.bat
echo.

echo Step 3: Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Error: Failed to install dependencies
    pause
    exit /b 1
)
echo Dependencies installed successfully!
echo.

echo Step 4: Checking for .env file...
if not exist .env (
    echo .env file not found. Creating from .env.example...
    copy .env.example .env
    echo.
    echo IMPORTANT: Please edit .env file and add your GEMINI_API_KEY
    echo Get your API key from: https://makersuite.google.com/app/apikey
    echo.
    notepad .env
)
echo.

echo ====================================
echo Setup Complete!
echo ====================================
echo.
echo To start the application:
echo   1. Make sure you've added your GEMINI_API_KEY to .env
echo   2. Run: python app.py
echo   3. Open http://localhost:5000 in your browser
echo.
echo Press any key to exit...
pause >nul
