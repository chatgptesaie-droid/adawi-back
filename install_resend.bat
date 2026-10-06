@echo off
cd /d "%~dp0"
call .venv\Scripts\activate
pip install resend
python -c "import resend; print('Resend installed successfully')"
pause
