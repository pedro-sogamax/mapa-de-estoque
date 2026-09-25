# Envio às indústrias

Como os mapas chegam às indústrias: o comando de envio, as travas de teste, as proteções
contra excesso, a configuração de e-mail e WhatsApp e o texto das mensagens. O desenho e as
decisões por trás do envio estão em [disparo.md](disparo.md).

## O comando

```powershell
.venv\Scripts\python -m src.disparo --dry-run    # mostra tudo, não envia nada
.venv\Scripts\python -m src.disparo              # mostra, pergunta e envia
```

Envia **de verdade** o que a última extração gerou, por e-mail, WhatsApp ou os dois, conforme
o cadastro de cada laboratório. Antes, mostra o plano e pede confirmação:

```
4 mensagem(ns) a enviar — periodo 01/08/2026 a 16/08/2026
TESTE   email     tudo vai para teste@sogamax.com.br
REAL    whatsapp  vai para as INDUSTRIAS

  DIFFUCAP           email     estoque@industria-a.com.br
  MARJAN             email     suprimentos@industria-b.com.br
  MARJAN             whatsapp  +5511988887777  (com anexo)
  SANOFI_MEDLEY      whatsapp  +5511977776666

Enviar 4 mensagem(ns) — whatsapp vai para as INDUSTRIAS?
Digite SIM para confirmar: _
```

O aviso é **por canal**: cada trava protege um canal só, e o comando diz qual está protegido e
qual vai para fora.

### Opções

| Opção | Efeito |
|---|---|
| *(nenhuma)* | envia o que a última extração gerou |
| `--dry-run` | mostra o plano completo e sai, sem abrir conexão |
| `--sim` | não pergunta antes de enviar |
| `--periodo 2026-07` | envia uma leva antiga, varrendo o `FORMATADO_DIR` |
| `--fabricante MARJAN` | só um laboratório |
| `--comprador "Maria Silva"` | só a carteira desses compradores; aceita vários, separados por vírgula |
| `--canal email` / `--canal whatsapp` | só um canal |
| `--refazer` | reenvia o que já foi enviado (combine com `--fabricante`) |
| `--rascunho` | **não envia**: grava os `.eml` e a página `wa.me` para envio manual |
| `--forcar` | libera o teto de mensagens por rodada |

Códigos de saída: `0` tudo entregue, `2` erro de configuração, **`3` algum envio falhou**.
O `3` é distinto do `1` da extração, para o log separar "não gerei" de "gerei e não entreguei".

## Enviar automaticamente ao fim da extração

```powershell
.venv\Scripts\python -m src.main --enviar
```

Com `--enviar`, a extração termina e chama o disparo na sequência, o equivalente a
`python -m src.disparo --canal email --sim`. É o que o [executar.bat](../executar.bat) e,
portanto, a tarefa agendada fazem.

Três limites deliberados:

- **Só o canal de e-mail.** O WhatsApp continua exclusivo do comando manual: um canal que pode
  ter o número banido não entra numa tarefa agendada.
- **É opt-in.** Sem a flag, `python -m src.main` só extrai. Rodar a extração à mão nunca envia
  nada.
- **Roda em processo separado**, para o disparo manter o próprio `logs\disparo.log` e o próprio
  código de saída.

O `--enviar` dispensa **uma** proteção: a confirmação `SIM`. Todas as outras continuam
valendo, e são elas que sustentam o modo automático: o registro de envios, o teto por rodada,
a cota horária, o disjuntor e a trava `DESTINATARIO_TESTE`. No modo agendado, ninguém está
olhando na hora.

Se a extração não gerar arquivo nenhum, o disparo **não** é chamado; sem isso ele releria o
manifesto da rodada anterior. Laboratório que falhou na extração não vira mensagem.

## As travas contra engano

1. **A confirmação.** Nada sai antes de você digitar `SIM`. `--sim` pula, para quando já
   conferiu no `--dry-run`.
2. **`DESTINATARIO_TESTE` e `TELEFONE_TESTE`** no `.env`. Preenchidos, todo o canal vai para
   esses destinos e nenhuma indústria é tocada. São **independentes**: preencher só um deixa o
   outro canal enviando de verdade, e por isso o cabeçalho marca `TESTE` ou `REAL` por canal.

   O `DESTINATARIO_TESTE` aceita **mais de um endereço**, separados por vírgula:

   ```ini
   DESTINATARIO_TESTE=teste@sogamax.com.br, comprador@sogamax.com.br
   ```

   Assim um comprador acompanha a homologação vendo exatamente o que a indústria veria, sem
   desligar a trava. Com a trava ligada, a `copia` de cada laboratório é **suprimida**:
   ninguém de fora entra na mensagem por nenhuma via.

   A trava **não** muda o `responder_para`. Ela protege quem *recebe* o mapa; a resposta ir
   para o comprador certo é justamente o que se quer conferir antes de liberar.
3. **O registro de envios** (`dados\envios.json`). O que já foi entregue não é reenviado. O
   registro é gravado **a cada mensagem**, não no fim: se o comando morrer na décima mensagem,
   as nove que saíram ficam registradas. `--refazer` ignora o registro, de propósito.

> ⚠️ O cadastro tem os endereços reais das indústrias. A única coisa entre o sistema e elas é
> o `DESTINATARIO_TESTE`: esvaziá-lo libera o envio real. Confira sempre com `--dry-run`.

## Proteções contra descontrole

As travas acima protegem contra engano humano. Estas protegem contra o **sistema disparando
além do razoável**, que é o que faz um provedor suspender a conta de e-mail da empresa.

| Proteção | Padrão | O que ela impede |
|---|---|---|
| **Teto por rodada** | 95 | Um cadastro duplicado ou um manifesto errado virar centenas de mensagens. Recusa **antes de conectar**, com código 2. `--forcar` libera |
| **Cota por hora** | 90/canal | Estourar o limite da Locaweb (100/h por caixa). Ao atingir, para e diz a partir de que hora continuar |
| **Disjuntor** | 3 falhas | Insistir com um servidor que já está recusando tudo. Desliga aquele canal; os outros seguem |
| **Retentativa** | 3 tentativas | Perder um envio por instabilidade passageira, mas **só** repete erro temporário |
| **Anexo grande** | 10 MB | Anexar o arquivo errado |

Todas anunciam o motivo quando agem, e o que não saiu aparece no resumo como *"não tentado —
fica para a próxima rodada"*.

**O que é temporário e o que não é.** Erro `4xx` do SMTP (caixa cheia, servidor ocupado,
greylist) e queda de conexão são transitórios: até duas retentativas, esperando 5 s e 15 s,
com a conexão reaberta. Erro `5xx` e destinatário inexistente são definitivos: falham na hora,
porque repetir só gasta a reputação do remetente.

**Credencial recusada é caso à parte:** uma tentativa e a leva inteira para, com código 3.
Repetir login com senha errada é o caminho mais curto para o provedor bloquear a conta.

> ⚠️ **A margem da cota é pequena.** A segunda-feira envia uma mensagem por laboratório ativo,
> e uma segunda que também recupere um mensal atrasado soma as duas levas: perto de 90, o
> limite da cota. Mais laboratórios ou mais compradores exigem uma caixa SMTP por comprador,
> cada uma com a própria cota.

**Auditoria.** Cada mensagem que sai é registrada em `logs\envios.jsonl`, uma linha por envio,
só acrescentando:

```json
{"em": "2026-08-24T07:12:33", "canal": "email", "fabricante": "MARJAN", "id": "<...@sogamax.com.br>"}
```

É o que alimenta a cota horária e o registro do que **realmente** saiu. O `envios.json` guarda
só o último envio de cada laboratório, então um `--refazer` apagaria o rastro do anterior.

O `--dry-run` mostra tudo isso antes de qualquer conexão:

```
  ATENCAO: mapa@industria.com.br recebe 2 e-mails nesta leva (EUROFARMA, EUROFARMA_RX)

  cota email     0 de 90 usados na ultima hora; cabem mais 90, a leva pede 46
  teto por rodada: 95 mensagens
```

O aviso de endereço repetido não bloqueia: são relatórios diferentes, e mandar separado pode
ser o certo. Mas quem digita `SIM` precisa saber que aquela pessoa vai receber duas mensagens.

## Configurar o e-mail

O domínio da Sogamax é hospedado na **Locaweb**, com SMTP autenticado. No `.env`:

```ini
SMTP_HOST=email-ssl.com.br
SMTP_PORTA=465
SMTP_SEGURANCA=ssl
SMTP_USUARIO=mapa@sogamax.com.br     # endereço COMPLETO, com @
SMTP_SENHA=...                       # a senha da própria caixa
```

Vale usar uma **caixa dedicada** em vez da pessoal de um comprador. As respostas vão para o
comprador de cada laboratório pelo `responder_para` (veja
[configuracao.md](configuracao.md#o-comprador)).

> ⚠️ A Locaweb exige que **quem assina seja a conta que autenticou**. Deixe `REMETENTE` vazio
> (o padrão usa o próprio `SMTP_USUARIO`); preenchê-lo com outro endereço faz o servidor
> recusar cada mensagem com *503 Client host rejected*. Para direcionar as respostas, use o
> `responder_para`, que não tem essa restrição.

Uma conexão serve a leva inteira.

## Configurar o WhatsApp

Depende de contratar um provedor de API não oficial. Enquanto `ZAPI_INSTANCIA` e `ZAPI_TOKEN`
estiverem vazios, o canal é **pulado com aviso** e o e-mail funciona sozinho.

```ini
WHATSAPP_PROVEDOR=zapi
ZAPI_URL_BASE=https://api.z-api.io
ZAPI_INSTANCIA=...
ZAPI_TOKEN=...
ZAPI_CLIENT_TOKEN=...
INTERVALO_ENVIO_S=5
```

> ⚠️ **API não oficial contraria os termos de uso da Meta.** O número pode ser banido sem aviso
> e sem recurso. Use um **número dedicado**, nunca o pessoal de um comprador nem o principal da
> empresa. A sessão também cai sozinha (troca de aparelho, atualização, inatividade) e só volta
> com QR Code presencial; quando isso acontece o comando falha com o motivo, e os e-mails saem
> assim mesmo.

`INTERVALO_ENVIO_S` espaça as mensagens: disparar dezenas iguais em rajada é exatamente o
padrão que faz um número ser banido.

As rotas ficam em [whatsapp_api.py](../src/disparo/canais/whatsapp_api.py), numa tabela de
perfis. O perfil `zapi` está pronto; **outro provedor exige um perfil próprio**, conferido na
documentação oficial dele, porque os nomes dos campos divergem entre provedores.

## O texto das mensagens

Fica em [templates/](../templates/), fora do código, para ser ajustado sem mexer em Python:

| Arquivo | Papel |
|---|---|
| `email.txt` | assunto (**1ª linha**) e o corpo em texto puro |
| `email.html` | o mesmo corpo em HTML, com a assinatura da Sogamax |
| `whatsapp.txt` | a mensagem do WhatsApp |
| `assinatura/` | logo e ícones das redes, embutidos na mensagem |

Variáveis: `{FABRICANTE}`, `{PERIODO}`, `{COMPRADOR}`, `{CARGO}`, `{TELEFONES}`,
`{EMAIL_COMPRADOR}`, `{DATA}` e, só no WhatsApp, `{EMAILS}`.

**Toda mensagem sai nas duas versões** (`multipart/alternative`): quem renderiza HTML vê a
assinatura completa; quem não renderiza (cliente antigo, leitor de tela, filtro corporativo)
lê o texto puro, com a mesma informação. O `email.html` é opcional: apagá-lo faz a mensagem
sair só em texto.

### A assinatura

Reproduz a assinatura oficial do Outlook: logo à esquerda, barra `#0099CC`, Verdana 9pt,
rótulos em ciano e o endereço da empresa. Nome, cargo, telefones e e-mail vêm do comprador do
laboratório: **o formato é padronizado e o conteúdo é de quem assina**.

As imagens são **embutidas na mensagem** (`cid:`), nunca baixadas de um servidor. A assinatura
aparece sem o destinatário clicar em "baixar imagens", e uma imagem remota num e-mail
automático é lida por filtros como pixel de rastreamento.

Para trocar a marca, troque os arquivos em `templates/assinatura/`. O código só conhece as
imagens listadas na tabela `IMAGENS_ASSINATURA`, em [src/disparo/eml.py](../src/disparo/eml.py).

## Quando um provedor cair

`--rascunho` volta ao modo de preparação: grava um `.eml` por laboratório, que o Outlook abre
pronto com anexo, e uma página com links `wa.me`. Serve para entregar o mapa no mesmo dia sem
depender de SMTP nem de API.

O rascunho **não** marca nada como entregue: montar um arquivo não é entregar, e registrar
bloquearia o envio de verdade depois. O link `wa.me` também não carrega arquivo, então
laboratórios com `whatsapp_anexo: true` são avisados no resumo.
