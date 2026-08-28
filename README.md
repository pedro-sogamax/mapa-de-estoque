# Mapa de Estoque — extração automática do Geweb

Automatiza o passo descrito em [docs/mapa.md](docs/mapa.md): gerar e baixar o relatório
**Compras/Vendas por Produto → Relatório Mensal (Compras/Venda Varejo)** no Geweb, para cada
fabricante, sem clicar em nada.

Os arquivos saem **já formatados**, e `python -m src.disparo` os entrega às indústrias por
e-mail e WhatsApp — com confirmação antes, rodado por uma pessoa. Para a rodada agendada
entregar sozinha, o `--enviar` encadeia o disparo ao fim da extração, **só pelo e-mail** e
sem perguntar. O desenho completo do envio está em [docs/disparo.md](docs/disparo.md).

---

## 1. Instalação (uma vez)

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\playwright install chromium
```

Depois, copie o `.env.example` para `.env` e preencha as credenciais do Geweb:

```powershell
copy .env.example .env
notepad .env
```

São vinte e sete chaves, lidas por [src/config.py](src/config.py):

| Variável | Obrigatória | Padrão | Para que serve |
|---|---|---|---|
| `GEWEB_URL` | **sim** | — | URL da tela de **login** (não a do menu) |
| `GEWEB_USUARIO` | **sim** | — | Usuário do Geweb — de preferência um dedicado à automação |
| `GEWEB_SENHA` | **sim** | — | Senha correspondente |
| `DOWNLOAD_DIR` | não | `downloads` | Onde os relatórios brutos do Geweb são gravados (veja *Saída*) |
| `FORMATADO_DIR` | não | `formatado` | Onde vai o `.xlsx` já formatado, pronto para enviar |
| `HEADLESS` | não | `false` | `true` roda sem abrir janela |
| `TIMEOUT_MS` | não | `30000` | Timeout das ações de tela |
| `TIMEOUT_RELATORIO_MS` | não | `180000` | Timeout da geração do relatório, que demora bem mais |
| `SLOW_MO_MS` | não | `0` | Atraso artificial entre ações, para depurar (ex.: `300`) |
| `ENVIOS_DIR` | não | `envios` | Onde os rascunhos são gravados — só com `--rascunho` |
| `COMPRADOR` | não | — | Nome que assina o e-mail e o WhatsApp |
| `REMETENTE` | não | vazio | `From` da mensagem. Vazio = a própria caixa do `SMTP_USUARIO` |
| `RESPONDER_PARA` | não | vazio | `Reply-To`, quando a resposta deve ir para outra caixa |
| `DESTINATARIO_TESTE` | não | vazio | **Trava de teste do e-mail**: preenchido, manda tudo para esse endereço. Aceita vários, separados por vírgula |
| `TELEFONE_TESTE` | não | vazio | **Trava de teste do WhatsApp** — independente da de e-mail |
| `SMTP_HOST` / `SMTP_PORTA` | não | `smtp.locaweb.com.br` / `587` | Servidor de envio |
| `SMTP_SEGURANCA` | não | `starttls` | `starttls` (587) ou `ssl` (465) |
| `SMTP_USUARIO` / `SMTP_SENHA` | para enviar | — | Caixa que envia. Sem elas o canal de e-mail é pulado |
| `WHATSAPP_PROVEDOR` | não | `zapi` | Perfil de API a usar |
| `ZAPI_URL_BASE` / `ZAPI_INSTANCIA` / `ZAPI_TOKEN` / `ZAPI_CLIENT_TOKEN` | para enviar | — | Credenciais. Sem elas o canal de WhatsApp é pulado |
| `INTERVALO_ENVIO_S` | não | `5` | Segundos entre laboratórios, para não parecer disparo em massa |
| `MAX_ENVIOS_POR_RODADA` | não | `30` | Recusa a leva acima disso — pega cadastro duplicado |
| `MAX_ENVIOS_POR_HORA` | não | `90` | Cota por canal, abaixo do limite do provedor |
| `MAX_FALHAS_SEGUIDAS` | não | `3` | Falhas que desligam um canal |
| `MAX_TENTATIVAS` | não | `3` | Tentativas por mensagem, só para erro temporário |
| `MAX_ANEXO_MB` | não | `10` | Recusa anexo acima disso |

Faltando uma das três obrigatórias, a rodada sai com **código 2** antes de abrir o navegador.

> ⚠️ `HEADLESS` só reconhece `1`, `true`, `sim`, `yes` ou `y` como verdadeiro. Qualquer outro
> valor — inclusive `on` ou `verdadeiro` — é lido como `false`, sem aviso.

> O `.env` está no `.gitignore` e nunca deve ser compartilhado nem versionado. O mesmo vale
> para `.auth\state.json`: ele guarda o cookie de sessão autenticado e vale tanto quanto a
> senha. O `.gitignore` protege contra o Git, não contra cópia da pasta, backup ou pasta
> sincronizada em nuvem — vale conferir onde o `DOWNLOAD_DIR` e o `FORMATADO_DIR` apontam.

---

## 2. Seletores do Geweb

Já preenchidos em [src/geweb/seletores.py](src/geweb/seletores.py), a partir de uma gravação do
fluxo real. O que o Geweb faz e como é tratado:

| Comportamento do Geweb | Como é tratado |
|---|---|
| Todo o conteúdo vive dentro do iframe `#IFrameConteudo` | `IFRAME_RELATORIO` |
| Sidebar sanfona: cada nível só aparece após clicar no pai | 3 cliques em `MENUS_ATE_O_RELATORIO` |
| Cada item de menu carrega seu código (`5-2-10`) | selecionado por código, não por texto |
| Tipo de relatório e Fabricante são widgets **select2** | clicar → buscar → escolher |
| Datas são `<input type="date">`, em formato ISO | `FORMATO_DATA = "%Y-%m-%d"` |
| Fabricante é buscado por **código** (`13963` → `(13963) EUROFARMA`) | `codigo` no `fabricantes.yaml` |
| **Gerar** abre um popup e dispara o download | popup fechado automaticamente |

### Armadilhas já resolvidas (não reintroduza)

Cada uma custou uma execução falha até ser identificada:

- **Texto do menu vem duplicado** — `textContent` do link é `"Relatórios Relatórios"`, porque o
  ícone SVG tem um `<title>` igual ao rótulo. `:text-is("Relatórios")` acha **zero**. Por isso os
  menus são selecionados pelo código (`5-0-0`), não pelo texto.
- **`[class~=]`, nunca `[class*=]`** — `5-0-0` é substring de `15-0-0`, que é o botão **Sair**.
- **Fabricante é select2 de múltipla escolha** — o elemento com o id é o `<ul>` interno, vazio e
  de altura zero; o Playwright recusa clicar nele. O alvo é a caixa em volta (`:has(...)`).
- **A busca do select2 múltiplo é `<textarea>`, não `<input>`** — um seletor com `input.` acha zero.
- **A opção casa por trecho, não exato** — `role=option[name="(13963)"]` não acha
  `(13963) EUROFARMA`; use `[role=option]:has-text(...)`.
- **O `.xls` gerado é HTML** com formatação Excel (`mso-number-format`). Abre no Excel
  normalmente — é como o Geweb exporta —, mas não é um `.xlsx` binário, e os números vêm como
  texto em pt-BR (`1.269,92`). É por isso que existe o [formatador](#o-arquivo-formatado).
- **Escolher o tipo de relatório carrega um modelo salvo por AJAX** e repovoa o formulário
  inteiro — empresas, tipos de movimento, grupos, layout — **redefinindo as datas para o mês
  corrente**. Esta foi a falha mais perigosa de todas: o relatório saía com dados e parecia
  certo, mas vinha do mês errado. Duas defesas: esperar `#vazia_nome_selecao` deixar de estar
  vazio (sinal de que o modelo carregou) e preencher as datas **por último**, conferindo-as
  logo antes de clicar em Gerar.

### Se a tela mudar

```powershell
.venv\Scripts\python -m src.descobrir
```

Faz login, mapeia a sidebar, testa cada clique da navegação e imprime os ids reais de todos os
campos da tela. Resultado em `logs\descoberta.log` (reescrito a cada execução). É a ferramenta
para reencontrar seletores sem precisar adivinhar. Se um dos cliques de menu falhar, ela sai
com código 1 e aponta a lista de links que encontrou.

Para checar só o preenchimento, sem gerar relatório nenhum:

```powershell
.venv\Scripts\python -m src.descobrir --fluxo
```

Percorre navegação → período → fabricante lendo os campos entre as etapas, mas **não clica em
Gerar**. Útil para confirmar que o modelo salvo não sobrescreveu as datas.

### Se a tela mudar no futuro

Regrave o fluxo e reajuste **apenas** o `seletores.py`:

```powershell
.venv\Scripts\playwright codegen --target python -o gravacao.py https://sistemas.sogamax.com.br/sistema/login.php
```

> ⚠️ O `gravacao.py` guarda a senha digitada em texto puro. Está no `.gitignore` — apague o
> arquivo depois de extrair os seletores.

---

## 3. Cadastrar os fabricantes

Edite [fabricantes.yaml](fabricantes.yaml). Cada item tem `nome` (vira pasta de saída) e os
códigos do Geweb.

**Um laboratório pode ter vários códigos** — um por divisão/CD (RX, OTC, genérico, cada centro
de distribuição). Como o campo Fabricante aceita múltipla escolha, todos entram no mesmo
relatório. No cadastro atual são quatro casos assim, todos com dois códigos: `ACHE`,
`BIOSINTETICA_RX`, `ASPEN` e `TORRENT` — os demais têm um só.

```yaml
- nome: BIOPAS               # um código só
  codigo: 106499

- nome: TORRENT              # dois códigos somados num arquivo
  codigos: [21411, 54843]
```

Quem manda nisso é a planilha do comprador: os códigos unidos por `" - "` na coluna
`ID FABRICANTE` são os que entram **juntos** no mesmo relatório. Códigos em linhas
separadas viram **arquivos separados**, mesmo quando o nome é igual (é o caso das duas
unidades da Brace Pharma).

Para achar os códigos, a lista completa dos 1140 fornecedores está em
`logs\fabricantes-geweb.txt` (formato `(codigo) NOME`). Para atualizá-la:

```powershell
.venv\Scripts\python -m src.descobrir --fabricantes
```

### Agenda de envio: mensal + dias da semana

O cadastro vem de [docs/FABRICANTES ENVIO MAPA.xlsx](docs/FABRICANTES%20ENVIO%20MAPA.xlsx),
que define **dois envios independentes**. Um fabricante pode receber os dois:

| Campo | Quando dispara | Período que o relatório cobre |
|---|---|---|
| `mensal: true` (padrão) | **1º dia útil do mês** (pula sábado, domingo e feriado nacional) — ou na primeira rodada seguinte, se aquele dia for perdido | o mês anterior inteiro (`2026-07`) |
| `dias_semana: [segunda, quarta]` | nesses dias da semana | do **dia 1º do mês corrente até ontem** (`2026-08-01_a_2026-08-04`) |

```yaml
- nome: BIOPAS            # só o mensal
  codigo: 106499

- nome: MARJAN            # mensal + dois envios por semana
  codigo: 7127
  dias_semana: [segunda, quarta]
```

Como o mensal só dispara enquanto o mês anterior não tiver saído (veja *O mensal se recupera
sozinho*) e o semanal só nos dias marcados, **a tarefa agendada pode rodar todo dia útil**:
nos dias sem envio ela não abre o Geweb e sai com código 0.

Dois outros campos completam o cadastro:

| Campo | Efeito |
|---|---|
| `ativo: false` | Pula o fabricante sem tirá-lo da lista — é assim que se desliga um envio |
| `mensal: false` | Só o semanal. **Exige `dias_semana`** — sem ele o fabricante não teria envio nenhum, e a rodada para com código 2 |

`dias_semana` aceita **apenas segunda a sexta** — um sábado ou domingo no cadastro derruba a
rodada com código 2. A grafia é livre: `TERÇA-FEIRA`, `Terça` e `terca` são o mesmo dia, e o
dia repetido é ignorado em vez de gerar o relatório duas vezes.

**Confira a agenda antes de rodar de verdade** — `--planejar` mostra o plano sem tocar no
Geweb, e `--hoje` simula outra data:

```powershell
.venv\Scripts\python -m src.main --planejar
.venv\Scripts\python -m src.main --planejar --hoje 2026-09-01
```

**Outra janela semanal.** Se alguma indústria preferir a semana fechada em vez do mês
acumulado, use `janela_semanal: semana_fechada` naquele fabricante — aí o período vira
**segunda a sexta** da última semana encerrada (sábado e domingo ficam de fora), ancorada na
última sexta-feira, de modo que rodar na segunda ou na quarta devolve sempre a mesma semana.

**Início de mês.** No 1º dia útil não existe nada acumulado ainda, então o envio semanal
daquele dia é **coberto pelo mensal**: o fabricante recebe o mês anterior fechado, que sai
no mesmo dia, em vez do acumulado. O log diz isso explicitamente.

Esse é o **único** dia do mês em que acontece — vale para qualquer mês, comece ele em
sábado, domingo ou feriado. Exemplo real: em agosto/2026 o dia 1º caiu num sábado, o 1º dia
útil foi segunda 03/08, e os quatro fabricantes de segunda (DIFFUCAP, EUROFARMA_RX, MARJAN,
SANOFI_MEDLEY) receberam o fechamento de julho. Na quarta 05/08 a MARJAN já recebeu o
acumulado normal, `01/08 a 04/08`.

**Feriado.** O cálculo do 1º dia útil usa a biblioteca [`holidays`](https://pypi.org/project/holidays/)
com os feriados **nacionais** brasileiros. Se o dia 1º cair num feriado, o mensal espera o
próximo dia de expediente. Feriado municipal ou estadual **não** entra — para incluir os de
São Paulo, troque `holidays.Brazil()` por `holidays.Brazil(subdiv="SP")` em
[src/periodo.py](src/periodo.py).

### O mensal se recupera sozinho

Se a rotina dependesse só da data, uma máquina desligada no 1º dia útil faria os 24 mapas do
mês **não saírem — em silêncio**, porque no dia seguinte a checagem de data recusaria a
rodada. É a pior falha possível numa automação: você para de conferir justamente porque
confia nela.

Por isso a condição real não é "hoje é o 1º dia útil", e sim **"o mês anterior ainda não foi
entregue a este fabricante"**. O registro fica em `estado.json`, na raiz:

```json
{ "mensal": { "ACHE": "2026-07", "ASPEN": "2026-07" } }
```

Três consequências, todas desejáveis:

- **Dia perdido é recuperado.** A primeira rodada de qualquer dia útil gera o que ficou
  para trás, avisando no log: `RECUPERANDO o mensal de 2026-08, que devia ter saído em 01/09`.
- **Nunca duplica.** Rodar dez vezes no mesmo dia gera os relatórios uma vez só.
- **A recuperação é por fabricante.** Se 22 saíram e 2 falharam, no dia seguinte só os 2
  falharam voltam a ser tentados. O registro só é gravado depois de o Geweb ter respondido —
  com o arquivo, ou informando que não houve movimento no período. Uma falha de verdade
  (timeout, código inexistente, sessão caída) não registra nada.

`--planejar` consulta o registro mas nunca escreve nele. Para forçar a regeração de um mês,
apague a linha do fabricante em `estado.json` — ou, mais direto, use `--mes 2026-08`, que
ignora a agenda por completo e não mexe no registro.

**Período que cruza a virada do mês:** o próprio Geweb quebra o relatório em duas colunas,
uma por mês. A pasta continua identificada pelas datas inicial e final, então nada se
sobrescreve.

Passar `--mes` ou `--inicio/--fim` na linha de comando **ignora a agenda** e vale para todos
os fabricantes — é o modo de refazer um mapa antigo.

---

## 4. Usar

```powershell
# validar só o login (navegador visível)
.venv\Scripts\python -m src.geweb.session

# o que a rodada faria hoje, sem abrir o Geweb
.venv\Scripts\python -m src.main --planejar

# um fabricante, um mês — use este para conferir os números
.venv\Scripts\python -m src.main --fabricante EUROFARMA_RX --mes 2026-07

# período livre, para todos os fabricantes
.venv\Scripts\python -m src.main --inicio 2026-07-01 --fim 2026-07-07

# rodada normal: o que a agenda mandar hoje
.venv\Scripts\python -m src.main

# rodada normal e, no fim, os e-mails ja enviados — e o que o executar.bat faz
.venv\Scripts\python -m src.main --enviar

# como o agendador roda
.venv\Scripts\python -m src.main --headless

# investigar uma falha: log detalhado, com o traceback completo
.venv\Scripts\python -m src.main --debug

# forçar a janela visível mesmo com HEADLESS=true no .env
.venv\Scripts\python -m src.main --no-headless
```

`--mes` e `--inicio/--fim` são formas alternativas de dizer a mesma coisa: passar as duas sai
com código 2. `--inicio` e `--fim` andam sempre juntos.

### Saída

Cada relatório sai em **duas versões**, em duas árvores iguais:

```
downloads\EUROFARMA_RX\2026-07\0001_EUROFARMA_RX_2026-07.xls    <- como o Geweb entregou
formatado\EUROFARMA_RX\2026-07\0001_EUROFARMA_RX_2026-07.xlsx   <- pronto para enviar
```

O bruto nunca é apagado: se um dia a formatação sair errada, o arquivo original continua lá.

Fica **dentro do projeto**, não na pasta Downloads do Windows. Os destinos são o
`DOWNLOAD_DIR` e o `FORMATADO_DIR` do `.env`:

| `DOWNLOAD_DIR=` | Onde grava |
|---|---|
| `downloads` | `...\script-test\downloads\` (relativo ao projeto) |
| `D:\MapaEstoque` | `D:\MapaEstoque\` |
| `\\servidor\publico\mapas` | direto na pasta de rede |
| `C:\Users\<voce>\OneDrive\Mapas` | dentro do OneDrive, sincronizando sozinho |

`FORMATADO_DIR` segue exatamente as mesmas regras. As duas pastas são independentes — dá para
deixar o bruto local e mandar só o formatado para a pasta de rede ou para o OneDrive, que é o
arranjo mais útil quando outra pessoa vai pegar o arquivo para enviar.

> ⚠️ **Pasta de rede:** use o caminho UNC completo (`\\servidor\pasta`), **nunca a letra
> mapeada** (`Z:\pasta`). Unidades mapeadas só existem dentro da sessão interativa do
> Windows; com a tarefa agendada rodando *"estando o usuário conectado ou não"*, o `Z:` não
> existe e a extração falha ao salvar. Confirme também que o usuário da tarefa agendada tem
> permissão de escrita no compartilhamento.

O período vira o nome da pasta: mês cheio → `2026-07`; intervalo livre →
`2026-07-27_a_2026-07-31`. Assim uma extração semanal nunca sobrescreve a mensal.

**Numeração sequencial** — cada arquivo recebe um número único e crescente, para nenhum
relatório sair com o mesmo nome de outro. O contador fica em `sequencia.json`, na raiz, e:

- **sobrevive entre execuções** — reextrair o mesmo fabricante e período gera um arquivo
  novo (`0001_...` e `0003_...` convivem), preservando o histórico;
- **não abre buracos** — se um fabricante falhar, o número reservado volta para a fila;
- **se recompõe sozinho** — apagado o `sequencia.json`, ele varre `downloads\` e retoma do
  maior número existente, para nunca reaproveitar um número já usado.

Log: `logs\execucao.log` — acumula todas as rodadas, sem rotação.

Códigos de saída:

| Código | Quando |
|---|---|
| `0` | Tudo certo — inclusive o dia sem envio e o `--planejar` |
| `1` | Algum fabricante falhou, ou a sessão/login caiu antes de qualquer extração |
| `2` | Erro de configuração: `.env` incompleto, `fabricantes.yaml` inválido, período malformado, `--fabricante` inexistente, ou seletor ainda por preencher |
| `3` | Só com `--enviar`: os relatórios saíram, mas algum e-mail não foi entregue — o mesmo código do `src.disparo` |

### O arquivo formatado

O Geweb entrega um `.xls` que na verdade é HTML: sem formatação nenhuma e com os números
gravados como texto em pt-BR (`1.269,92`). Era isso que alguém abria no Excel e formatava à
mão, um por um, antes de mandar para a indústria.

[src/formatador.py](src/formatador.py) faz esse trabalho ao fim de cada extração. O modelo é o
[docs/MAPA.xlsx](docs/MAPA.xlsx) — um relatório deste script formatado à mão, cujo layout foi
medido célula a célula e reproduzido:

| | |
|---|---|
| Formato | `.xlsx` binário de verdade, não HTML renomeado |
| Aba | o nome do arquivo (truncado em 31 caracteres, limite do Excel) |
| Fonte | Arial 9 |
| Cabeçalho | negrito, centralizado, quebra de linha, **congelado** ao rolar |
| Colunas | largura ajustada ao conteúdo; `DESCRIÇÃO` à esquerda, o resto centralizado |
| Números | número de verdade, não texto — dá para somar e filtrar |
| `EAN` | inteiro, sem notação científica |
| Coluna de valor | `#,##0.00`, negativo em vermelho |
| Linhas de grade | desligadas |

Conteúdo não muda: são as mesmas 11 colunas, na mesma ordem, com os mesmos valores que o Geweb
mandou. O formatador só converte e formata.

**Se a conversão falhar** (o Geweb devolveu uma página de erro, ou mudou o relatório), a rodada
**não** é interrompida e o código de saída continua `0`: o `.xls` bruto já está salvo e é
exatamente o arquivo que o comprador enviava antes. O resumo avisa quais precisam ser
formatados à mão:

```
ok    EUROFARMA_RX               mensal           2026-07
      formatacao falhou: ...
1 relatorio(s) sairam so no formato bruto do Geweb — formate a mao antes de enviar.
```

Para conferir a conversão de um arquivo já baixado, sem abrir o Geweb:

```powershell
.venv\Scripts\python -m src.formatador `
  downloads\EUROFARMA_RX\2026-07\0001_EUROFARMA_RX_2026-07.xls `
  teste.xlsx
```

---

## 5. Enviar às indústrias

```powershell
.venv\Scripts\python -m src.disparo --dry-run    # mostra tudo, não envia nada
.venv\Scripts\python -m src.disparo              # mostra, pergunta e envia
```

O comando **envia de verdade**, por e-mail, por WhatsApp ou pelos dois, conforme o cadastro de
cada laboratório. Rodado assim, quem dispara é uma pessoa, depois da extração — e é o único
jeito de usar o WhatsApp. Para a extração agendada entregar os e-mails sozinha, veja
*[Enviar automaticamente ao fim da extração](#enviar-automaticamente-ao-fim-da-extração)*.

```
4 mensagem(ns) a enviar — periodo 01/08/2026 a 16/08/2026
TESTE   email     tudo vai para pedro@sogamax.com.br
REAL    whatsapp  vai para as INDUSTRIAS

  DIFFUCAP           email     estoque@diffucap.com.br
  MARJAN             email     suprimentos@marjan.com.br
  MARJAN             whatsapp  +5511988887777  (com anexo)
  SANOFI_MEDLEY      whatsapp  +5511977776666

Enviar 4 mensagem(ns) — whatsapp vai para as INDUSTRIAS?
Digite SIM para confirmar: _
```

Repare que o aviso é **por canal**: cada trava protege um canal só, e o comando diz na cara
qual está protegido e qual vai para fora.

### Enviar automaticamente ao fim da extração

```powershell
.venv\Scripts\python -m src.main --enviar
```

Com `--enviar`, a extração termina e chama o disparo na sequência, equivalente a rodar
`python -m src.disparo --canal email --sim`. É o que o [executar.bat](executar.bat) faz, e
portanto o que a tarefa agendada faz: os relatórios saem do Geweb e os e-mails partem, sem
ninguém digitar nada.

Três limites deliberados:

- **Só o canal de e-mail.** O WhatsApp continua exclusivo do comando manual. Um canal que
  pode fazer um número ser banido não entra numa tarefa agendada por tabela.
- **É opt-in.** Sem a flag, `python -m src.main` continua só extraindo — a garantia de que
  rodar a extração à mão nunca envia nada segue de pé.
- **Roda em processo separado**, para o disparo manter o próprio `logs\disparo.log` e o
  próprio código de saída.

O que o `--enviar` troca por automação é exatamente **uma** proteção: a confirmação `SIM`.
Todas as outras continuam valendo, e são elas que sustentam o modo automático —
`envios.json` (não reenvia o que já saiu), teto de 30 por rodada, cota de 90/h, disjuntor de
3 falhas e a trava `DESTINATARIO_TESTE`. Vale reler a lista abaixo com essa lente: no modo
agendado, ninguém está olhando na hora.

Se a extração não gerar arquivo nenhum, o disparo **não** é chamado — sem isso ele releria o
manifesto da rodada anterior. E quem falhou na extração simplesmente não vira mensagem: só
entra na leva o que tem arquivo.

### As travas contra engano

1. **A confirmação.** Nada sai antes de você digitar `SIM`. `--sim` pula, para quando já
   conferiu no `--dry-run`.
2. **`DESTINATARIO_TESTE` e `TELEFONE_TESTE`** no `.env`. Preenchidos, todo o canal vai para
   você e nenhuma indústria é tocada. São **independentes** — preencher só um deixa o outro
   canal enviando de verdade, e é por isso que o cabeçalho marca `TESTE` ou `REAL` linha a
   linha.

   O `DESTINATARIO_TESTE` aceita **mais de um endereço**, separados por vírgula:

   ```ini
   DESTINATARIO_TESTE=pedro@sogamax.com.br, yuritoso@sogamax.com.br
   ```

   É o que permite o comprador acompanhar a homologação vendo exatamente o que a indústria
   veria, sem que ninguém precise desligar a trava para isso — que seria a forma errada de
   resolver o mesmo problema. Com a trava ligada, o campo `copia` de cada laboratório é
   **suprimido** junto: ninguém de fora entra na mensagem por nenhuma via.
3. **`envios.json`.** O que já foi entregue não é reenviado. O registro é gravado **a cada
   mensagem**, não no fim: se o comando morrer na décima de vinte e quatro, as nove que saíram
   ficam registradas. `--refazer` ignora isso, de propósito.

### Proteções contra descontrole

As travas da seção anterior protegem contra engano — alguém rodar o comando sem querer. Estas
protegem contra o **sistema disparando além do razoável**, que é o que faz um provedor
suspender a conta de e-mail da empresa.

| Proteção | Padrão | O que ela impede |
|---|---|---|
| **Teto por rodada** | 30 | Um `fabricantes.yaml` duplicado ou um manifesto errado virar centenas de mensagens. Recusa **antes de conectar**, com código 2 |
| **Cota por hora** | 90/canal | Estourar o limite da Locaweb (100/h por caixa). Ao atingir, para e diz a partir de que hora continuar |
| **Disjuntor** | 3 falhas | Insistir com um servidor que já está recusando tudo. Desliga aquele canal; os outros seguem |
| **Retentativa** | 3 tentativas | Perder um envio por soluço passageiro — mas **só** repete erro temporário |
| **Anexo grande** | 10 MB | Anexar o arquivo errado |

Todas anunciam o motivo quando agem, e o que não saiu aparece no resumo como *"não tentado —
fica para a próxima rodada"*. Nada é silenciosamente descartado.

**O que é temporário e o que não é.** Erro `4xx` do SMTP (caixa cheia, servidor ocupado,
greylist) e queda de conexão são transitórios: até duas retentativas, esperando 5 s e 15 s, e
a conexão é reaberta antes de tentar de novo. Erro `5xx` e destinatário inexistente são
definitivos — falham na hora, porque repetir só gasta reputação do remetente.

**Credencial recusada é caso à parte:** uma tentativa e a leva inteira para. Repetir login com
senha errada 24 vezes é o caminho mais curto para o provedor bloquear a conta.

**Histórico de auditoria.** Cada mensagem que sai é registrada em `logs\envios.jsonl`, uma
linha por envio, só acrescentando:

```json
{"em": "2026-08-24T07:12:33", "canal": "email", "fabricante": "MARJAN", "id": "<...@sogamax.com.br>"}
```

É o que alimenta a cota horária, e é também o registro do que **realmente** saiu — o
`envios.json` guarda só o último envio de cada laboratório, então um `--refazer` apagaria o
rastro do anterior.

O `--dry-run` mostra tudo isso antes de qualquer conexão: quanto da cota já foi usado, se a
leva cabe, e quais endereços recebem mais de uma mensagem.

```
  ATENCAO: mapa@eurofarma.com.br recebe 2 e-mails nesta leva (EUROFARMA, EUROFARMA_RX)

  cota email     0 de 90 usados na ultima hora; cabem mais 90, a leva pede 24
  teto por rodada: 30 mensagens
```

O aviso de endereço repetido não bloqueia: EUROFARMA e EUROFARMA_RX são relatórios diferentes,
de códigos diferentes do Geweb, e mandar separado pode ser o certo. Mas quem digita `SIM`
precisa saber que aquela pessoa vai receber duas mensagens.

### Configurar o e-mail

O domínio da Sogamax é hospedado na **Locaweb**, que oferece SMTP autenticado padrão. No `.env`:

```ini
SMTP_HOST=email-ssl.com.br
SMTP_PORTA=465
SMTP_SEGURANCA=ssl
SMTP_USUARIO=mapa@sogamax.com.br     # endereço COMPLETO, com @
SMTP_SENHA=...                       # a senha da própria caixa
RESPONDER_PARA=yuri@sogamax.com.br
```

Host, porta e segurança já vêm preenchidos — só faltam usuário e senha.

Vale usar uma **caixa dedicada** (`mapa@`) em vez da pessoal do comprador, com
`RESPONDER_PARA` apontando para ele — assim a indústria responde para quem cuida do mapa.

> ⚠️ A Locaweb exige que **quem assina seja a conta que autenticou**. Deixe `REMETENTE` vazio
> (o padrão usa o próprio `SMTP_USUARIO`); preenchê-lo com outro endereço faz o servidor
> recusar cada mensagem com *503 Client host rejected*. Para direcionar as respostas, use
> `RESPONDER_PARA`, que não tem essa restrição.

Uma conexão serve a leva inteira. Se as credenciais forem recusadas, o comando sai com código
3 sem tentar mensagem nenhuma.

### Configurar o WhatsApp

Depende de contratar um provedor de API não oficial. Enquanto `ZAPI_INSTANCIA` e `ZAPI_TOKEN`
estiverem vazios, o canal é **pulado com aviso** — o e-mail funciona sozinho.

```ini
WHATSAPP_PROVEDOR=zapi
ZAPI_URL_BASE=https://api.z-api.io
ZAPI_INSTANCIA=...
ZAPI_TOKEN=...
ZAPI_CLIENT_TOKEN=...
INTERVALO_ENVIO_S=5
```

> ⚠️ **API não oficial contraria os termos de uso da Meta.** O número pode ser banido sem
> aviso e sem recurso. Use um **número dedicado**, nunca o pessoal do comprador nem o
> principal da empresa. A sessão também cai sozinha (troca de aparelho, atualização,
> inatividade) e só volta com QR Code presencial — quando isso acontece o comando falha
> visivelmente, com o motivo, e os e-mails saem assim mesmo.

`INTERVALO_ENVIO_S` espaça as mensagens. Disparar 24 iguais em rajada é exatamente o padrão
que faz um número ser banido.

As rotas ficam em [whatsapp_api.py](src/disparo/canais/whatsapp_api.py), numa tabela de
perfis. O perfil `zapi` está pronto; **outro provedor exige um perfil próprio**, conferido na
documentação oficial dele — os nomes dos campos divergem entre provedores.

### Cadastrar os contatos

**Cadastrado em 26/08/2026**, a partir da coluna `E-MAIL` de
[docs/Fabricantes atualizado.xlsx](docs/Fabricantes%20atualizado.xlsx): os 24 laboratórios têm
e-mail, todos com `copia: [pedro@sogamax.com.br, yuritoso@sogamax.com.br]` e `canais: [email]`.
Telefone não existe na planilha, então o WhatsApp continua fora.

Desses 24, **23 estão ativos**: a SANOFI_MEDLEY foi desligada em 27/08/2026 com `ativo: false`,
por fim da parceria.

> ⚠️ Isso mudou a natureza da proteção. Antes, um mapa não podia chegar a fornecedor porque
> **nenhum endereço de fornecedor existia** no projeto. Agora existem, e a única coisa entre o
> sistema e as indústrias é o `DESTINATARIO_TESTE` no `.env` — esvaziá-lo é a ação que libera
> o envio real. Confira sempre com `--dry-run` antes.

Dois contatos atendem mais de um laboratório do mesmo grupo econômico:
`eduardo.lucena@underskin.com.br` cobre as duas Brace Pharma, GERMED e LEGRAND, e
`roberto.mattos@ems.com.br` cobre EMS_RX e LAFIMAN. São 20 endereços distintos para 24
laboratórios, e o `--dry-run` avisa quem recebe mais de uma mensagem na leva.

O cadastro fica no [fabricantes.yaml](fabricantes.yaml):

```yaml
  - nome: EUROFARMA_RX
    codigo: 13963
    dias_semana: [segunda]
    contatos: &eurofarma          # âncora: a outra entrada do grupo reaproveita
      emails: [mapa.estoque@eurofarma.com.br]
      copia: [yuri@sogamax.com.br]
      whatsapp: ["+5511999999999"]
      canais: [email, whatsapp]   # um, outro, ou os dois
      whatsapp_anexo: true        # manda a planilha no WhatsApp também

  - nome: EUROFARMA
    codigo: 14232
    contatos: *eurofarma          # mesmo destinatário, sem duplicar o dado
```

Cada laboratório já tem a linha modelo comentada, é só descomentar e preencher.

| Campo | Efeito |
|---|---|
| `canais` | por onde este laboratório recebe: `[email]`, `[whatsapp]` ou os dois |
| `whatsapp_anexo` | `true` manda o `.xlsx` pelo WhatsApp; `false` (padrão) só avisa que foi por e-mail |
| `copia` | vai em cópia no e-mail |

### Mais de um comprador

`COMPRADOR` e `RESPONDER_PARA` no `.env` valem para o projeto inteiro. Hoje isso basta —
os 24 laboratórios são do YURI TOSO. Quando entrar um laboratório de outro comprador, o
bloco `comprador` sobrepõe os dois **naquele laboratório**:

```yaml
  - nome: ACHE
    codigos: [106975, 106976]
    comprador: &yuri                        # âncora, como a de contatos
      nome: YURI TOSO
      responder_para: yuritoso@sogamax.com.br

  - nome: OUTRO_LAB
    codigo: 12345
    comprador: {nome: MARIA SILVA, responder_para: maria@sogamax.com.br}
```

Sem o bloco, valem os do `.env` — nada muda para quem já está cadastrado. Os dois campos
andam juntos de propósito: são a mesma decisão de negócio vista de dois ângulos. O `nome`
**assina** a mensagem (é o `{COMPRADOR}` do template), e o `responder_para` recebe a
resposta. Errar o primeiro é pior, porque a indústria vê a assinatura de outra pessoa.

O `nome` é obrigatório dentro do bloco: um `comprador` sem ele derruba a rodada com código
2, em vez de mandar um mapa sem assinatura.

**Um laboratório com dois compradores.** O `responder_para` aceita vários endereços,
separados por vírgula — a resposta da indústria chega aos dois:

```yaml
  - nome: LAB_COMPARTILHADO
    codigo: 12345
    comprador:
      nome: YURI TOSO e MARIA SILVA          # é o texto que assina, escreva como quiser
      responder_para: yuritoso@sogamax.com.br, maria@sogamax.com.br
```

Repare que `responder_para` e `copia` resolvem coisas diferentes, e o segundo comprador
provavelmente quer as duas:

| Campo | Onde fica | O que a pessoa recebe |
|---|---|---|
| `responder_para` | bloco `comprador` | só a **resposta** da indústria, quando ela responde |
| `copia` | bloco `contatos` | o **mapa enviado**, no mesmo momento em que a indústria recebe |

Quem só está no `responder_para` não fica sabendo que o mapa saiu — só aparece na conversa
se a indústria responder. Para acompanhar os envios, o endereço precisa estar em `copia`.

> ⚠️ A trava `DESTINATARIO_TESTE` **suprime a `copia`** (e não o `responder_para`). Em
> homologação, portanto, o segundo comprador não recebe as cópias — o que é o certo, já que
> nesse modo tudo já está indo para os endereços de teste.

> A trava `DESTINATARIO_TESTE` **não** sobrepõe o `responder_para`. Ela protege quem
> *recebe* o mapa; mandar a resposta para o comprador certo é o comportamento correto mesmo
> em homologação — é justamente o que se quer conferir antes de liberar.

A âncora (`&nome` / `*nome`) evita repetir o contato nos grupos que aparecem duas vezes —
EUROFARMA/EUROFARMA_RX, as duas Brace Pharma, ACHE/BIOSINTETICA.

> ⚠️ A âncora precisa ser **definida antes de ser usada**, na ordem do arquivo. Como
> `EUROFARMA` vem antes de `EUROFARMA_RX`, é o primeiro que leva o `&euro` e o segundo que
> usa `*euro`. Invertido, o YAML falha com *"found undefined alias"* e a rodada sai com
> código 2.

Quem não tiver contato **continua sendo extraído normalmente** — só não entra no envio, e
aparece nominalmente no resumo. Telefone vai em formato internacional (`+5511999999999`) e
e-mail precisa de `@`; os dois são conferidos no carregamento, com código 2 antes de qualquer
conexão.

### O texto das mensagens

Fica em [templates/](templates/), fora do código:

| Arquivo | Papel |
|---|---|
| `email.txt` | assunto (**1ª linha**) e o corpo em texto puro |
| `email.html` | o mesmo corpo em HTML, com a assinatura da Sogamax |
| `whatsapp.txt` | a mensagem do WhatsApp |
| `assinatura/` | logo e ícones das redes, embutidos na mensagem |

Variáveis: `{FABRICANTE}`, `{PERIODO}`, `{COMPRADOR}`, `{CARGO}`, `{TELEFONES}`,
`{EMAIL_COMPRADOR}`, `{DATA}` e, só no WhatsApp, `{EMAILS}`.

**Toda mensagem sai nas duas versões** (`multipart/alternative`): quem renderiza HTML vê a
assinatura completa; quem não renderiza — cliente antigo, leitor de tela, filtro corporativo —
lê o texto puro, com a mesma informação. O `email.html` é opcional: apagá-lo faz a mensagem
voltar a sair só em texto.

### A assinatura

Reproduz a assinatura oficial do Outlook: logo à esquerda, barra `#0099CC`, Verdana 9pt,
rótulos em ciano e o endereço da empresa. Os dados da pessoa vêm do comprador — nome, cargo,
telefones e e-mail —, então **o formato é padronizado e o conteúdo é de quem assina**.

As imagens são **embutidas na mensagem** (`cid:`), nunca baixadas de um servidor. Isso importa
por dois motivos: a assinatura aparece sem o destinatário precisar clicar em "baixar imagens", e
uma imagem remota num e-mail automático é lida por filtros como pixel de rastreamento. É o mesmo
mecanismo que o Outlook já usa.

Para trocar a marca, troque os arquivos em `templates/assinatura/` — o código não conhece
nenhuma imagem por nome além da tabela `IMAGENS_ASSINATURA` em
[src/disparo/eml.py](src/disparo/eml.py).

Os dados de quem assina saem do `.env` (`COMPRADOR`, `COMPRADOR_CARGO`, `COMPRADOR_TELEFONES`,
`RESPONDER_PARA`) ou, quando houver mais de um comprador, do bloco `comprador` do laboratório:

```yaml
    comprador:
      nome: Yuri Toso
      cargo: Compras
      telefones: 0800 022 1210 / (22) 2785-2614 / (22) 98817-5168
      responder_para: yuritoso@sogamax.com.br
```

Cada campo cai para o `.env` sozinho, então um bloco que só define o `nome` continua herdando
cargo e telefones do padrão.

### Opções

| Flag | Efeito |
|---|---|
| *(nenhuma)* | envia o que a última extração gerou |
| `--dry-run` | mostra o plano completo e sai, sem abrir conexão |
| `--sim` | não pergunta antes de enviar |
| `--periodo 2026-07` | envia uma leva antiga, varrendo o `FORMATADO_DIR` |
| `--fabricante MARJAN` | só um laboratório |
| `--canal email` / `--canal whatsapp` | só um canal |
| `--refazer` | reenvia o que já foi enviado |
| `--rascunho` | **não envia**: grava os `.eml` e a página `wa.me` para envio manual |
| `--forcar` | libera o teto de mensagens por rodada |

Códigos de saída: `0` tudo entregue, `2` erro de configuração, **`3` algum envio falhou** —
distinto do `1` da extração, para o log distinguir "não gerei" de "gerei e não entreguei".

### Quando um provedor cair

`--rascunho` volta ao modo de preparação: grava um `.eml` por laboratório, que o Outlook abre
pronto com anexo, e uma página com links `wa.me`. Serve para entregar o mapa no mesmo dia sem
depender de SMTP nem de API.

O rascunho **não** marca nada como entregue no `envios.json` — montar um arquivo não é
entregar, e registrar ali bloquearia o envio de verdade depois. O link `wa.me` também não
carrega arquivo, então laboratórios com `whatsapp_anexo: true` são avisados no resumo.

---

## 6. Agendar no Windows

**Uma tarefa só, todo dia útil.** A agenda está dentro do script — ele decide o que gerar em
cada dia, e num dia sem envio sai em 0,4 s sem nem abrir o navegador. Não crie uma tarefa
por periodicidade.

```powershell
schtasks /Create /TN "Mapa de Estoque - Geweb" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 07:00 /TR "C:\Users\pedro.veloso\Documents\script-test\executar.bat" /F
```

Ou pelo Agendador de Tarefas → Criar Tarefa Básica:

- **Gatilho:** semanalmente, seg/ter/qua/qui/sex, 07:00
- **Ação:** Iniciar um programa
- **Programa/script:** `C:\Users\pedro.veloso\Documents\script-test\executar.bat`

Não precisa preencher *"Iniciar em"*: o `.bat` faz `cd /d "%~dp0"` sozinho, justamente para
não depender da pasta de trabalho da tarefa. O log fica em `logs\agendador.log`, com início,
fim e código de saída de cada rodada.

**A tarefa extrai e envia.** O `.bat` chama `src.main --headless --enviar`, então cada
rodada termina com os e-mails já entregues às indústrias — veja
*[Enviar automaticamente ao fim da extração](#enviar-automaticamente-ao-fim-da-extração)*
para o que isso implica. Para voltar ao arranjo anterior (extrair agendado, enviar a mão),
tire o `--enviar` do [executar.bat](executar.bat); nada mais muda.

O código de saída **3** no `agendador.log` é a assinatura de "os relatórios saíram, mas
algum e-mail não foi entregue". Vale conferir esse log de vez em quando: no modo agendado
ninguém vê a falha na hora.

O que sai em cada dia:

| Dia | Gera | Duração |
|---|---|---|
| 1º dia útil do mês | 23 mensais do mês anterior | ~1min30 |
| Segunda | 3 semanais (DIFFUCAP, EUROFARMA_RX, MARJAN) | ~20 s |
| Quarta | 1 semanal (MARJAN) | ~7 s |
| Terça, quinta e sexta | nada | 0,4 s |

> A SANOFI_MEDLEY saiu da agenda em 27/08/2026 (parceria encerrada) — está no
> `fabricantes.yaml` com `ativo: false`, o que a tira da extração e do envio sem apagar o
> cadastro. Era a única de quinta-feira, e por isso aquele dia ficou vazio.

> **Máquina desligada no dia certo não é problema para o mensal** — a próxima rodada
> recupera (veja *O mensal se recupera sozinho*). Já um envio **semanal** perdido não é
> refeito: quem tem dois dias na semana é coberto pelo envio seguinte, porque a janela
> acumula desde o dia 1º; quem só tem segunda espera a próxima semana.

---

## Ordem de validação recomendada

1. `python -m src.geweb.session` → o navegador loga e para na home.
2. Um fabricante, um mês → **abra o Excel e compare com o relatório gerado à mão**. Este é o
   teste que realmente importa. Confira também o cabeçalho da última coluna: precisa dizer
   `JULHO_2026`, e não o mês corrente.
3. Rodada completa → um arquivo por fabricante e resumo no final.
4. Coloque um `codigo` inválido num fabricante → os demais devem concluir normalmente e ele
   aparecer como falha no resumo.
5. Repita com `--headless` → resultado idêntico. É comum quebrar aqui na primeira vez.
6. Só então agende.

---

## Uma sessão por usuário — restrição do Geweb

O Geweb aceita **uma única sessão por usuário**. Se o comprador estiver logado no navegador,
o script é recusado com:

```
Usuário já logado no sistema para empresa (10501)!
IP: 172.16.130.31
```

O script identifica essa mensagem e falha com um recado claro em vez de um timeout genérico.

Três formas de conviver com isso, da melhor para a pior:

1. **Usuário dedicado à automação** no Geweb (ex.: `automacao`), com permissão apenas para
   esse relatório. Nunca conflita com ninguém e o log do ERP fica rastreável. **Recomendado.**
2. **Agendar fora do expediente** (madrugada), quando ninguém está logado.
3. Rodar manualmente, saindo do Geweb antes.

A sessão salva em `.auth\state.json` é reaproveitada entre execuções, então o script não faz
login toda vez — mas quando ela expira, a restrição volta a valer.

---

## Sessão manual (se o Geweb exigir 2FA ou captcha)

O login automático não passa por 2FA. Alternativa: abrir a sessão à mão uma vez e salvar o
estado autenticado, que o script reaproveita:

```powershell
.venv\Scripts\playwright open --save-storage=.auth\state.json https://SEU-GEWEB/login
```

Faça o login na janela que abrir e feche. O arquivo `.auth\state.json` passa a ser usado nas
rodadas seguintes; quando a sessão expirar, repita o comando.

---

## Estrutura

| Arquivo | Papel |
|---|---|
| [src/geweb/seletores.py](src/geweb/seletores.py) | **Único arquivo a ajustar ao Geweb.** Mudou o layout? Conserta aqui. |
| [src/geweb/session.py](src/geweb/session.py) | Abre o navegador, faz login, reaproveita a sessão salva |
| [src/geweb/relatorio_page.py](src/geweb/relatorio_page.py) | Navega, preenche filtros, clica em Gerar, captura o download |
| [src/geweb/localizador.py](src/geweb/localizador.py) | Traduz os prefixos `label=` / `placeholder=` / `texto=` dos seletores |
| [src/config.py](src/config.py) | Lê `.env` e `fabricantes.yaml`, valida |
| [src/periodo.py](src/periodo.py) | Dia útil e feriado nacional, mês anterior, acumulado do mês, semana fechada, rótulo da pasta |
| [src/agenda.py](src/agenda.py) | Decide o que cada dia gera: o mensal pendente e os envios semanais |
| [src/estado.py](src/estado.py) | Lê e grava `estado.json` — o registro do que já foi entregue |
| [src/sequencia.py](src/sequencia.py) | Contador de `sequencia.json`, com recomposição a partir de `downloads\` |
| [src/formatador.py](src/formatador.py) | Converte o HTML do Geweb no `.xlsx` formatado — **único lugar que conhece o layout de saída** |
| [src/main.py](src/main.py) | Loop por fabricante, tratamento de falha isolada, resumo |
| [src/rodada.py](src/rodada.py) | Manifesto da última extração — a ponte entre a rodada e o disparo |
| [src/disparo/](src/disparo/) | O comando de envio: decide a leva, confirma e entrega |
| [src/disparo/canais/](src/disparo/canais/) | Um módulo por meio de entrega — SMTP, API de WhatsApp e rascunho |
| [src/disparo/limites.py](src/disparo/limites.py) | Cota horária, disjuntor e teto por rodada — as defesas contra descontrole |
| [src/descobrir.py](src/descobrir.py) | Diagnóstico da tela e extração da lista de fornecedores — não faz parte da rodada |
