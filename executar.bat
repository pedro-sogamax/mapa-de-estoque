@echo off
REM Wrapper para o Agendador de Tarefas do Windows.
REM Roda a extracao do dia, sem janela, e em seguida ENVIA os e-mails as industrias.
REM A saida vai para logs\agendador.log.
REM
REM   --enviar  encadeia `python -m src.disparo --canal email --sim` ao fim da extracao,
REM             sem pedir confirmacao. Tire a flag para voltar a so extrair, com o envio
REM             a mao. O WhatsApp nao entra aqui — so no comando manual.
REM
REM Codigos de saida:
REM   0  tudo certo          2  erro de configuracao
REM   1  extracao falhou     3  extraiu, mas algum e-mail nao foi entregue
REM
REM Configuracao da tarefa agendada:
REM   Programa/script : C:\Users\pedro.veloso\Documents\script-test\executar.bat
REM   Iniciar em      : C:\Users\pedro.veloso\Documents\script-test

setlocal
cd /d "%~dp0"

if not exist "logs" mkdir "logs"

echo. >> "logs\agendador.log"
echo ===== Inicio: %date% %time% ===== >> "logs\agendador.log"

".venv\Scripts\python.exe" -m src.main --headless --enviar >> "logs\agendador.log" 2>&1
set CODIGO=%ERRORLEVEL%

echo ===== Fim: %date% %time% (codigo de saida: %CODIGO%) ===== >> "logs\agendador.log"

exit /b %CODIGO%
