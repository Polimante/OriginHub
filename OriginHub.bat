@echo off
rem Starts OriginHub (requires: pip install -r requirements.txt)
start "" pythonw "%~dp0app\main.py" %*
