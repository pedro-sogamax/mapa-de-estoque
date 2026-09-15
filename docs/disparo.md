# Disparo do Mapa de Estoque — e-mail e WhatsApp

Desenho do passo **6** do procedimento ([mapa.md](mapa.md)): entregar o arquivo à indústria.

> ## O que já está feito
>
> `python -m src.disparo` ([src/disparo/](../src/disparo/)) **envia de verdade**, por e-mail
> (SMTP) e por WhatsApp (API não oficial), conforme o `canais` de cada laboratório. Pergunta
> antes (digite `SIM`), grava o `envios.json` a cada mensagem e sai com código 3 se algum
> envio falhar. O passo a passo está no [README](../README.md#5-enviar-às-indústrias).
>
> Isso implementa as §2 (camada de canais), §3 (cadastro), §4 (gatilho, idempotência, falha
> isolada, código de saída próprio), §5 (conteúdo e anexo) e §8 (modos de teste).
>
> **O que continua em aberto**: a contratação do provedor de WhatsApp (§7) e a liberação do
> envio real — os destinatários (§3) e as credenciais de SMTP já estão cadastrados, e a trava
> `DESTINATARIO_TESTE` é o que segura tudo até a conferência com o comprador terminar. A
> aplicação de e-mail da empresa (§6) deixou de ser caminho crítico — o SMTP da Locaweb
> resolveu sem ela; o questionário fica registrado caso um dia se queira migrar.

---

## 1. Situação atual

O script cobre os passos 1 a 6: extrai, formata e entrega. O disparo tem duas formas: o
comando `python -m src.disparo`, acionado a mão, que é o único caminho do WhatsApp; e o
`src.main --enviar`, que encadeia **só o e-mail** ao fim da extração e é o que a tarefa
agendada usa.

O modo a mão veio primeiro, de propósito: mandar mapa para 24 indústrias sem ninguém olhar
era risco que ninguém tinha pedido para correr. O `--enviar` assume esse risco de forma
consciente e delimitada — um canal só, e todas as defesas da §4 e das cotas de pé; o que ele
dispensa é a confirmação `SIM`, não as proteções.

O que **já existe** e será reaproveitado:

| Peça | Onde | Para que serve no disparo |
|---|---|---|
| `Resultado` | [src/main.py:49-65](../src/main.py#L49-L65) | já carrega `fabricante`, `motivo`, `periodo`, `arquivo`, `formatado`, `erro` e `aviso` — é tudo que o envio precisa |
| Fim da extração | [src/main.py:294](../src/main.py#L294) | ponto exato onde o disparo entra, antes do resumo |
| `EstadoDaAgenda` | [src/estado.py](../src/estado.py) | padrão de registro idempotente com gravação atômica, a ser copiado para os envios |
| Cadastro por laboratório | [fabricantes.yaml](../fabricantes.yaml) | onde os contatos vão morar (§3) |

**Os destinatários existem desde 26/08/2026.** A planilha `Fabricantes atualizado.xlsx`
acrescentou a coluna `E-MAIL`, e os 24 laboratórios foram cadastrados no `fabricantes.yaml`
(um e-mail cada, cópia para o Pedro e o YURI, canal e-mail). Em 27/08/2026 a SANOFI_MEDLEY foi
desligada com `ativo: false` (parceria encerrada), deixando **23 ativos**. A planilha antiga
`FABRICANTES ENVIO MAPA.xlsx` — só FABRICANTE, ID, COMPRADOR e dias da semana — ficou obsoleta.
As credenciais de SMTP também já estão no `.env`.

O que ainda **não existe**: telefone de ninguém, e a contratação do provedor de WhatsApp. O
canal continua pulado com aviso, e o e-mail funciona sozinho.

Com o cadastro real no arquivo, a proteção deixou de ser dupla: hoje a única coisa que impede
um mapa de chegar à indústria é a trava `DESTINATARIO_TESTE` (§8). Enquanto ela estiver
preenchida, todo envio vai para as caixas internas.

---

## 2. Arquitetura proposta

Uma camada de canais desacoplada, para que trocar de provedor seja trocar um adaptador:

```
  agenda -> extração -> list[Resultado]
                              |
                  src/disparo/__main__.py
             (para cada Resultado com arquivo, decide
              quem recebe, por qual canal, e registra)
                              |
        +---------------------+---------------------+
        |                     |                     |
   canal E-MAIL         canal WHATSAPP        canal RASCUNHO
   (SMTP da Locaweb)    (API nao oficial)    (.eml + link wa.me)
        |                     |                     |
        +---------------------+---------------------+
                              |
                        envios.json  (o que já foi entregue)
```

Contrato único entre o roteador e os canais:

```python
class Canal(Protocol):
    nome: str
    def enviar(self, destino: Destino, mensagem: Mensagem, anexo: Path | None) -> Envio: ...
```

Três decisões que sustentam o desenho:

1. **O canal não sabe de agenda nem de Geweb.** Recebe destino, texto e caminho do anexo.
2. **O roteador não sabe de SMTP nem de HTTP.** Decide o quê, para quem e se já foi enviado.
3. **O canal Rascunho é contingência permanente.** Gera um `.eml` pronto para abrir no Outlook
   e um texto com link `wa.me` por laboratório, sem enviar nada. Foi o primeiro modo a existir,
   e continua em `--rascunho`: quando o SMTP recusar ou a sessão do WhatsApp cair, o mapa ainda
   sai no mesmo dia.

Layout implementado:

```
src/disparo/
    __main__.py       # o comando: monta o plano, confirma, orquestra o envio
    selecao.py        # o que entra: manifesto da ultima rodada ou --periodo
    mensagem.py       # aplica os templates ao relatorio extraido
    registro.py       # envios.json (espelha src/estado.py)
    eml.py            # monta a EmailMessage; grava .eml no modo rascunho
    whatsapp.py       # pagina de links wa.me, do modo rascunho
    canais/
        base.py       # Protocol Canal, Destino, Mensagem, Envio, FalhaNoEnvio
        email_smtp.py # SMTP autenticado
        whatsapp_api.py  # API nao oficial, por perfil de provedor
        rascunho.py   # contingencia: grava em disco em vez de enviar
```

---

## 3. Cadastro de destinatários

**Recomendação: no próprio [fabricantes.yaml](../fabricantes.yaml)**, com um bloco `contatos`.

```yaml
  - nome: EUROFARMA_RX
    codigo: 13963
    dias_semana: [segunda]
    contatos: &eurofarma          # âncora: reaproveitada pela outra entrada do grupo
      emails: [mapa.estoque@eurofarma.com.br]
      copia: [yuri@sogamax.com.br]
      whatsapp: ["+5511999999999"]
      canais: [email]             # email | whatsapp | os dois
      whatsapp_anexo: false       # true manda a planilha pelo WhatsApp tambem

  - nome: EUROFARMA
    codigo: 14232
    contatos: *eurofarma          # mesmo destinatário, sem duplicar o dado
```

Por quê aqui:

- É a fonte de verdade **já existente** por laboratório — o dia de envio e o destinatário são a
  mesma decisão de negócio e devem ficar juntos.
- A validação estruturada já está pronta em [src/config.py:127-203](../src/config.py#L127-L203),
  com mensagens de erro claras; estender o `Fabricante` com `contatos` é acrescentar campos ao
  que já existe, não criar um segundo mecanismo.
- As **âncoras YAML** (`&nome` / `*nome`, suportadas nativamente pelo PyYAML) resolvem os casos
  em que o mesmo laboratório aparece em mais de uma entrada (EUROFARMA/EUROFARMA_RX,
  EMS_BRACE_PHARMA_*, ACHE/BIOSINTETICA) sem duplicar contato.

Alternativas descartadas: um `contatos.yaml` separado cria duas listas para manter em sincronia
pelo nome do fabricante; ler direto da planilha `.xlsx` do comprador acopla o cadastro a um
arquivo que ninguém versiona, para um dado que muda pouco (o `openpyxl` já é dependência do
projeto por causa do formatador, então esse argumento caiu — o outro continua de pé).

Regras de validação, já implementadas em [src/config.py](../src/config.py):

- `emails` vazio **e** `whatsapp` vazio ⇒ o laboratório entra na rodada de extração normalmente,
  mas o disparo o pula com aviso nominal no resumo (nunca em silêncio).
- `canais` ausente ⇒ assume `[email]`; canal desconhecido ⇒ erro de configuração.
- Telefone sempre em **E.164** (`+55DDNNNNNNNNN`), conferido no carregamento — o link `wa.me`
  só funciona nesse formato, e o erro apareceria tarde, na hora de clicar.
- E-mail sem `@` ⇒ erro de configuração, apontando o laboratório.

### De onde tirar os contatos reais

Este é o levantamento que precede tudo. Na ordem de confiabilidade:

1. **Histórico de e-mails enviados pelo comprador** — é o dado real, já em uso, com o endereço
   que a indústria de fato lê. Extrair remetentes/destinatários dos envios dos últimos meses.
2. **Confirmação com cada indústria** — sobretudo para pedir um endereço de setor
   (`mapa@`, `estoque@`) em vez do e-mail pessoal de um contato, que rotaciona.
3. **Contratos/cadastro comercial** como conferência.

Vale registrar, junto ao contato, **em que formato cada indústria espera receber** — algumas
pedem o arquivo dentro do corpo, outras têm portal próprio.

---

## 4. Regras de disparo

**Gatilho.** Só dispara para `Resultado` com `formatado` ou `arquivo` preenchido — o bruto é
descartado quando o formatado sai, então no caso normal só o `formatado` existe. Laboratório que falhou na
extração não gera mensagem nenhuma — o erro aparece no resumo e a rodada do dia seguinte
tenta de novo, como já acontece hoje. O anexo é o `formatado`, caindo para o `arquivo` bruto
quando a formatação falhou (§5).

Caso especial: `RelatorioSemDados` ([src/main.py:120-129](../src/main.py#L120-L129)) não gera
arquivo, mas é um desfecho legítimo (não houve movimento no período). **Decisão pendente com o
comprador**: avisar a indústria de que não houve movimento, ou silenciar? No código o mensal é
marcado como entregue nesse caso — mas a detecção ainda está inativa (`MENSAGEM_SEM_DADOS = None`
em [src/geweb/seletores.py](../src/geweb/seletores.py)), então hoje isso vira falha genérica.

**Idempotência.** Um `envios.json` novo, espelhando [src/estado.py](../src/estado.py) (gravação
em temporário + `os.replace`). Sem isso, a recuperação automática do mensal — que reexecuta
quando a máquina ficou desligada no 1º dia útil — reenviaria e-mails já enviados. Chave do
registro: `fabricante + periodo.rotulo + canal`.

```json
{
  "enviados": {
    "EUROFARMA_RX|2026-07|email": {"em": "2026-08-01T07:12:33", "id": "<...@sogamax.com.br>"},
    "MARJAN|2026-07-27_a_2026-07-31|whatsapp": {"em": "2026-08-03T07:11:02", "id": "D241X...B68"}
  }
}
```

Gravado **a cada mensagem**, não ao fim da leva: uma queda na décima de vinte e quatro não pode
fazer as nove primeiras saírem de novo. E, ao contrário do `estado.json`, um `envios.json`
ilegível **interrompe** a leva em vez de seguir em frente — perder este registro custaria
reenvio para a indústria.

**Reenvio.** Nunca automático. Só com `--refazer` — combine com `--fabricante` para limitar o
alvo. Vale também para o `--dry-run`, que mostra o que seria reenviado.

**Falha de envio.** Não invalida o download nem interrompe os demais laboratórios — mesma
política de falha isolada já usada em `extrair_todos()`. O código de saída **`3`**, distinto do
`1` de falha de extração, separa "não consegui gerar" de "gerei mas não entreguei".

**Janela de horário.** Quem roda a mão escolhe a hora. Na tarefa agendada, a janela é a da
extração — hoje 07:00 em dia útil (README §6), com os e-mails saindo logo em seguida, na
mesma rodada.

**Envio encadeado (`--enviar`).** Depois de gravar o manifesto e imprimir o resumo,
[src/main.py](../src/main.py) chama `python -m src.disparo --canal email --sim` num processo
separado, e devolve o código de saída dele. Três garantias no desenho:

- **Só o canal e-mail.** O WhatsApp exige decisão humana e não tem trava de teste preenchida.
- **Opt-in.** Sem a flag, a extração não envia nada — a promessa original continua verdadeira
  para quem roda `python -m src.main` a mão.
- **Não chama o disparo se nada foi extraído**, senão ele releria o manifesto anterior.

O processo separado não é detalhe de implementação: chamado dentro do mesmo processo, o
`logging.basicConfig` já consumido pela extração jogaria o log do disparo dentro do
`execucao.log` e deixaria o `disparo.log` mudo.

---

## 5. Conteúdo da mensagem

Variáveis disponíveis a partir do `Resultado`: `fabricante`, `periodo` (rótulo `2026-07` ou
`2026-07-27_a_2026-07-31`), `motivo` (`mensal` / `semanal-segunda` / manual) e a data da
extração.

Esboço a validar com o comprador:

> **Assunto:** Mapa de Estoque — Sogamax — {FABRICANTE} — {PERÍODO}
>
> Prezados,
> Segue em anexo o mapa de estoque referente ao período {PERÍODO}.
> Qualquer divergência, favor responder este e-mail.
> Atenciosamente, {COMPRADOR} — Sogamax

Duas regras que evitam problema:

- **Responder-para** deve apontar para a caixa do comprador, mesmo que o remetente técnico seja
  outro. A indústria responde ao mapa com frequência, e o conteúdo dessas respostas é
  divergência de estoque — cair numa caixa que ninguém acompanha é perder o retorno útil do
  mapa em silêncio. Implementado: `RESPONDER_PARA` no `.env` vira o header `Reply-To`, e o
  `REMETENTE` **não** pode ser mudado (a Locaweb exige que assine quem autenticou).
- O texto vive em template versionado, não embutido no código, para o comprador poder ajustar.

**Assinatura (27/08/2026).** A mensagem passou a sair em duas versões na mesma entrega
(`multipart/alternative`): texto puro e HTML com a assinatura oficial da Sogamax — logo, dados
do comprador e ícones das redes. A estrutura MIME final é
`mixed( alternative( plain, related(html + imagens) ), anexo )`.

Duas decisões:

- **Imagens embutidas (`cid:`), não remotas.** Aparecem sem o destinatário precisar autorizar o
  download, e uma imagem remota num e-mail automático é exatamente o que filtros classificam
  como pixel de rastreamento. É o mesmo mecanismo da assinatura do Outlook.
- **O texto puro continua existindo.** Não é fallback decorativo: é o que um filtro corporativo,
  um cliente antigo ou um leitor de tela vai mostrar, e ele carrega a mesma informação.

Os dados de quem assina (nome, cargo, telefones, e-mail) vêm do comprador do laboratório, com o
`.env` como padrão — o formato é padronizado, o conteúdo é de quem assina.

### O formato do anexo — resolvido

Era um problema conhecido: o Geweb entrega um `.xls` que **é HTML renomeado**
([src/geweb/relatorio_page.py:187-190](../src/geweb/relatorio_page.py#L187-L190)), e filtros
corporativos tratam HTML renomeado como suspeito — risco de quarentena silenciosa.

Isso já não vale. [src/formatador.py](../src/formatador.py) converte cada relatório num
`.xlsx` binário de verdade, formatado, em `formatado\`. **O anexo do envio é esse arquivo** —
`Resultado.formatado`, não `Resultado.arquivo`.

Dois detalhes para o adaptador de envio:

- `formatado` pode vir `None` se a conversão falhar (o campo `aviso` diz por quê). Só nesse
  caso o `.xls` bruto é guardado, em `arquivo`, e serve de reserva — é exatamente o que a
  indústria recebe hoje e aceita. Com a conversão bem-sucedida o bruto é apagado e `arquivo`
  vem `None`.
- PDF continua fora de cogitação: a indústria manipula os números do mapa.

---

## 6. Canal e-mail — o que precisa ser levantado

A aplicação terceira que já dispara e-mail é a primeira opção, por não exigir nada novo da TI.
Perguntas a responder **antes** de escrever o adaptador:

**Integração**
1. Ela expõe **API HTTP** (REST/webhook) ou só interface web/agendamento interno?
2. Se tem API: URL base, forma de autenticação (token? usuário/senha?), formato do corpo.
3. Dá para chamar de uma máquina Windows na rede interna, ou só de servidor?

**Capacidade**
4. Aceita **anexo**? De que tamanho máximo? (O anexo é `.xlsx`; os relatórios ficam bem abaixo
   de 1 MB.)
5. Aceita destinatários variáveis por chamada, ou trabalha com listas pré-cadastradas?
6. Aceita corpo em HTML e campo *responder-para*?

**Operação**
7. Qual remetente a indústria enxerga? O domínio tem SPF/DKIM configurado?
8. Existe **log de entrega** consultável (enviado / recusado / bounce)?
9. Há limite diário de envios? (o pico é o 1º dia útil, com 24 mensagens)
10. Quem administra e quem avisa quando ela cair?

Se a resposta a (1) ou (4) inviabilizar, as contingências, em ordem de esforço:

| Opção | Esforço | Observação |
|---|---|---|
| SMTP autenticado do Microsoft 365 | baixo | `smtplib` na biblioteca padrão; exige senha de app / SMTP AUTH liberado no tenant; sai da caixa configurada |
| Microsoft Graph API (OAuth) | médio | sem senha no `.env`, auditável; exige app registrada no Entra ID e consentimento do admin |
| Serviço transacional (Resend/SendGrid) | médio | melhor entregabilidade e logs; exige verificar o domínio no DNS; remetente não é a caixa do comprador |

---

## 7. Canal WhatsApp — API não oficial (Uzapi)

**Modelo de integração** (padrão comum a Uzapi, Z-API e similares):

- Um **número dedicado** é pareado por **QR Code** e a sessão fica mantida no servidor do
  provedor.
- As chamadas são HTTP com identificação de sessão + token nos headers.
- Há endpoints de envio de texto e de envio de arquivo (por URL pública ou base64) e um
  **webhook** de status (mensagem enviada, sessão caiu, QR Code expirado).

> **A confirmar antes de implementar**: as rotas exatas, os nomes dos campos e o formato do
> anexo devem ser lidos na coleção Postman oficial da Uzapi
> (<https://documenter.getpostman.com/view/131526/U16hsmcg>) — a página é renderizada por
> JavaScript e não foi possível extrair os campos com segurança para este documento. Não
> implementar por analogia com outro provedor.

**Riscos, registrados de propósito:**

1. **É solução não oficial e contraria os termos de uso da Meta.** O número pode ser banido sem
   aviso e sem recurso.
2. Por isso: **número dedicado**, nunca o número pessoal do comprador nem o número comercial
   principal da Sogamax.
3. **A sessão cai** (troca de aparelho, atualização, inatividade) e volta só com QR Code
   presencial. Precisa de alerta ativo quando cair, senão o envio falha em silêncio.
4. Depende de um servidor de terceiro no ar — indisponibilidade dele é indisponibilidade do
   canal.
5. Envio em rajada (24 mensagens no 1º dia útil) é padrão típico de disparo em massa. Se for
   usado para envio real, intervalar as mensagens.

**Uso sugerido para começar: WhatsApp como aviso, não como transporte.**

> "Bom dia! O mapa de estoque da Sogamax referente a 2026-07 foi enviado agora para o e-mail
> mapa@laboratorio.com.br. Qualquer coisa, é só chamar aqui."

O arquivo vai por e-mail; o WhatsApp só avisa. Reduz drasticamente a exposição do número e
entrega o ganho real — que é a indústria saber que o mapa chegou.

---

## 8. Modos de operação e teste

| Flag | Efeito |
|---|---|
| `--dry-run` | mostra o plano completo e sai; não abre conexão nem grava `envios.json` |
| `--sim` | não pede a confirmação `SIM` |
| `--canal email` / `--canal whatsapp` | restringe a um canal |
| `--refazer` | ignora o `envios.json` (combine com `--fabricante`) |
| `--rascunho` | grava `.eml` e a página `wa.me` em vez de enviar |

Além das flags, **duas** chaves no `.env` sobrepõem os destinatários reais:
`DESTINATARIO_TESTE` para o e-mail e `TELEFONE_TESTE` para o WhatsApp. São independentes de
propósito, e o cabeçalho do plano marca `TESTE` ou `REAL` **por canal** — preencher só uma
deixaria o outro canal enviando para as indústrias, e isso precisa estar na cara.

O `DESTINATARIO_TESTE` aceita vários endereços separados por vírgula. Sem isso, incluir o
comprador na homologação exigiria desligar a trava — trocar a proteção pelo que ela protege,
que é o pior desfecho possível para uma trava de teste.

Roteiro de homologação:

1. `--dry-run` numa rodada real: conferir a lista de destinatários e o texto com o comprador.
2. `--rascunho`: gerar os `.eml`, o comprador abre e envia manualmente por uma semana.
3. As duas travas de teste apontando para as contas do Pedro: verificar entrega, formatação,
   se o anexo abre e se a mensagem de WhatsApp chega legível.
4. Envio real para **um** laboratório combinado, por um ciclo.
5. Liberação geral, esvaziando as travas.

---

## 9. Ordem de implementação

O código está feito:

- ~~Estender `Fabricante` com `contatos` + validação em `src/config.py`~~
- ~~`src/disparo/` com o contrato `Canal`, o roteador, `envios.json` e o canal Rascunho~~
- ~~Canal e-mail~~ — SMTP da Locaweb, sem depender da aplicação da empresa
- ~~Canal WhatsApp~~ — adaptador por perfil, com o perfil Z-API pronto

O que falta não é código:

- ~~**Levantar os contatos** (§3)~~ — feito em 26/08/2026, da coluna `E-MAIL` da planilha.
- ~~**Credenciais de SMTP**~~ — a caixa `confirmacao@` está configurada e validada com envio real.

O que falta:

1. **Conferir os contatos com o comprador** — sete laboratórios apontam para um domínio que não
   é o do próprio nome (grupo econômico), e quatro deles para a mesma pessoa. Plausível, mas
   vale confirmar antes do primeiro mapa real.
2. **Esvaziar o `DESTINATARIO_TESTE`** — é a ação que libera o envio às indústrias, e a única
   proteção que resta depois do cadastro real.
3. **Contratar o provedor de WhatsApp** e preencher instância e token. Se não for Z-API, um
   perfil novo em `whatsapp_api.py`, conferido na documentação oficial do provedor.
4. Homologar pelo roteiro da §8, do `--dry-run` até a liberação geral.

---

## 10. Pendências para decidir com o comprador

- Laboratório **sem movimento no período**: avisa ou silencia? (§4)
- Texto final do e-mail e do WhatsApp (§5).
- ~~Quem recebe a **cópia interna** de cada envio~~ — **resolvido (26/08/2026)**: o YURI, via
  `copia` nos 24 laboratórios. Some com a trava de teste ligada, e volta na liberação. A
  resposta da indústria também chega a ele, por outro caminho — o `RESPONDER_PARA` do `.env`,
  que vira `Reply-To`. São coisas distintas: a cópia é o mapa no momento do envio; o Reply-To
  é a resposta depois.
- Quem deve ser alertado quando um envio falhar, e por qual meio. Hoje a falha aparece no
  resumo e no código de saída 3; ninguém é avisado ativamente.

**Resolvido:** o WhatsApp é aviso ou carrega o arquivo? Virou decisão por laboratório, no
campo `whatsapp_anexo` (§3), com o padrão em "só avisa".

**Resolvido (25/08/2026): mais de um comprador.** A planilha do cadastro tem uma coluna
`COMPRADOR`, hoje com um valor só (YURI TOSO), mas a estrutura de negócio prevê outros. Como
`COMPRADOR` e `RESPONDER_PARA` são globais no `.env`, um laboratório de outro comprador sairia
**assinado com o nome errado** e com a resposta indo para a pessoa errada — o primeiro erro
visível para a indústria.

O bloco `comprador` por fabricante (§3) resolve os dois: `nome` assina, `responder_para`
recebe a resposta. É opcional e cai no `.env` quando ausente, então nada muda para os 24 já
cadastrados. Não é preciso preencher nada enquanto houver um comprador só — a estrutura fica
pronta para o dia em que houver dois.
