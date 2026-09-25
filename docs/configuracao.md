# Configuração

A configuração fica em dois arquivos:

| Arquivo | O que guarda | Versionado |
|---|---|---|
| `.env` | Credenciais, caminhos, travas de teste e limites. Muda por instalação | **não** |
| [fabricantes.yaml](../fabricantes.yaml) | Os laboratórios: códigos do Geweb, agenda, contatos e comprador | sim |

Os dois são lidos e validados por [src/config.py](../src/config.py) antes de qualquer
conexão.

## O arquivo .env

Crie a partir do modelo, que já traz um comentário por chave:

```powershell
copy .env.example .env
```

### Geweb e pastas

| Variável | Obrigatória | Padrão | Para que serve |
|---|---|---|---|
| `GEWEB_URL` | **sim** | | URL da tela de **login** (não a do menu) |
| `GEWEB_USUARIO` | **sim** | | Usuário do Geweb, de preferência um dedicado à automação |
| `GEWEB_SENHA` | **sim** | | Senha correspondente |
| `DOWNLOAD_DIR` | não | `downloads` | Passagem do arquivo bruto do Geweb. Só fica guardado se a formatação falhar |
| `FORMATADO_DIR` | não | `formatado` | Onde vai o `.xlsx` formatado, pronto para enviar, e a planilha de histórico |
| `HEADLESS` | não | `false` | `true` roda sem abrir janela |
| `TIMEOUT_MS` | não | `30000` | Timeout das ações de tela, em ms |
| `TIMEOUT_RELATORIO_MS` | não | `180000` | Timeout da geração do relatório, que demora bem mais |
| `SLOW_MO_MS` | não | `0` | Atraso artificial entre ações, para depurar (ex.: `300`) |

Faltando uma das três obrigatórias, a rodada sai com **código 2** antes de abrir o navegador.

> ⚠️ `HEADLESS` só reconhece `1`, `true`, `sim`, `yes` ou `y` como verdadeiro. Qualquer outro
> valor, inclusive `on` ou `verdadeiro`, é lido como `false`, sem aviso.

Caminhos relativos são resolvidos a partir da pasta do projeto. Também valem caminhos
absolutos (`D:\MapaEstoque`), de rede (`\\servidor\publico\mapas`) ou dentro de uma pasta
sincronizada (OneDrive, ownCloud). As duas pastas são independentes: como o bruto quase
nunca fica, o `DOWNLOAD_DIR` pode ser local e só o `FORMATADO_DIR` apontar para a rede.

> ⚠️ **Pasta de rede:** use o caminho UNC completo (`\\servidor\pasta`), **nunca a letra
> mapeada** (`Z:\pasta`). Unidades mapeadas só existem na sessão interativa do Windows; com a
> tarefa agendada rodando *"estando o usuário conectado ou não"*, o `Z:` não existe e a
> extração falha ao salvar. Confirme também que o usuário da tarefa tem permissão de escrita.

### Envio

| Variável | Obrigatória | Padrão | Para que serve |
|---|---|---|---|
| `COMPRADOR` | não | | Nome que assina a mensagem, para laboratório **sem** bloco `comprador` |
| `COMPRADOR_CARGO` | não | | Cargo na assinatura, mesmo critério |
| `COMPRADOR_TELEFONES` | não | | Telefones na assinatura, mesmo critério |
| `RESPONDER_PARA` | não | | `Reply-To` padrão, mesmo critério. Aceita vários, separados por vírgula |
| `REMETENTE` | não | | `From` da mensagem. Deixe vazio: a Locaweb exige que assine a própria caixa do `SMTP_USUARIO` |
| `DESTINATARIO_TESTE` | não | | **Trava de teste do e-mail.** Preenchido, todo e-mail vai para esses endereços e a `copia` é suprimida. Aceita vários, separados por vírgula |
| `TELEFONE_TESTE` | não | | **Trava de teste do WhatsApp**, independente da de e-mail |
| `ALERTA_PARA` | não | | Quem recebe o aviso de falha da rodada. Vazio não desliga: cai no `RESPONDER_PARA` e, na falta dele, na caixa que envia |
| `ENVIOS_DIR` | não | `envios` | Onde os rascunhos são gravados, só com `--rascunho` |

Hoje todo laboratório tem o próprio bloco `comprador`, então `COMPRADOR`, `COMPRADOR_CARGO`,
`COMPRADOR_TELEFONES` e `RESPONDER_PARA` só entram em uso se um laboratório for cadastrado
sem ele. Veja [O comprador](#o-comprador).

### SMTP e WhatsApp

| Variável | Obrigatória | Padrão | Para que serve |
|---|---|---|---|
| `SMTP_HOST` | para enviar | | Servidor de envio. Locaweb: `email-ssl.com.br` |
| `SMTP_PORTA` | não | `587` | `465` com `ssl`, `587` com `starttls` |
| `SMTP_SEGURANCA` | não | `starttls` | `starttls` ou `ssl` |
| `SMTP_USUARIO` / `SMTP_SENHA` | para enviar | | Caixa que envia, com o endereço **completo**. Sem elas o canal de e-mail é pulado |
| `WHATSAPP_PROVEDOR` | não | `zapi` | Perfil de API a usar |
| `ZAPI_URL_BASE` | não | `https://api.z-api.io` | Endereço da API |
| `ZAPI_INSTANCIA` / `ZAPI_TOKEN` / `ZAPI_CLIENT_TOKEN` | para enviar | | Credenciais. Sem elas o canal de WhatsApp é pulado |
| `INTERVALO_ENVIO_S` | não | `5` | Segundos entre laboratórios, para não parecer disparo em massa |

### Limites de segurança

| Variável | Padrão | Efeito |
|---|---|---|
| `MAX_ENVIOS_POR_RODADA` | `95` | Recusa a leva acima disso, antes de conectar. Pega cadastro duplicado |
| `MAX_ENVIOS_POR_HORA` | `90` | Cota por canal, abaixo do limite da Locaweb (100/h por caixa) |
| `MAX_FALHAS_SEGUIDAS` | `3` | Falhas seguidas que desligam um canal |
| `MAX_TENTATIVAS` | `3` | Tentativas por mensagem, só para erro temporário |
| `MAX_ANEXO_MB` | `10` | Recusa anexo acima disso |

O porquê de cada limite está em [envio.md](envio.md#proteções-contra-descontrole).

## O arquivo fabricantes.yaml

Uma entrada por relatório. O cabeçalho do próprio arquivo documenta cada campo, e a fonte do
cadastro é a planilha do comprador,
[docs/referencia/ENVIO MAPA.xlsx](referencia/ENVIO%20MAPA.xlsx).

Depois de qualquer edição, confira:

```powershell
.venv\Scripts\python -m pytest                              # valida o cadastro de produção
.venv\Scripts\python -m src.main --planejar                  # o plano de hoje
.venv\Scripts\python -m src.main --planejar --hoje 2026-09-01   # o plano de outra data
```

### Códigos do Geweb

Cada item tem um `nome` (vira pasta de saída e chave do registro de envios) e um ou mais
códigos do Geweb.

```yaml
- nome: BIOPAS               # um código só
  codigo: 106499

- nome: TORRENT              # dois códigos somados num arquivo
  codigos: [21411, 54843]
```

**Um laboratório pode ter vários códigos**, um por divisão ou centro de distribuição. O campo
Fabricante do Geweb aceita múltipla escolha, então todos entram no mesmo relatório.

Quem manda nisso é a planilha do comprador: os códigos unidos por `" - "` na coluna
`ID FABRICANTE` entram **juntos** no mesmo relatório. Códigos em linhas separadas viram
**arquivos separados**, mesmo quando o nome é igual.

> ⚠️ O `nome` precisa ser único. Ele chaveia a pasta, o `estado.json` e a numeração: dois
> laboratórios com o mesmo nome sobrescreveriam o registro um do outro. Por isso existem
> sufixos como `_GENERICOS`, `_RX` e `_OTC`.

A lista completa de fornecedores do Geweb, no formato `(codigo) NOME`, fica em
`logs\fabricantes-geweb.txt`. Para atualizá-la:

```powershell
.venv\Scripts\python -m src.descobrir --fabricantes
```

### Agenda de envio

Cada laboratório pode receber dois envios independentes:

| Campo | Quando dispara | Período que o relatório cobre |
|---|---|---|
| `mensal: true` (padrão) | **1º dia útil do mês**, ou na primeira rodada seguinte se aquele dia for perdido | o mês anterior inteiro (`2026-07`) |
| `dias_semana: [segunda, quarta]` | nesses dias da semana | do **dia 1º do mês corrente até ontem** (`2026-08-01_a_2026-08-04`) |

```yaml
- nome: BIOPAS            # só o mensal
  codigo: 106499

- nome: MARJAN            # mensal + dois envios por semana
  codigo: 7127
  dias_semana: [segunda, quarta]
```

Outros campos:

| Campo | Efeito |
|---|---|
| `ativo: false` | Pula o laboratório sem tirá-lo do arquivo. É assim que se desliga um envio |
| `mensal: false` | Só o semanal. **Exige `dias_semana`**; sem ele o laboratório não teria envio nenhum e fica de fora |
| `janela_semanal: semana_fechada` | O semanal passa a cobrir **segunda a sexta** da última semana encerrada, em vez do acumulado do mês |

`dias_semana` aceita **apenas segunda a sexta**; sábado ou domingo tira o laboratório da
rodada. A grafia é livre (`TERÇA-FEIRA`, `Terça` e `terca` são o mesmo dia) e o dia repetido
é ignorado.

Como a agenda decide cada dia, inclusive início de mês, feriados e a recuperação do mensal,
está em [operacao.md](operacao.md#a-agenda).

### Contatos

O bloco `contatos` diz para quem e por qual canal o mapa vai:

```yaml
  - nome: EUROFARMA
    codigo: 14232
    contatos: &eurofarma          # âncora: a outra entrada do grupo reaproveita
      emails: [mapa.estoque@industria.com.br]
      copia: [comprador@sogamax.com.br]
      whatsapp: ["+5511999999999"]
      canais: [email, whatsapp]   # um, outro, ou os dois
      whatsapp_anexo: true        # manda a planilha no WhatsApp também

  - nome: EUROFARMA_RX
    codigo: 13963
    contatos: *eurofarma          # mesmo destinatário, sem duplicar o dado
```

| Campo | Efeito |
|---|---|
| `emails` | destinatários do e-mail |
| `copia` | vai em cópia no e-mail, no momento do envio |
| `whatsapp` | telefones, em formato internacional (`+5511999999999`) |
| `canais` | por onde este laboratório recebe: `[email]` (padrão), `[whatsapp]` ou os dois |
| `whatsapp_anexo` | `true` manda o `.xlsx` pelo WhatsApp; `false` (padrão) só avisa que foi por e-mail |

Quem não tiver contato **continua sendo extraído normalmente**: só não entra no envio, e
aparece nominalmente no resumo.

Alguns contatos atendem mais de um laboratório do mesmo grupo econômico (as duas Brace
Pharma, GERMED e LEGRAND; EMS_RX e LAFIMAN; BLAU e BERGAMO; as duas entradas da CELLERA). O
`--dry-run` avisa quem recebe mais de uma mensagem na mesma leva.

### O comprador

O bloco `comprador` decide quem **assina** a mensagem, quem **recebe a resposta** da
indústria e em qual **pasta** o relatório é gravado:

```yaml
  - nome: ACHE
    codigos: [106975, 106976]
    comprador: &maria                       # âncora, como a de contatos
      nome: Maria Silva
      cargo: Compras
      telefones: 0800 000 0000 / (22) 99999-0000
      responder_para: maria@sogamax.com.br

  - nome: BIOSINTETICA_RX
    codigos: [9030, 42818]
    comprador: *maria
```

| Campo | Obrigatório | Efeito |
|---|---|---|
| `nome` | **sim** | Assina a mensagem (`{COMPRADOR}` no template) e nomeia a pasta de saída |
| `responder_para` | não | Vira o `Reply-To`: a resposta da indústria vai para cá. Aceita vários, separados por vírgula |
| `cargo`, `telefones` | não | Completam a assinatura |

Cada campo ausente cai no valor do `.env` sozinho, então um bloco que só define o `nome`
continua herdando cargo e telefones do padrão. Sem bloco nenhum, vale tudo do `.env`.
Um `comprador` sem `nome` tira o laboratório da rodada, em vez de mandar um mapa sem
assinatura.

**Um laboratório com dois compradores.** O `nome` é texto livre e o `responder_para` aceita
vários endereços:

```yaml
    comprador:
      nome: Maria Silva e João Souza
      responder_para: maria@sogamax.com.br, joao@sogamax.com.br
```

`responder_para` e `copia` resolvem coisas diferentes, e o segundo comprador provavelmente
quer as duas:

| Campo | Onde fica | O que a pessoa recebe |
|---|---|---|
| `responder_para` | bloco `comprador` | só a **resposta** da indústria, se ela responder |
| `copia` | bloco `contatos` | o **mapa enviado**, no mesmo momento em que a indústria recebe |

> Um mesmo contato pode receber mapas de compradores diferentes. Hoje acontece com a Merck:
> MERCK_RX e MERCK_GENERICOS são de compradoras diferentes, e o contato recebe duas mensagens
> assinadas por pessoas distintas. É proposital, mas as duas compradoras precisam saber.

### Âncoras YAML

`&nome` define um bloco e `*nome` o reaproveita, para não repetir o mesmo contato ou o mesmo
comprador em várias entradas.

> ⚠️ A âncora precisa ser **definida antes de ser usada**, na ordem do arquivo. Invertido, o
> YAML falha com *"found undefined alias"* e a rodada sai com código 2.

### Validação

O cadastro é conferido no carregamento, antes de qualquer conexão:

- e-mail precisa de `@`; telefone precisa estar no formato internacional;
- canal desconhecido, dia da semana inválido ou `mensal: false` sem `dias_semana` são erro.

**Um erro de cadastro não derruba a rodada inteira.** O laboratório com problema fica de fora,
com `CADASTRO IGNORADO` no log e um e-mail para o `ALERTA_PARA`; os demais rodam normalmente.
A rodada só para com código 2 se o YAML estiver ilegível ou se **nenhum** laboratório sobrar
válido.
