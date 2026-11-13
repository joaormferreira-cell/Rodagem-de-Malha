@echo off
chcp 65001 >nul
title Rodagem de Malha
cd /d "%~dp0"

echo ============================================================
echo   RODAGEM DE MALHA - target de BWT por caminho
echo ============================================================
echo.

set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"

echo [1/3] Preparando os dados (pasta dados_reais)...
"%PY%" teste_local\preparar_dados_reais.py
if errorlevel 1 goto erro
echo.

echo [2/3] Calculando e conferindo (leva cerca de 2 minutos)...
"%PY%" -m malha rodar --dados dados_reais\pronto --saida saida
if errorlevel 1 goto erro
echo.

echo [3/3] Abrindo o Excel do resultado...
for /f "delims=" %%A in ('dir /b /o-d "saida\Rodagem de Malha *.xlsx" 2^>nul') do (
    start "" "saida\%%A"
    goto fim
)

:fim
echo.
echo Pronto. O resultado esta na pasta "saida".
pause
exit /b 0

:erro
echo.
echo ************************************************************
echo   A rodagem parou. Leia as mensagens acima.
echo   Se foi uma checagem, a lista fica em saida\checagens.xlsx
echo ************************************************************
pause
exit /b 1
