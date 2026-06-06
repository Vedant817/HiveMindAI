@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0run-local-free.ps1" %*

