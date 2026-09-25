# Revisão semanal do histórico, com recibo de leitura

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

1. **Fim da rodada de segunda.** Depois que os 46 semanais foram extraídos e enviados, a
   própria rodada monta o resumo da semana e o envia ao revisor, com a planilha anexada. Não
   há horário fixo: o relatório sai depois do último envio, para já incluir a maior leva da
   semana — inclusive quando o Geweb está lento ou a segunda recupera um mensal atrasado
   (até 89 mensagens).
2. **Pedido de recibo.** O e-mail leva o cabeçalho padrão `Disposition-Notification-To`.
   Ao abri-lo, o programa de e-mail do revisor devolve o recibo sozinho.
3. **O recibo volta para a `confirmacao@`**, a caixa que já envia os mapas.
4. **A rodada diária lê essa caixa por IMAP** e procura o recibo da semana.
   - Chegou → a aba **Revisões** registra *Lido*, por quem e quando.
   - Não chegou e já passaram **3 dias** → a aba registra *Sem leitura* e o diretor recebe um
     alerta.
   - Não chegou e ainda não passaram 3 dias → confere de novo na próxima rodada.

A **semana do relatório vai de terça a segunda**, fechando com a rodada que o envia.

A única ação humana é o revisor abrir o e-mail.

## 3. O que o diretor vê

Uma aba nova, **Revisões**, na mesma planilha de histórico que já chega pelo ownCloud:

| SEMANA | ENVIADO EM | LIDO POR | LIDO EM | SITUAÇÃO |
|---|---|---|---|---|
| 09/09 a 15/09 | 15/09 07:09 | revisor@… | 15/09 09:14 | Lido |
| 23/09 a 29/09 | 29/09 07:11 | — | — | Sem leitura |

*(linhas de exemplo)*

Como as outras abas, ela é projeção: os envios e recibos ficam registrados num arquivo em
`logs/`, e a aba é refeita a partir dele a cada rodada.

## 4. O que prova e o que não prova

**Prova** que o e-mail com o relatório da semana foi aberto, por quem e quando, e quais
semanas ficaram sem leitura.

**Não prova** que o conteúdo foi lido com atenção — nada prova isso sem pedir uma ação da
pessoa. Também não prova que o anexo foi aberto; por isso o resumo vai **no corpo** do
e-mail, e o que se mede é a abertura dele.

O recibo pode ser recusado se o programa de e-mail estiver configurado para perguntar antes
de enviar. O alerta de 3 dias cobre esse caso.

## 5. Onde entra no código

| Peça | Onde |
|---|---|
| Envio do relatório | [src/main.py](../../src/main.py), depois de `_disparar_email`, só na rodada de segunda |
| Leitura dos recibos | módulo novo, chamado em toda rodada (inclusive nos dias sem extração) |
| Aba Revisões | `gerar_planilhas` em [src/historico.py](../../src/historico.py) |
| Alerta de 3 dias | [src/alerta.py](../../src/alerta.py), que já envia sem passar pela cota das indústrias |
| Configuração | `.env`: destinatário do relatório e credenciais IMAP da `confirmacao@` |

O relatório e o alerta são 1 ou 2 e-mails a mais numa segunda que já manda 46 — longe do
limite de 100/hora da caixa na Locaweb.

## 6. Em aberto

- [ ] Programa de e-mail do revisor (Outlook/Exchange, Gmail…) e se a TI consegue deixar o
      recibo **automático**, sem perguntar.
- [ ] Acesso IMAP à `confirmacao@` (hoje o projeto só usa SMTP).
- [ ] Nome e e-mail do revisor; se o diretor recebe cópia do relatório.
- [ ] Aprovação da diretoria.

Descartado: uma confirmação por comando (`python -m src.alerta --ciente`) chegou a ser
escrita antes desta proposta e foi desfeita sem commit — exigia uma etapa manual, o contrário
do pedido.
