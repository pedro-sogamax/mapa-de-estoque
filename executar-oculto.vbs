' Lancador da tarefa agendada: roda o executar.bat SEM janela.
'
' Com a janela do cmd visivel, quem estava na maquina a fechou achando que era lixo, e a
' rodada de 26/10/2026 morreu no meio da extracao, antes de enviar. Sem janela, nao ha o que
' fechar. Tudo continua indo para logs\agendador.log, e o codigo de saida e o do .bat.
'
' Programa/script da tarefa: wscript.exe
' Argumentos           : "<pasta do projeto>\executar-oculto.vbs"

Dim shell, pasta
Set shell = CreateObject("WScript.Shell")
pasta = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
' 0 = janela oculta; True = espera terminar, para a tarefa ver o codigo de saida.
WScript.Quit shell.Run("""" & pasta & "\executar.bat""", 0, True)
