# Operação

Como rodar a extração, como a agenda decide o que cada dia gera e onde fica o resultado. O
envio às indústrias está em [envio.md](envio.md).

## Comandos

```powershell
# validar só o login (navegador visível)
.venv\Scripts\python -m src.geweb.session

# o que a rodada faria hoje, sem abrir o Geweb
.venv\Scripts\python -m src.main --planejar

# o mesmo, simulando outra data
.venv\Scripts\python -m src.main --planejar --hoje 2026-09-01

# um fabricante, um mês (use para conferir os números)
.venv\Scripts\python -m src.main --fabricante EUROFARMA_RX --mes 2026-07

# a carteira de um comprador (aceita vários, separados por vírgula)
.venv\Scripts\python -m src.main --comprador "Maria Silva, João Souza" --mes 2026-08

# período livre, para todos os fabricantes
.venv\Scripts\python -m src.main --inicio 2026-07-01 --fim 2026-07-07

# rodada normal: o que a agenda mandar hoje
.venv\Scripts\python -m src.main

# rodada normal e, no fim, os e-mails enviados (é o que o executar.bat faz)
.venv\Scripts\python -m src.main --enviar

# sem abrir janela, como o agendador roda
.venv\Scripts\python -m src.main --headless

# investigar uma falha: log detalhado, com o traceback completo
.venv\Scripts\python -m src.main --debug

# forçar a janela visível mesmo com HEADLESS=true no .env
.venv\Scripts\python -m src.main --no-headless
```

| Opção | Efeito |
|---|---|
| `--planejar` | Mostra o plano do dia e sai. Não abre o Geweb nem grava nada |
| `--hoje AAAA-MM-DD` | Simula outra data (útil com `--planejar`) |
| `--fabricante NOME` | Só um laboratório |
| `--comprador "A, B"` | Só a carteira desses compradores |
| `--mes AAAA-MM` | Um mês fechado, para todos os selecionados. **Ignora a agenda** |
| `--inicio` / `--fim` | Período livre. Andam sempre juntos e também ignoram a agenda |
| `--enviar` | Ao fim da extração, envia os e-mails. Veja [envio.md](envio.md#enviar-automaticamente-ao-fim-da-extração) |
| `--headless` / `--no-headless` | Sobrepõe o `HEADLESS` do `.env` |
| `--debug` | Log detalhado |

`--mes` e `--inicio/--fim` são formas alternativas de dizer a mesma coisa: passar as duas sai
com código 2. As duas ignoram a agenda e não mexem no registro de entregas, então são o jeito
de refazer um mapa antigo.

## A agenda

A tarefa agendada roda todo dia útil, e o script decide o que gerar. Os campos do cadastro
estão em [configuracao.md](configuracao.md#agenda-de-envio).

| Dia | Gera | Duração |
|---|---|---|
| 1º dia útil do mês | os mensais do mês anterior | ~3min30 |
| Segunda | os semanais de todos os laboratórios | ~3min40 |
| Quarta | os semanais de quem tem quarta cadastrada | ~10 s |
| Dia sem envio | nada: sai com código 0 sem abrir o navegador | < 1 s |

Os números exatos mudam com o cadastro. O `--planejar` mostra o plano real de qualquer dia.

**Início de mês.** No 1º dia útil não existe nada acumulado ainda, então o semanal daquele dia
é **coberto pelo mensal**: o laboratório recebe o mês anterior fechado, que sai no mesmo dia,
em vez do acumulado. O log diz isso explicitamente. É o único dia do mês em que acontece.

Exemplo: em agosto de 2026, o dia 1º caiu num sábado. O 1º dia útil foi a segunda, 03/08, e
os laboratórios de segunda receberam o fechamento de julho. Na quarta, 05/08, quem tinha
quarta recebeu o acumulado normal, de 01/08 a 04/08.

**Semana fechada.** Com `janela_semanal: semana_fechada`, o período vira **segunda a sexta**
da última semana encerrada, ancorada na última sexta-feira. Rodar na segunda ou na quarta
devolve sempre a mesma semana.

**Feriado.** O 1º dia útil considera os feriados **nacionais** brasileiros, pela biblioteca
[`holidays`](https://pypi.org/project/holidays/). Feriado estadual ou municipal não entra;
para incluir os de um estado, troque `holidays.Brazil()` por `holidays.Brazil(subdiv="RJ")`
(ou a sigla desejada) em [src/periodo.py](../src/periodo.py).

**Período que cruza a virada do mês.** O próprio Geweb quebra o relatório em duas colunas, uma
por mês.

### O mensal se recupera sozinho

Se a rotina dependesse só da data, uma máquina desligada no 1º dia útil faria os mapas do mês
**não saírem, em silêncio**, porque no dia seguinte a checagem de data recusaria a rodada.

Por isso a condição real não é "hoje é o 1º dia útil", e sim **"o mês anterior ainda não foi
entregue a este laboratório"**. O registro fica em `dados\estado.json`:

```json
{ "mensal": { "ACHE": "2026-07", "BIOPAS": "2026-07" } }
```

Três consequências:

- **Dia perdido é recuperado.** A primeira rodada de qualquer dia útil gera o que ficou para
  trás, avisando no log: `RECUPERANDO o mensal de 2026-08, que devia ter saído em 01/09`.
- **Nunca duplica.** Rodar dez vezes no mesmo dia gera os relatórios uma vez só.
- **A recuperação é por laboratório.** Se 40 saíram e 3 falharam, no dia seguinte só os 3
  voltam a ser tentados. O registro só é gravado depois de o Geweb responder, com o arquivo ou
  informando que não houve movimento. Uma falha de verdade (timeout, código inexistente,
  sessão caída) não registra nada.

Já um **semanal** perdido não é refeito: quem tem dois dias na semana é coberto pelo envio
seguinte, porque a janela acumula desde o dia 1º; quem só tem segunda espera a próxima semana.

`--planejar` consulta o registro, mas nunca escreve nele. Para forçar a regeração de um mês,
use `--mes`, ou apague a linha do laboratório em `estado.json`.

## Saída

O Geweb entrega o relatório em `DOWNLOAD_DIR`, ele é formatado em `FORMATADO_DIR` e **só o
formatado fica**:

```
downloads\Maria Silva\EUROFARMA_RX\2026-07\0001_EUROFARMA_RX_2026-07.xls    <- como o Geweb entregou (apagado)
formatado\Maria Silva\EUROFARMA_RX\2026-07\0001_EUROFARMA_RX_2026-07.xlsx   <- pronto para enviar (guardado)
```

**A primeira pasta é o comprador**, para cada um achar a própria carteira. O nome sai do bloco
`comprador` do laboratório; sem ele, do `COMPRADOR` do `.env`; sem nenhum dos dois, de uma
pasta `SEM_COMPRADOR`, que deixa a falta visível.

O bruto é apagado assim que o `.xlsx` é gravado, junto com as pastas que ficarem vazias. A
exceção é a formatação que falha: aí o bruto fica, porque é o único arquivo que resta para
enviar (veja [O arquivo formatado](#o-arquivo-formatado)).

**A pasta é o mês dos dados.** Dentro dela ficam o mensal e todos os acumulados daquele mês;
o período exato fica no nome do arquivo:

```
formatado\Maria Silva\MARJAN\2026-08\0078_MARJAN_2026-08-01_a_2026-08-24.xlsx   <- acumulado
formatado\Maria Silva\MARJAN\2026-08\0087_MARJAN_2026-08-01_a_2026-08-30.xlsx   <- acumulado
formatado\Maria Silva\MARJAN\2026-08\0105_MARJAN_2026-08.xlsx                   <- mensal de agosto
formatado\Maria Silva\MARJAN\2026-09\0112_MARJAN_2026-09-01_a_2026-09-13.xlsx
```

O mensal de agosto, gerado em setembro, fica em `2026-08`. Um intervalo que atravessa a virada
do mês fica no mês em que começa.

### Numeração sequencial

Cada arquivo recebe um número único e crescente, guardado em `dados\sequencia.json`. O
contador:

- **sobrevive entre execuções:** reextrair o mesmo período gera um arquivo novo (`0001_...` e
  `0003_...` convivem), preservando o histórico;
- **não abre buracos:** se um laboratório falhar, o número reservado volta para a fila;
- **se recompõe sozinho:** apagado o `sequencia.json`, ele varre `downloads\` e `formatado\` e
  retoma do maior número existente.

### Logs

| Arquivo | Conteúdo |
|---|---|
| `logs\execucao.log` | A narrativa da extração, com rotação (1 MB × 5 gerações) |
| `logs\disparo.log` | A narrativa do envio |
| `logs\agendador.log` | Início, fim e código de saída de cada rodada agendada |
| `logs\historico.jsonl` | Um evento por laboratório e etapa: a fonte da planilha de histórico |
| `logs\envios.jsonl` | Uma linha por mensagem que saiu: auditoria e cota horária |

## O histórico, em Excel

Para saber **o que deu certo e o que deu errado num dia** sem ler log de texto, cada rodada
reescreve uma planilha por mês dentro do `FORMATADO_DIR`:

```
<FORMATADO_DIR>\logs\2026-09.xlsx
```

Três abas, com cabeçalho congelado e autofiltro. Cada comprador acha a própria carteira
filtrando a coluna `COMPRADOR`:

| Aba | Uma linha por | Colunas |
|---|---|---|
| `Envios` | mensagem | data, hora, comprador, laboratório, período, canal, destinatário, **resultado**, **motivo**, id |
| `Extracoes` | relatório | data, hora, comprador, laboratório, período, **resultado**, **motivo**, arquivo |
| `Rodadas` | dia + etapa | data, etapa, ok, falha, não tentado, total |

O `resultado` é `ok`, `falha` ou `nao tentado` (e `sem dados`, na extração). **O que não saiu é
registrado junto com o motivo.**

**A planilha é uma projeção, não a fonte da verdade.** Se alguém deixar o `.xlsx` aberto no
Excel, o Windows trava a gravação: a rodada apenas avisa e segue, porque o dado já está no
`historico.jsonl` e a planilha é refeita inteira no comando seguinte. Para refazer na hora:

```powershell
.venv\Scripts\python -m src.historico
```

> ⚠️ O nome da planilha **não pode começar com número seguido de `_`**. A pasta fica dentro do
> `FORMATADO_DIR`, e o [src/sequencia.py](../src/sequencia.py) contaria o arquivo como
> relatório numerado. `2026-09.xlsx` é seguro, e há teste cobrindo isso.

## O arquivo formatado

O Geweb entrega um `.xls` que na verdade é HTML: sem formatação e com os números gravados como
texto em pt-BR (`1.269,92`). [src/formatador.py](../src/formatador.py) converte cada um num
`.xlsx` no layout de [docs/referencia/MAPA.xlsx](referencia/MAPA.xlsx), um relatório
formatado à mão cujo layout foi medido célula a célula:

| | |
|---|---|
| Formato | `.xlsx` binário de verdade, não HTML renomeado |
| Aba | o nome do arquivo (truncado em 31 caracteres, limite do Excel) |
| Fonte | Arial 9 |
| Cabeçalho | negrito, centralizado, quebra de linha, **congelado** ao rolar |
| Colunas | largura ajustada ao conteúdo; `DESCRIÇÃO` à esquerda, o resto centralizado |
| Números | número de verdade, não texto: dá para somar e filtrar |
| `EAN` | inteiro, sem notação científica |
| Coluna de valor | `#,##0.00`, negativo em vermelho |
| Linhas de grade | desligadas |

O conteúdo não muda: as mesmas 11 colunas, na mesma ordem, com os mesmos valores do Geweb.

**Se a conversão falhar** (o Geweb devolveu uma página de erro, ou mudou o relatório), a rodada
**não** é interrompida: o `.xls` bruto fica em `DOWNLOAD_DIR`, e o resumo avisa quais precisam
ser formatados à mão:

```
ok    EUROFARMA_RX               mensal           2026-07
      formatacao falhou: ...
1 relatorio(s) sairam so no formato bruto do Geweb — formate a mao antes de enviar.
```

Para conferir a conversão de um bruto guardado, sem abrir o Geweb:

```powershell
.venv\Scripts\python -m src.formatador `
  downloads\EUROFARMA_RX\2026-07\0001_EUROFARMA_RX_2026-07.xls `
  teste.xlsx
```

## Códigos de saída

| Código | Quando |
|---|---|
| `0` | Tudo certo, inclusive o dia sem envio, o `--planejar` e a formatação que falhou (o bruto fica para envio manual) |
| `1` | Algum laboratório falhou, ou a sessão/login caiu antes de qualquer extração |
| `2` | Erro de configuração que impede a rodada: `.env` incompleto, `fabricantes.yaml` ilegível ou sem nenhum laboratório válido, período malformado, `--fabricante` inexistente ou seletor por preencher. Um laboratório isolado com cadastro inválido **não** cai aqui: ele fica de fora e a rodada segue |
| `3` | Só com `--enviar`: os relatórios saíram, mas algum e-mail não foi entregue |
