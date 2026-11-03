@echo off
cd /d "%~dp0"
where pyw >nul 2>nul && (start "" pyw trimfile.py & exit /b)
where pythonw >nul 2>nul && (start "" pythonw trimfile.py & exit /b)
python trimfile.py
pause
