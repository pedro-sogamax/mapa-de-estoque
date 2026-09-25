## Objetivo

Automatizar processos de exportação de relatórios do sistema Geweb.

## Problema

Hoje dependemos de forma manual de retirada de relatórios em excel/csv para enviar para os
fornecedores parceiros.

## O procedimento manual

Extraído de [MAPA DE ESTOQUE.docx](referencia/MAPA%20DE%20ESTOQUE.docx). É o que o comprador faz hoje,
fabricante por fabricante:

1. No Geweb, seguir **RELATÓRIOS → MOVIMENTAÇÃO → COMPRAS/VENDAS POR PRODUTO**.
2. Em *Tipo de relatório*, escolher **RELATÓRIO MENSAL – COMPRAS/VENDA (VAREJO)**.
3. Informar o período.
4. Selecionar o fabricante — o campo aceita mais de um código por vez.
5. Clicar em **Gerar**. O relatório sai em Excel.
6. Enviar o arquivo por e-mail à indústria.

O mapa é enviado em periodicidades diferentes conforme o combinado com cada indústria. A
planilha do comprador ([ENVIO MAPA.xlsx](referencia/ENVIO%20MAPA.xlsx)) é quem
manda nisso: uma coluna MENSAL e uma coluna por dia da semana.

## O que a automação cobre

Os passos **1 a 5**: login, navegação, filtros, geração e download, para todos os fabricantes
cadastrados, na periodicidade que a planilha define. O arquivo é gravado com nome e pasta
próprios, sem sobrescrever nada.

Cobre também a formatação que era feita à mão depois do download: cada relatório é gravado como
`.xlsx` formatado em `formatado\`, numa pasta por mês, no mesmo layout de
[MAPA.xlsx](referencia/MAPA.xlsx) — que é justamente um relatório deste script formatado à mão.

O passo **6** também é automático: `python -m src.disparo` envia o e-mail de cada laboratório,
com o anexo, e a tarefa agendada encadeia o envio por e-mail ao fim da extração. O uso está em
[envio.md](envio.md), e o desenho em [disparo.md](disparo.md).

Duas observações sobre o escopo:

- O `.docx` menciona envio **diário** como possibilidade. Nenhum fabricante usa isso hoje, e a
  automação implementa apenas **mensal** e **semanal**.
- O Excel que o Geweb exporta é um `.xls` em HTML com formatação Excel, não um `.xlsx`
  binário. Abre normalmente — é como o próprio Geweb entrega. Ele continua sendo salvo como
  veio, mas quem se envia é a versão formatada, que é `.xlsx` de verdade.

O passo a passo de instalação, cadastro e agendamento está no [índice da documentação](README.md).
