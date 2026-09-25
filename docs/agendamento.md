# Agendamento

A automação roda pelo Agendador de Tarefas do Windows, com **uma tarefa só, todo dia útil às
07:00**. A agenda está dentro do script: ele decide o que gerar em cada dia, e num dia sem
envio sai em menos de um segundo, sem abrir o navegador. Não crie uma tarefa por
periodicidade.

## O que a tarefa roda

A tarefa chama o [executar.bat](../executar.bat), que:

1. entra na pasta do projeto (`cd /d "%~dp0"`), então não depende do campo *"Iniciar em"*;
2. roda `src.main --headless --enviar`: extrai sem janela e, no fim, envia os e-mails;
3. grava a saída e o código de saída em `logs\agendador.log`.

Para voltar ao arranjo de extrair agendado e enviar à mão, tire o `--enviar` do
`executar.bat`; nada mais muda. O que o `--enviar` implica está em
[envio.md](envio.md#enviar-automaticamente-ao-fim-da-extração).

## Situação atual

> **A tarefa existe e está DESABILITADA.** Foi criada com o gatilho e o caminho corretos, mas
> não dispara enquanto a homologação não terminar. Até lá, as rodadas são manuais.

```powershell
# conferir o estado
Get-ScheduledTask -TaskName "Mapa de Estoque - Geweb" | Select-Object TaskName, State

# habilitar, depois de validar tudo (veja instalacao.md)
schtasks /Change /TN "Mapa de Estoque - Geweb" /ENABLE

# desabilitar
schtasks /Change /TN "Mapa de Estoque - Geweb" /DISABLE
```

> ⚠️ **Só uma máquina pode ter a tarefa habilitada.** Duas enviariam em dobro e disputariam a
> sessão do Geweb.

## Criar a tarefa

Numa instalação nova, ou para recriá-la. Ajuste `$raiz` para a pasta do projeto e mantenha as
aspas, porque o caminho pode ter espaços e acentos:

```powershell
$raiz = "C:\caminho\para\mapa-de-estoque"
$acao = New-ScheduledTaskAction -Execute (Join-Path $raiz "executar.bat") -WorkingDirectory $raiz
$gatilho = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 7:00am
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries
Register-ScheduledTask -TaskName "Mapa de Estoque - Geweb" -Action $acao -Trigger $gatilho -Settings $config -Force
Disable-ScheduledTask -TaskName "Mapa de Estoque - Geweb"   # habilite só depois de homologar
```

`-StartWhenAvailable` faz a tarefa rodar assim que a máquina voltar, se estava desligada às
07:00. É o que o mensal recuperável espera (veja
[operacao.md](operacao.md#o-mensal-se-recupera-sozinho)).

Num servidor, configure a tarefa para rodar **"estando o usuário conectado ou não"**, com um
usuário que tenha permissão de escrita no `FORMATADO_DIR`. Nesse modo, unidades mapeadas
(`Z:`) não existem: use caminhos UNC no `.env`.

## Acompanhar

**Você não precisa vigiar o log.** Quando a rodada não termina limpa, o script manda um e-mail
para o `ALERTA_PARA` dizendo o que falhou, nomeando cada laboratório: relatório que não saiu,
arquivo que ficou só no formato bruto, laboratório que ficou de fora por erro de cadastro e
envio que não foi entregue. Rodada limpa **não** gera e-mail: um aviso diário de "tudo certo"
só treina as pessoas a ignorar o alerta.

Para conferir um dia específico, abra a planilha de histórico do mês (veja
[operacao.md](operacao.md#o-histórico-em-excel)) ou o `logs\agendador.log`, que traz início,
fim e código de saída de cada rodada. O código **3** significa "os relatórios saíram, mas
algum e-mail não foi entregue".
