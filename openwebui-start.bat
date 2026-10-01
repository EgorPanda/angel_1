@echo off
setlocal
title Open WebUI (Angel PC)
cd /d "E:\angel\openwebui-env"
echo Starting Open WebUI at http://127.0.0.1:8080  (Ollama: 127.0.0.1:11434)
echo Close this window to stop. Browser: http://127.0.0.1:8080
start "" http://127.0.0.1:8080
".\Scripts\open-webui.exe" serve --host 127.0.0.1 --port 8080
endlocal