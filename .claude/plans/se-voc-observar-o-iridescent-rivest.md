# Proteções contra abuso e descontrole no envio

## Contexto

O disparo por SMTP já funciona, mas as travas existentes protegem contra **engano humano** —
confirmação `SIM`, `DESTINATARIO_TESTE`/`TELEFONE_TESTE`, idempotência via `envios.json`,
intervalo entre laboratórios e falha isolada. Nenhuma delas protege contra **descontrole**:
o laço em [__main__.py](src/disparo/__main__.py) percorre a lista inteira, seja ela de 24 ou
de 2.400 itens, e continua tentando mesmo depois de o servidor recusar tudo.

Três cenários realistas hoje quebram a conta de e-mail da empresa:

| Cenário | O que acontece hoje |
|---|---|
| Senha revogada, ou o provedor marcou a conta | 24 tentativas seguidas de login/envio recusado — que é justamente o padrão que faz um provedor suspender a conta |
| `fabricantes.yaml` duplicado, ou manifesto com leva antiga junto | dispara tudo, sem teto: `--sim` num cadastro errado manda centenas |
| Rodada grande perto do limite da Locaweb (100/h por caixa) | estoura a cota, e os últimos e-mails somem sem ninguém notar |

O objetivo é o sistema **parar sozinho** antes de virar abuso, e dizer com clareza por quê.

### Decisões tomadas com o usuário

| Assunto | Escolha |
|---|---|
| Mesmo e-mail em vários laboratórios | manter um e-mail por relatório, mas **avisar** no plano |
| Ao atingir a cota horária | **parar e avisar** quantos faltam e a partir de que hora continuar |
| Erro temporário do servidor (4xx) | **2 retentativas** com espera crescente; erro permanente falha na hora |

---

## Implementação

### 1. Novo módulo — `src/disparo/limites.py`

Concentra as três defesas que o roteador não deveria conhecer em detalhe.

**Cota por hora** (`CotaDeEnvio`). Janela deslizante de 60 minutos, por canal, persistida em
`logs/envios.jsonl` — um registro por linha, gravado a cada envio:

```json
{"em": "2026-08-19T07:12:33", "canal": "email", "fabricante": "MARJAN", "id": "<...>"}
```

Append-only, e por isso serve às duas coisas: contar a cota e ser o **histórico de auditoria**
do que realmente saiu — hoje o `envios.json` guarda só o último envio de cada chave, então um
reenvio apaga o rastro do anterior.

Antes de cada mensagem o roteador pergunta `cota.permite("email")`. Ao estourar, a leva para
com o horário em que a janela abre de novo. Padrão `MAX_ENVIOS_POR_HORA=90`, com folga sobre
os 100/hora por caixa da Locaweb.

**Disjuntor** (`Disjuntor`). Conta falhas consecutivas por canal; ao chegar em
`MAX_FALHAS_SEGUIDAS` (padrão 3), aquele canal é desligado para o resto da leva e os demais
seguem. Um envio bem-sucedido zera o contador — o alvo é a falha sistemática (credencial
revogada, servidor barrando, sessão do WhatsApp caída), não o erro isolado de um endereço.

**Teto por rodada.** Se o plano tiver mais que `MAX_ENVIOS_POR_RODADA` (padrão 30, contra os
24 reais), o comando **recusa antes de conectar**, com código 2, explicando o que provavelmente
está errado e como seguir (`--fabricante`, `--periodo`, ou `--forcar` se for mesmo intencional).
É a rede contra cadastro duplicado e contra `--sim` distraído.

### 2. Retentativa e classificação de erro — `canais/email_smtp.py`

Hoje qualquer `SMTPException` vira `FalhaNoEnvio`. Passa a distinguir:

| Situação | Tratamento |
|---|---|
| 4xx (`SMTPResponseException` com código 4xx), queda de conexão, timeout | **temporário** — até 2 retentativas, esperando 5 s e 15 s |
| 5xx, endereço inexistente, mensagem recusada | **permanente** — falha na hora |
| `SMTPAuthenticationError` | **permanente e fatal** — aborta a leva inteira |

A autenticação merece regra própria: repetir login com senha errada é exatamente o que faz um
provedor bloquear a conta. Uma tentativa, e para tudo.

Na queda de conexão a retentativa **reabre a sessão** antes de tentar de novo — senão as duas
tentativas seguintes falhariam pelo mesmo motivo.

### 3. Aviso de destinatário repetido — `__main__.py`

Ao montar o plano, agrupar por endereço e destacar quem recebe mais de uma mensagem:

```
  ATENCAO: mapa@eurofarma.com.br recebe 2 e-mails nesta leva (EUROFARMA, EUROFARMA_RX)
```

Não bloqueia: são relatórios diferentes, de códigos diferentes do Geweb, e mandar separado
pode ser o certo. Mas a pessoa que confirma precisa ver isso antes de digitar `SIM`.

### 4. Limite de tamanho do anexo

`MAX_ANEXO_MB` (padrão 10). Um `.xlsx` do mapa tem menos de 100 KB; qualquer coisa perto do
limite indica arquivo errado. Conferido na montagem do plano, antes de qualquer conexão — o
laboratório entra como pendência, e o resto da leva segue.

### 5. Chaves novas no `.env`

| Chave | Padrão | Protege contra |
|---|---|---|
| `MAX_ENVIOS_POR_RODADA` | `30` | cadastro duplicado, leva inesperadamente grande |
| `MAX_ENVIOS_POR_HORA` | `90` | estourar a cota da Locaweb (100/h por caixa) |
| `MAX_FALHAS_SEGUIDAS` | `3` | martelar um servidor que já está recusando |
| `MAX_TENTATIVAS` | `3` | (1 tentativa + 2 retentativas) |
| `MAX_ANEXO_MB` | `10` | anexar arquivo errado |

Todos com padrão seguro: quem não mexer no `.env` já fica protegido.

### 6. Onde isso aparece para o operador

- **No `--dry-run`**: o plano mostra o total, o teto, quanto da cota horária já foi usado e os
  destinatários repetidos. Nada disso exige conexão.
- **Durante o envio**: cada parada anuncia o motivo — `COTA ATINGIDA`, `CANAL DESLIGADO apos 3
  falhas`, `TETO DA RODADA`.
- **No resumo**: enviados, falhos, e o que ficou para a próxima rodada por causa de limite.

**Não muda:** a extração, o formatador, a agenda, nem o contrato `Canal`. As proteções ficam no
roteador e no canal de e-mail; o canal de WhatsApp herda a cota e o disjuntor sem mudança.

---

## Verificação

Tudo com dublês, sem tocar em servidor real — o mesmo método que validou o envio.

1. **Teto por rodada**: manifesto forjado com 50 itens ⇒ recusa com código 2, sem abrir
   conexão; com `--forcar`, prossegue.

2. **Disjuntor**: servidor falso que recusa sempre ⇒ para no 3º laboratório, não no 24º; o
   resumo diz que o canal foi desligado; o canal de WhatsApp na mesma leva continua enviando.

3. **Retentativa**: servidor que devolve 4xx duas vezes e aceita na terceira ⇒ a mensagem sai,
   e o log mostra as duas esperas. Servidor que devolve 5xx ⇒ falha imediata, **sem** repetir.

4. **Autenticação**: senha errada ⇒ uma única tentativa de login e abortagem da leva. Conferir
   no dublê que `login` foi chamado **uma vez só** — repetir aqui é o que bloqueia conta.

5. **Cota horária**: `MAX_ENVIOS_POR_HORA=3` e uma leva de 5 ⇒ envia 3, para, informa o horário
   de liberação, e os 3 ficam registrados. Rodar de novo em seguida ⇒ recusa por cota. Forjar
   timestamps antigos no `envios.jsonl` ⇒ a janela deslizante libera.

6. **Destinatário repetido**: dois laboratórios com o mesmo e-mail via âncora YAML ⇒ o aviso
   aparece no plano, e as duas mensagens continuam sendo enviadas.

7. **Anexo grande**: arquivo de 15 MB ⇒ aquele laboratório vira pendência com o motivo, e os
   outros são enviados normalmente.

8. **Nenhuma regressão**: a leva de 4 laboratórios que já funciona continua saindo igual, com
   os padrões novos ligados.

---

## O que isto não resolve

Estas defesas protegem a conta e a operação. **Não** substituem o que continua faltando para
o disparo ser usado de verdade: os contatos das indústrias, as credenciais de SMTP e a
contratação do provedor de WhatsApp.

Também fica de fora, por ora, o alerta ativo quando algo falha — hoje a falha aparece no
resumo, no `logs/disparo.log` e no código de saída 3, mas ninguém é avisado por outro meio.
É a pendência da §10 do [docs/disparo.md](docs/disparo.md), e depende de decidir *quem* deve
ser avisado.
