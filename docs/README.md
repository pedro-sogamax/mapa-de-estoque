# Documentação

A visão geral e o início rápido estão no [README do projeto](../README.md).

## Guias

| Documento | Para quem | O que tem |
|---|---|---|
| [instalacao.md](instalacao.md) | quem instala | Requisitos, instalação, validação e migração para outra máquina ou servidor |
| [configuracao.md](configuracao.md) | quem cadastra | Todas as chaves do `.env` e os campos do `fabricantes.yaml` |
| [operacao.md](operacao.md) | quem opera | Comandos, agenda, saída, histórico em Excel e códigos de saída |
| [envio.md](envio.md) | quem opera | O envio às indústrias: travas, proteções, e-mail, WhatsApp e mensagens |
| [agendamento.md](agendamento.md) | quem instala | A tarefa agendada do Windows e o alerta de falha |
| [solucao-de-problemas.md](solucao-de-problemas.md) | todos | Sintomas comuns, sessão do Geweb e o que fazer quando a tela muda |
| [desenvolvimento.md](desenvolvimento.md) | quem mantém o código | Testes, estrutura dos arquivos e convenções |

## Desenho

| Documento | O que tem |
|---|---|
| [mapa.md](mapa.md) | O procedimento manual que deu origem ao projeto e o que a automação cobre |
| [disparo.md](disparo.md) | O desenho do envio: arquitetura de canais, decisões e pendências |

## Propostas

Ideias ainda **não implementadas**, guardadas para decisão.

| Documento | Situação |
|---|---|
| [propostas/revisao-semanal.md](propostas/revisao-semanal.md) — com [fluxograma](propostas/revisao-semanal-fluxograma.html) | Relatório semanal ao revisor com recibo de leitura automático. Aguarda aprovação da diretoria e respostas da TI |

## Referência

Arquivos recebidos do comprador. São a fonte do cadastro e do layout, não são lidos pelo código.

| Arquivo | O que é |
|---|---|
| [ENVIO MAPA.xlsx](referencia/ENVIO%20MAPA.xlsx) | **Planilha vigente** (16/09/2026): dias de envio, e-mails e comprador de cada laboratório. Fonte do `fabricantes.yaml` |
| [MAPA.xlsx](referencia/MAPA.xlsx) | Relatório formatado à mão; modelo do layout que o `src/formatador.py` reproduz |
| [MAPA DE ESTOQUE.docx](referencia/MAPA%20DE%20ESTOQUE.docx) | O procedimento manual original, resumido em [mapa.md](mapa.md) |
| [Fabricantes atualizado.xlsx](referencia/Fabricantes%20atualizado.xlsx) | Contatos das indústrias de 26/08/2026. **Obsoleta**, substituída pela `ENVIO MAPA.xlsx` |

O histórico de mudanças está no [CHANGELOG](../CHANGELOG.md).
