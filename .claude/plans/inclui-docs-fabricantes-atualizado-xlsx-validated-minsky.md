# Cadastrar os contatos reais das 24 indústrias

## Contexto

O levantamento dos contatos das indústrias era **o bloqueio principal** do projeto: o código de
envio está pronto e validado desde 24/08 (24 de 24 e-mails entregues no teste real), mas os 24
laboratórios apontavam para endereços internos de homologação, porque nenhum e-mail de indústria
existia em lugar nenhum do projeto.

A planilha `docs/Fabricantes atualizado.xlsx` traz esse dado: uma coluna `E-MAIL` nova, com um
endereço por laboratório. Este plano transfere esse cadastro para o `fabricantes.yaml`.

**Nada será disparado.** A trava `DESTINATARIO_TESTE` continua ligada com `pedro@sogamax.com.br`
e `yuritoso@sogamax.com.br`, então todo envio segue indo para vocês dois. O que muda é só o
cadastro — o sistema fica pronto para a liberação, que é um passo separado e futuro.

## Conferência já feita (não precisa refazer)

- **Os 24 casam 1 para 1** com o `fabricantes.yaml`, pelos códigos do Geweb (`ID FABRICANTE`).
  Nenhuma linha sobrou de nenhum lado.
- **A agenda da planilha nova bate exatamente** com a do cadastro atual: mensal em todos;
  semanal em DIFFUCAP (seg), EUROFARMA_RX (seg), MARJAN (seg+qua), SANOFI_MEDLEY (seg+qui).
  Nada a mudar aí.
- **Nenhum endereço malformado.** Dois têm maiúsculas (`Antonio.Barbara@viatris.com`,
  `Gustavo.Barbosa@swixxbiopharma.com`) — válido, será preservado como veio.
- **Não há telefone na planilha**, então todos ficam `canais: [email]`. O WhatsApp continua fora.

## ⚠️ O que este plano muda na postura de segurança

Hoje a proteção contra um mapa chegar a fornecedor é **dupla**: a trava redireciona, e além
disso nenhum endereço de indústria existe no arquivo. Depois deste cadastro, a segunda camada
deixa de existir — **a trava `DESTINATARIO_TESTE` passa a ser a única proteção.**

Isso é inevitável (é o objetivo do cadastro) e é o desenho normal do projeto, mas muda o peso
daquela linha do `.env`: esvaziá-la passa a ser a ação que libera o envio real. O plano inclui
tornar isso explícito no cabeçalho do arquivo.

## Mudanças

### 1. `fabricantes.yaml` — o cadastro (mudança principal)

Substituir as 24 linhas `contatos: &teste {...}` / `contatos: *teste` pelo bloco real de cada
laboratório, no formato:

```yaml
    contatos: {emails: [ethieny.araujo@diffucap.com.br], copia: [yuritoso@sogamax.com.br], canais: [email]}
```

Como todas as 24 linhas são substituídas de uma vez, a âncora `&teste` desaparece junto com seus
aliases — sem risco de alias órfão (que derrubaria a rodada com *"found undefined alias"*).

**Sem âncoras para os endereços compartilhados.** Dois contatos atendem mais de um laboratório:

| Endereço | Laboratórios |
|---|---|
| `eduardo.lucena@underskin.com.br` | EMS_BRACE_PHARMA_EXTREMA, EMS_BRACE_PHARMA_HORTOLANDIA, GERMED, LEGRAND |
| `roberto.mattos@ems.com.br` | EMS_RX, LAFIMAN |

O README sugere âncoras para não duplicar dado, mas ali o caso é *o mesmo laboratório em duas
entradas*. Aqui são laboratórios **distintos** que por ora compartilham um contato de grupo
econômico. Se o Eduardo sair da GERMED e continuar na LEGRAND, a âncora obrigaria a desmembrar.
Escrever explícito custa uma linha a mais e evita esse acoplamento — com um comentário marcando
que o endereço é compartilhado, para o aviso do `--dry-run` não surpreender.

**O cadastro completo a aplicar** (nome no YAML ← e-mail da planilha):

| Laboratório | E-mail |
|---|---|
| ACHE | neymar.silva@ache.com.br |
| BIOSINTETICA_RX | lindomar.amaral@biosintetica.com.br |
| ASPEN | fjunior4@br.aspenpharma.com |
| BIOPAS | Gustavo.Barbosa@swixxbiopharma.com |
| DIFFUCAP | ethieny.araujo@diffucap.com.br |
| DIVCOM_RX | mapaulo@fqm.com.br |
| EMS_BRACE_PHARMA_HORTOLANDIA | eduardo.lucena@underskin.com.br |
| EMS_BRACE_PHARMA_EXTREMA | eduardo.lucena@underskin.com.br |
| EMS_RX | roberto.mattos@ems.com.br |
| EUROFARMA | janderson.venturin@momentafarma.com.br |
| EUROFARMA_RX | pedro.silva@eurofarma.com |
| GERMED | eduardo.lucena@underskin.com.br |
| HERBAMED | kirian.cunha@herbamed.com.br |
| KLEY_HERTZ | mfigueiredo@hertzfarma.com.br |
| LAFIMAN | roberto.mattos@ems.com.br |
| LEGRAND | eduardo.lucena@underskin.com.br |
| MARJAN | nr.nelson@marjanfarma.com.br |
| MEDQUIMICA | thiagodomingues@lupin.com |
| MYRALIS | elaine.silva@myralis.com.br |
| ORGANON | paulo.sakakura@organon.com |
| SANOFI_MEDLEY | comercial.farma@sanofi.com |
| SUPERA_RX | leandro.braga@superarx.com.br |
| TORRENT | renato@torrent.com.br |
| VIATRIS | Antonio.Barbara@viatris.com |

Todos com `copia: [yuritoso@sogamax.com.br]` e `canais: [email]`.

### 2. `fabricantes.yaml` — cabeçalho

- Linha 2: a fonte passa a ser `docs/Fabricantes atualizado.xlsx` (a antiga não tinha e-mail).
- Substituir o bloco "CADASTRO DE HOMOLOGAÇÃO" (que diz que não há endereço de indústria no
  arquivo — deixará de ser verdade) por um aviso de que os contatos agora são **reais**, e que
  a partir daqui a única coisa que impede o envio às indústrias é o `DESTINATARIO_TESTE`.

### 3. Documentação que passa a mentir

Três trechos afirmam que não existe destinatário cadastrado:

- `README.md`, seção *Cadastrar os contatos*: "**nenhum e-mail ou telefone de indústria existe
  hoje no projeto**".
- `docs/disparo.md` §1: "O que **não existe**: **nenhum destinatário cadastrado**".
- `docs/disparo.md` §9, item 1: "Levantar os contatos — bloqueia o uso" → passa a concluído; o
  que resta como bloqueio para produção é só esvaziar a trava.

Em `docs/disparo.md` §10, a pendência *"quem recebe a cópia interna de cada envio"* passa a
resolvida: YURI, via `copia` nos 24. Registrar junto que a resposta da indústria também chega a
ele, pelo `RESPONDER_PARA` já configurado — são caminhos distintos (cópia = o mapa no envio;
Reply-To = a resposta depois).

### 4. Memória do projeto

Atualizar `mapa-estoque-etapas-pendentes.md`: o bloqueio principal deixou de existir, e o novo
estado é "cadastrado e travado, aguardando decisão de liberar".

## Não muda

- `.env` — a trava fica como está (`pedro@` + `yuritoso@`), e `RESPONDER_PARA` já é o YURI.
- Nenhum código Python. O `Contatos` já suporta `emails`/`copia`/`canais`; nada falta.
- Nenhuma tarefa agendada. Continua não existindo.

## Verificação

1. **O YAML carrega e ninguém ficou sem contato:**
   ```powershell
   .venv\Scripts\python -m src.main --planejar
   ```
   Deve listar a agenda normalmente e sair com código 0. Um erro de digitação em qualquer
   e-mail derruba aqui com código 2, apontando o laboratório — a validação já existe em
   `src/config.py`.

2. **Conferir o cadastro contra a planilha, célula a célula.** Script de leitura que compara os
   24 endereços carregados do YAML com os da planilha e acusa qualquer divergência. É a
   verificação que importa, porque a trava esconde o destino real no `--dry-run`.

3. **Confirmar que a trava continua segurando tudo:**
   ```powershell
   .venv\Scripts\python -m src.disparo --periodo 2026-08-01_a_2026-08-24 --canal email --dry-run --refazer
   ```
   O cabeçalho deve dizer `TESTE email tudo vai para pedro@sogamax.com.br, yuritoso@sogamax.com.br`,
   e **nenhum endereço de indústria pode aparecer** em nenhuma linha do plano.

4. **Reexecutar o teste de vazamento** (`teste_trava.py`, do scratchpad), agora com contatos
   reais no arquivo em vez de fictícios: o `To` deve conter só os dois endereços internos, `Cc`
   vazio, e nenhum domínio de indústria no corpo bruto da mensagem.

5. **Regressões:** as outras três baterias (`teste_enviar`, `teste_comprador`,
   `teste_dois_compradores`) devem continuar passando.

## Depois disto (fora deste plano)

O que restará para a produção, na ordem: conferir os contatos com o YURI (ver abaixo), esvaziar
o `DESTINATARIO_TESTE`, e agendar o `executar.bat`.

**Vale conferir com o YURI** que estes endereços de grupo econômico são mesmo os certos, porque
o domínio não corresponde ao nome do laboratório e um deles pode ser engano de preenchimento:
BIOPAS→swixxbiopharma, DIVCOM_RX→fqm, EUROFARMA(14232)→momentafarma, MEDQUIMICA→lupin,
LAFIMAN→ems, e GERMED/LEGRAND/EMS_BRACE→underskin. Todos são plausíveis como grupo econômico
(e o de EUROFARMA/14232 confirma a nota antiga de que aquele código é MOMENTA), mas quatro
laboratórios apontando para a mesma pessoa é o tipo de coisa que vale confirmar antes de o
primeiro mapa real sair.
