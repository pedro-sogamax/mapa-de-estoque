# Revisão semanal do histórico, com confirmação de leitura

Proposta, **ainda não implementada**. Fluxograma: [revisao-semanal-fluxograma.html](revisao-semanal-fluxograma.html)
(abra no navegador).

> ## O pedido
>
> A diretoria vai designar uma pessoa para analisar o histórico das rodadas toda semana, e
> quer que fique registrado que a planilha foi vista — **sem nenhuma etapa manual**: nada de
> preencher coluna, rodar comando ou responder e-mail.

---

## 1. Por que não dá para registrar quem abre a planilha

A planilha de histórico (`FORMATADO_DIR/logs/AAAA-MM.xlsx`, gerada por
[src/historico.py](../../src/historico.py)) não tem como saber quem a abriu:

- **Um `.xlsx` não executa nada ao ser aberto.** Macro (`.xlsm`) não resolve: o Excel a
  bloqueia em arquivo vindo de pasta sincronizada, e quem abre pode simplesmente não ativar.
- **A planilha é refeita do zero a cada rodada.** `gerar_planilhas` cria um `Workbook()` novo
  e grava por cima — qualquer "visto" digitado no Excel some na rodada seguinte.
- **O ownCloud não vê a abertura.** O cliente de sincronização baixa o arquivo uma vez e daí
  em diante ele é aberto do disco local, sem passar pelo servidor. Pela interface web o acesso
  passa pelo servidor, mas o painel de Atividades mostra criação, alteração e
  compartilhamento, não visualização; registrar leitura exige o app de auditoria
  (`admin_audit`), que grava num log de administrador — a confirmar com quem administra o
  servidor se ele existe na nossa edição.

Conclusão: a abertura só é mensurável se o relatório chegar por um meio que devolva sinal.
O e-mail devolve.

## 2. A proposta

1. **Fim da rodada de segunda.** Depois que os 45 semanais foram extraídos e enviados, a
   própria rodada monta o relatório da semana e o envia à revisora:
   - **no corpo**, os totais da semana (extraídos e enviados) e a lista do que falhou ou
     ficou pendente, por fabricante;
   - **em anexo**, uma planilha de log só daquela semana (terça a segunda), com as mesmas
     abas da planilha mensal filtradas pelo período.

   Não há horário fixo: o relatório sai depois do último envio, para já incluir a maior leva
   da semana — inclusive quando o Geweb está lento ou a segunda recupera um mensal atrasado
   (até 88 mensagens). O gatilho é o dia da semana, não "houve semanal hoje": quando a
   segunda é o 1º dia útil do mês a agenda só gera mensais, e o relatório sai do mesmo jeito.

   **Se a rodada de segunda falhar** (Geweb fora do ar, login quebrado), o relatório sai
   mesmo assim, com a falha entre as pendências. A revisora fica sabendo, e o prazo de
   leitura conta a partir daí.
2. **A revisora abre o e-mail** no Outlook, no celular ou no webmail — tanto faz. Ao abrir,
   o servidor da Locaweb marca a mensagem como lida (`\Seen`), porque a caixa dela é IMAP.
3. **A automação confere a caixa da revisora de hora em hora**, das 8h às 18h nos dias
   úteis, por IMAP e só para ler, e procura o relatório da semana pelo Message-ID que o
   envio devolveu.
   - Marcado como lido → a aba **Revisões** registra *Lido*.
   - Não lido e já passou o **prazo** → a aba registra *Sem leitura* e a gerente recebe um
     alerta.
   - Não lido e o prazo ainda não passou → confere de novo na hora seguinte.
   - **Lido depois do prazo** → a conferência continua depois do alerta, até sair o relatório
     da semana seguinte. Se a revisora ler nesse meio-tempo, a semana passa de *Sem leitura*
     para *Lido após o prazo*, com a data. Não sai outro e-mail: a gerente vê na planilha.

   O prazo é contado em **dias úteis** e fica no `.env` (`REVISAO_PRAZO_DIAS`, padrão **3**):
   relatório de segunda não lido gera alerta na quinta, e um feriado no meio empurra o
   alerta um dia.

   Quando não há relatório pendente — a maior parte da semana —, a conferência sai sem
   conectar a nada.

A **semana do relatório vai de terça a segunda**, fechando com a rodada que o envia.

A única ação humana é a revisora abrir o e-mail — como ela já faz com o resto da caixa.

**A automação nunca pode marcar nada como lido.** A caixa é aberta em modo só leitura
(`EXAMINE`, não `SELECT`) e nenhuma mensagem é baixada por inteiro — só os marcadores. Um
`SELECT` ou um `FETCH` sem `PEEK` marcaria o relatório como lido e forjaria a confirmação.

## 3. O que a diretoria vê

Uma aba nova, **Revisões**, na mesma planilha de histórico que já chega pelo ownCloud:

| SEMANA | ENVIADO EM | LIDO ATÉ | SITUAÇÃO |
|---|---|---|---|
| 09/09 a 15/09 | 15/09 07:09 | 15/09 10:00 | Lido |
| 16/09 a 22/09 | 22/09 07:08 | 26/09 11:00 | Lido após o prazo |
| 23/09 a 29/09 | 29/09 07:11 | — | Sem leitura |

*(linhas de exemplo)*

**"Lido até", não "lido em".** O IMAP guarda *que* a mensagem foi lida, não *quando*. A data
registrada é a da conferência que encontrou a marcação — a leitura aconteceu antes dela.
Com a conferência de hora em hora, a diferença é de no máximo uma hora; uma leitura fora do
horário comercial aparece na primeira conferência seguinte (às 8h do próximo dia útil).

Como as outras abas, ela é projeção, refeita a cada rodada a partir de `dados/revisoes.json`:
por semana, o Message-ID do relatório, quando saiu, quando a leitura foi percebida e se o
alerta já foi. É estado que impede repetição — rodar de novo na segunda não reenvia o
relatório, e o alerta de uma semana sai uma vez só —, por isso fica em `dados/` e não em
`logs/`. Em nenhum caso vai para `logs/envios.jsonl`, que é a base da cota de envio.

A aba é montada a partir desse registro inteiro, não pelo mês de cada evento como as outras:
uma semana que cruza a virada do mês teria o envio num `AAAA-MM.xlsx` e a leitura no seguinte.

## 4. O que prova e o que não prova

**Prova** que o e-mail com o relatório da semana foi aberto na caixa da revisora, até quando,
e quais semanas ficaram sem leitura. A `precificacao@` é usada só pela Nayra, então a caixa
identifica a pessoa.

**Não prova** que o conteúdo foi lido com atenção — nada prova isso sem pedir uma ação da
pessoa. Também não prova que o anexo foi aberto; por isso o resumo vai **no corpo** do
e-mail, e o que se mede é a abertura dele.

**Conta como lido sem ter sido aberto** quando a mensagem é marcada como lida sem abrir
("marcar tudo como lido", ou passar por ela no painel de leitura do Outlook). É o mesmo limite
de qualquer confirmação de leitura.

**Se a mensagem sumir da caixa** (apagada e a lixeira esvaziada, ou movida para uma pasta
que a conferência não olha), vale o último estado visto: se já tinha sido vista lida, fica
*Lido*; se não, cai em *Sem leitura* no prazo. A conferência procura em todas as pastas da
caixa, não só na entrada.

Testado em 29/09/2026: um e-mail enviado pela `confirmacao@` chegou à `precificacao@` como
**não lido**, continuou assim com o Outlook dela aberto, e passou a **lido** quando a Nayra o
abriu. Nada na caixa marca mensagens como lidas sozinho.

## 5. Onde entra no código

| Peça | Onde |
|---|---|
| Envio do relatório | [src/main.py](../../src/main.py), no fim da rodada quando `weekday() == 0`: depois de `_disparar_email`, e também nos `return` de falha do Geweb, para o relatório sair mesmo com a rodada quebrada. `CanalEmail` com `Mensagem.corpo_html` e anexo; o Message-ID vem de `Envio.identificadores` |
| Planilha da semana | [src/historico.py](../../src/historico.py): os eventos de `historico.jsonl` filtrados de terça a segunda, montados com o mesmo `_aba` das planilhas mensais |
| Conferência de leitura | módulo novo, com comando próprio (`python -m src.revisao`), chamado pela tarefa de hora em hora e também em toda rodada, antes do `return` de dia sem tarefa do `main`; fica de fora em `--planejar` e nas rodadas manuais. `EXAMINE` em cada pasta, `SEARCH HEADER Message-ID`, `FETCH (FLAGS)` |
| Tarefa de hora em hora | segunda tarefa agendada no Windows, das 8h às 18h nos dias úteis, só com a conferência — em [docs/agendamento.md](../agendamento.md) e no roteiro de migração, que passa a ter duas tarefas para recriar |
| Trava | a conferência e a rodada gravam no mesmo `dados/revisoes.json` e na mesma planilha. Se a rodada estiver rodando, a conferência pula aquela hora |
| Planilha e log | a conferência só regrava a planilha e só escreve no log quando algo muda (leitura percebida, prazo vencido) — no máximo uma ou duas vezes por semana. Regravar toda hora faria o ownCloud sincronizar o arquivo toda hora, e falharia com a planilha aberta no Excel |
| Aba Revisões | `gerar_planilhas` em [src/historico.py](../../src/historico.py) |
| Alerta de prazo | [src/alerta.py](../../src/alerta.py), que já envia sem passar pela cota das indústrias, mas com destinatário próprio |
| Falha da conferência | senha trocada ou IMAP fora → alerta técnico pelo `ALERTA_PARA`, não *Sem leitura*: a leitura não pôde ser conferida, o que é diferente de não ter acontecido |
| Configuração | `.env`: `REVISAO_PARA` (revisora), `REVISAO_COPIA_PARA` (cópia oculta, opcional), `REVISAO_ALERTA_PARA` (separado do `ALERTA_PARA`, que fica só com os alertas técnicos), `REVISAO_PRAZO_DIAS`, `REVISAO_IMAP_USUARIO`/`REVISAO_IMAP_SENHA` (a caixa da revisora; servidor e porta são os do SMTP, porta 993) |

Nenhum cabeçalho extra no e-mail e nenhuma leitura da `confirmacao@`: o pedido de recibo
(`Disposition-Notification-To`) saiu da proposta.

O relatório e o alerta não passam pela cota interna de 90/hora, mas contam no limite de
100/hora da caixa na Locaweb. Numa segunda comum são 45 + 2; no pior caso, com um mensal
atrasado, 88 + 2 = 90 de 100 — cabe, com pouca folga.

## 6. Em aberto

- [ ] Aprovação da diretoria.

## 7. Decidido em 29/09/2026

- **Revisora:** Nayra, pela caixa `precificacao@sogamax.com.br`, que só ela usa.
- **Como se mede a leitura:** pela marcação de lida no servidor, na caixa dela, e não por
  recibo de leitura. O recibo dependeria de configurar o Outlook dela para enviá-lo sempre,
  o que não é possível; a marcação de lida não depende de configuração e vale também para
  celular e webmail.
- **Senha da caixa da revisora:** guardada no `.env` da máquina da automação
  (`REVISAO_IMAP_SENHA`), usada só para leitura. Login conferido em 29/09/2026.
- **Alerta de prazo:** Eduarda (`eduarda@sogamax.com.br`), gerente da Nayra e dos
  compradores, em `REVISAO_ALERTA_PARA`.
- **Cópia:** a diretoria não recebe o relatório; acompanha pela aba Revisões. No início, o
  Pedro (`pedro@sogamax.com.br`, TI) recebe em **cópia oculta** para validar a ferramenta, e
  sai depois apagando `REVISAO_COPIA_PARA`. Não interfere na medição, que olha só a caixa
  da revisora.
- **Relatório:** totais e pendências no corpo, planilha da semana em anexo.
- **Prazo:** dias úteis, configurável (padrão 3).
- **Frequência da conferência:** de hora em hora, das 8h às 18h nos dias úteis, além da
  rodada diária. Custo: nenhum em dinheiro; ~1 s por execução sem relatório pendente, 2 a
  3 s com; de 2 a 5 conexões à caixa numa semana típica, cerca de 35 se ela não ler até o
  alerta — menos do que o próprio Outlook dela consulta o servidor.
- **Leitura depois do prazo:** a conferência continua até o relatório seguinte, e a semana
  passa a *Lido após o prazo*, com a data, sem novo e-mail.
- **Rodada de segunda quebrada:** o relatório sai mesmo assim.

Descartados:
- **Recibo de leitura** (`Disposition-Notification-To`): exigia configurar o Outlook da
  revisora para sempre devolver o recibo, e não volta nada pelo celular nem pelo webmail.
- **Imagem invisível no e-mail:** exigiria um servidor público, e o Outlook bloqueia imagens
  externas por padrão.
- **Confirmação por comando** (`python -m src.alerta --ciente`): chegou a ser escrita antes
  desta proposta e foi desfeita sem commit — exigia uma etapa manual, o contrário do pedido.
