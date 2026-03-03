@echo off
cd /d "%~dp0"
echo Starting Versuni Mystery Shopping Dashboard...
echo.
echo Dashboard will open at: http://localhost:8501
echo Press Ctrl+C to stop.
echo.
py -m streamlit run dashboard/app.py --server.port 8501
pause
