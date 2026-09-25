# Changelog

Mudanças relevantes para quem opera ou mantém o Mapa de Estoque, da mais recente para a mais
antiga. O detalhe de cada uma está no histórico do git.

## 2026-09-25

- Documentação reorganizada: o README virou uma visão geral, e os guias foram para `docs/`
  (instalação, configuração, operação, envio, agendamento, solução de problemas e
  desenvolvimento). Inclui o roteiro de migração para outra máquina ou servidor.
- O estado da automação (`estado.json`, `envios.json`, `sequencia.json`,
  `ultima-rodada.json`) passou da raiz do projeto para `dados/`. A primeira rodada move os
  arquivos sozinha.
- `docs/` organizada com índice, a pasta `referencia/` e a proposta de revisão semanal.

## 2026-09-17

- Histórico das rodadas em planilha: uma por mês, dentro do `FORMATADO_DIR`, com as abas
  `Envios`, `Extracoes` e `Rodadas`, registrando também o que falhou e o motivo.
- `--comprador` filtra a extração e o envio pela carteira de um ou mais compradores.

## 2026-09-16

- **Quatro compradores.** A planilha `ENVIO MAPA.xlsx` passou a trazer a coluna `COMPRADOR`
  preenchida. Todo laboratório ganhou um bloco `comprador` (nome, cargo, telefones e
  `responder_para`), e cada comprador entra na `copia` da própria carteira.
- Entraram 22 laboratórios: são 46 ativos. Saiu a PRINCIPIA, a pedido da compradora, e a
  quinta-feira voltou a ser um dia sem envio.
- A saída ganhou um nível: `COMPRADOR\LABORATORIO\AAAA-MM\arquivo.xlsx`.
- Teto por rodada ajustado para 95 mensagens, para caber o pior caso legítimo (mensal
  atrasado recuperado numa segunda-feira).
- Cadastro novo a partir de `ENVIO MAPA.xlsx`: todos os laboratórios passam a receber o
  semanal de segunda (EUROFARMA_RX e MARJAN também na quarta), entra a CELLERA e sai a ASPEN
  (`ativo: false`).

## 2026-09-15

- Só o `.xlsx` formatado fica guardado, numa pasta por mês. O bruto do Geweb é apagado,
  exceto quando a formatação falha.

## 2026-08-28

- Primeira versão em produção: extração do Geweb, formatação em `.xlsx`, agenda mensal e
  semanal com recuperação do mensal perdido, e envio por e-mail (SMTP) e WhatsApp (API).
- Testes automatizados do calendário, da agenda e da validação do cadastro.
- Um cadastro inválido tira só aquele laboratório da rodada, em vez de derrubá-la inteira.
- Log unificado, com rotação.
- E-mail de alerta quando a rodada não termina limpa.
- Tarefa agendada criada, desabilitada até o fim da homologação.

## 2026-08-27

- Assinatura oficial da Sogamax no e-mail, em HTML com imagens embutidas.
- SANOFI_MEDLEY desligada (`ativo: false`), por fim da parceria.

## 2026-08-26

- Contatos das indústrias cadastrados a partir da coluna `E-MAIL` da planilha do comprador:
  24 laboratórios, canal e-mail.
