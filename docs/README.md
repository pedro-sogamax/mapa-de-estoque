# Documentação

Instalação, cadastro, agendamento e operação do dia a dia estão no [README do projeto](../README.md).
Aqui fica o desenho do sistema, as propostas e o material que veio do comprador.

## Desenho

| Documento | O que tem |
|---|---|
| [mapa.md](mapa.md) | O procedimento manual que deu origem ao projeto e o que a automação cobre |
| [disparo.md](disparo.md) | O envio às indústrias: canais, cadastro, travas, WhatsApp e pendências |

## Propostas

Ideias ainda **não implementadas**, guardadas para decisão.

| Documento | Situação |
|---|---|
| [propostas/revisao-semanal.md](propostas/revisao-semanal.md) — com [fluxograma](propostas/revisao-semanal-fluxograma.html) | Relatório semanal ao revisor com recibo de leitura automático. Aguarda aprovação da diretoria e respostas da TI |

## Referência

Arquivos recebidos do comprador. São a fonte do cadastro e do layout, não são lidos pelo código.

| Arquivo | O que é |
|---|---|
| [ENVIO MAPA.xlsx](referencia/ENVIO%20MAPA.xlsx) | **Planilha vigente** (15/09/2026): dias de envio, e-mails e comprador de cada laboratório. Fonte do `fabricantes.yaml` |
| [MAPA.xlsx](referencia/MAPA.xlsx) | Relatório formatado à mão; modelo do layout que o `src/formatador.py` reproduz |
| [MAPA DE ESTOQUE.docx](referencia/MAPA%20DE%20ESTOQUE.docx) | O procedimento manual original, resumido em [mapa.md](mapa.md) |
| [Fabricantes atualizado.xlsx](referencia/Fabricantes%20atualizado.xlsx) | Contatos das indústrias de 26/08/2026. **Obsoleta**, substituída pela `ENVIO MAPA.xlsx` |
