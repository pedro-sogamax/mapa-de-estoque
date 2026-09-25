# Desenvolvimento

Como o código está organizado e como testar uma mudança.

## Testes

```powershell
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
```

Os testes cobrem as partes que decidem tudo e **não tocam rede nem navegador**: o calendário
(`src/periodo.py`: 1º dia útil com feriado, virada de ano, as duas janelas semanais), a agenda
(`src/agenda.py`: quem roda hoje e a recuperação do mensal atrasado), a validação do cadastro
(`src/config.py`), o alerta, o histórico e a organização das pastas. Rodam em menos de um
segundo.

Um dos testes carrega o **`fabricantes.yaml` de produção**: qualquer edição no cadastro real
precisa continuar passando. Rode `pytest` depois de mexer no cadastro; é mais rápido e mais
completo que o `--planejar`.

A validação ponta a ponta, com o Geweb de verdade, está em
[instalacao.md](instalacao.md#3-validar).

## Estrutura

| Arquivo | Papel |
|---|---|
| [src/geweb/seletores.py](../src/geweb/seletores.py) | **Único arquivo a ajustar ao Geweb.** Mudou o layout? Conserta aqui |
| [src/geweb/session.py](../src/geweb/session.py) | Abre o navegador, faz login, reaproveita a sessão salva |
| [src/geweb/relatorio_page.py](../src/geweb/relatorio_page.py) | Navega, preenche filtros, clica em Gerar, captura o download |
| [src/geweb/localizador.py](../src/geweb/localizador.py) | Traduz os prefixos `label=` / `placeholder=` / `texto=` dos seletores |
| [src/config.py](../src/config.py) | Lê `.env` e `fabricantes.yaml`, valida |
| [src/periodo.py](../src/periodo.py) | Dia útil e feriado nacional, mês anterior, acumulado do mês, semana fechada, rótulo da pasta |
| [src/agenda.py](../src/agenda.py) | Decide o que cada dia gera: o mensal pendente e os envios semanais |
| [src/estado.py](../src/estado.py) | Lê e grava `dados\estado.json`, o registro do que já foi entregue |
| [src/sequencia.py](../src/sequencia.py) | Contador de `dados\sequencia.json`, com recomposição a partir das pastas de saída |
| [src/formatador.py](../src/formatador.py) | Converte o HTML do Geweb no `.xlsx` formatado. **Único lugar que conhece o layout de saída** |
| [src/main.py](../src/main.py) | Loop por fabricante, tratamento de falha isolada, resumo |
| [src/rodada.py](../src/rodada.py) | Manifesto da última extração: a ponte entre a rodada e o disparo |
| [src/disparo/](../src/disparo/) | O comando de envio: decide a leva, confirma e entrega |
| [src/disparo/canais/](../src/disparo/canais/) | Um módulo por meio de entrega: SMTP, API de WhatsApp e rascunho |
| [src/disparo/limites.py](../src/disparo/limites.py) | Cota horária, disjuntor e teto por rodada |
| [src/descobrir.py](../src/descobrir.py) | Diagnóstico da tela e extração da lista de fornecedores. Não faz parte da rodada |
| [src/alerta.py](../src/alerta.py) | Avisa por e-mail quando a rodada não termina limpa |
| [src/log.py](../src/log.py) | Configuração única do log, com rotação (1 MB × 5 gerações) |
| [src/historico.py](../src/historico.py) | Histórico estruturado das rodadas e as planilhas mensais que os compradores abrem |
| [templates/](../templates/) | Texto e assinatura das mensagens |
| [tests/](../tests/) | Testes automatizados |

O desenho do envio (camada de canais, idempotência, decisões) está em
[disparo.md](disparo.md).

## Convenções

- **Falha isolada.** Um laboratório com problema nunca derruba a rodada: fica de fora, é
  nomeado no resumo e entra no e-mail de alerta.
- **Nada em silêncio.** O que não saiu é registrado com o motivo, no log e no histórico.
- **Estado gravado de forma atômica** (arquivo temporário + `os.replace`), e o registro de
  envios é gravado a cada mensagem.
- **Credenciais só no `.env`.** Nunca em código, log ou documentação.
- Mudanças visíveis para quem usa entram no [CHANGELOG](../CHANGELOG.md).
