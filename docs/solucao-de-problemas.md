# Solução de problemas

Onde procurar primeiro:

| Arquivo | O que mostra |
|---|---|
| `<FORMATADO_DIR>\logs\<AAAA-MM>.xlsx` | O que saiu e o que falhou, por laboratório, com o motivo |
| `logs\execucao.log` | A narrativa da extração. Rode com `--debug` para ver o traceback completo |
| `logs\disparo.log` | A narrativa do envio |
| `logs\agendador.log` | Início, fim e código de saída de cada rodada agendada |

## Sintomas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| Sai com código 2 antes de abrir o navegador | `.env` incompleto, `fabricantes.yaml` ilegível ou opção inválida | A mensagem diz qual chave ou linha. Veja [configuracao.md](configuracao.md) |
| `CADASTRO IGNORADO` no log | Um laboratório com erro no cadastro | Corrija a entrada indicada e rode `pytest` |
| `Usuário já logado no sistema` | Alguém está logado no Geweb com o mesmo usuário | Veja [Uma sessão por usuário](#uma-sessão-por-usuário) |
| Timeout ao clicar num menu ou campo | O Geweb mudou a tela | Veja [Se a tela do Geweb mudar](#se-a-tela-do-geweb-mudar) |
| Relatório com dados do mês errado | O modelo salvo do Geweb sobrescreveu as datas | Veja as [armadilhas já resolvidas](#armadilhas-já-resolvidas) e rode `python -m src.descobrir --fluxo` |
| `formatacao falhou` no resumo | O Geweb devolveu uma página de erro ou mudou o relatório | O bruto fica em `DOWNLOAD_DIR`; formate à mão ou confira com `python -m src.formatador` ([operacao.md](operacao.md#o-arquivo-formatado)) |
| A planilha de histórico não atualizou | Estava aberta no Excel durante a rodada | Feche e rode `python -m src.historico` |
| Falha ao salvar só na tarefa agendada | `FORMATADO_DIR` numa unidade mapeada (`Z:`) | Troque pelo caminho UNC (`\\servidor\pasta`) |
| E-mail recusado com *503 Client host rejected* | `REMETENTE` diferente da conta que autenticou | Deixe `REMETENTE` vazio. Veja [envio.md](envio.md#configurar-o-e-mail) |
| Envio parou com "cota" ou "teto" | Uma proteção contra excesso agiu | O resumo diz qual e quando continuar. Veja [envio.md](envio.md#proteções-contra-descontrole) |
| Mapa enviado de novo a uma indústria | A pasta `dados\` foi perdida ou trocada | Restaure o `dados\envios.json` e o `dados\estado.json` do backup ou da máquina antiga |

## Uma sessão por usuário

O Geweb aceita **uma única sessão por usuário**. Se alguém estiver logado com o mesmo usuário,
o script é recusado com:

```
Usuário já logado no sistema para empresa (10501)!
IP: 172.16.130.31
```

O script identifica essa mensagem e falha com um recado claro, em vez de um timeout genérico.
Três formas de conviver com isso, da melhor para a pior:

1. **Usuário dedicado à automação** no Geweb (ex.: `automacao`), com permissão apenas para esse
   relatório. Nunca conflita com ninguém e o log do ERP fica rastreável. **Recomendado.**
2. **Agendar fora do expediente**, quando ninguém está logado.
3. Rodar manualmente, saindo do Geweb antes.

A sessão salva em `.auth\state.json` é reaproveitada entre execuções, então o script não faz
login toda vez; quando ela expira, a restrição volta a valer.

## Sessão manual (2FA ou captcha)

O login automático não passa por 2FA nem captcha. A alternativa é abrir a sessão à mão uma vez
e salvar o estado autenticado, que o script reaproveita:

```powershell
.venv\Scripts\playwright open --save-storage=.auth\state.json https://sistemas.sogamax.com.br/sistema/login.php
```

Faça o login na janela que abrir e feche. Quando a sessão expirar, repita o comando.

> ⚠️ O `.auth\state.json` guarda o cookie de sessão e vale tanto quanto a senha.

## Se a tela do Geweb mudar

Tudo o que o script clica está em [src/geweb/seletores.py](../src/geweb/seletores.py), o
**único arquivo a ajustar** quando o layout do Geweb muda.

**1. Diagnosticar.** Faz login, mapeia a sidebar, testa cada clique da navegação e imprime os
ids reais de todos os campos da tela. O resultado vai para `logs\descoberta.log`. Se um clique
de menu falhar, sai com código 1 e lista os links que encontrou:

```powershell
.venv\Scripts\python -m src.descobrir
```

Para checar só o preenchimento, sem gerar relatório (percorre navegação → período →
fabricante lendo os campos entre as etapas, mas **não clica em Gerar**):

```powershell
.venv\Scripts\python -m src.descobrir --fluxo
```

**2. Regravar, se preciso.** Grave o fluxo novo e reajuste **apenas** o `seletores.py`:

```powershell
.venv\Scripts\playwright codegen --target python -o gravacao.py https://sistemas.sogamax.com.br/sistema/login.php
```

> ⚠️ O `gravacao.py` guarda a senha digitada em texto puro. Está no `.gitignore`, mas apague o
> arquivo depois de extrair os seletores.

### Como o Geweb se comporta

| Comportamento do Geweb | Como é tratado |
|---|---|
| Todo o conteúdo vive dentro do iframe `#IFrameConteudo` | `IFRAME_RELATORIO` |
| Sidebar sanfona: cada nível só aparece após clicar no pai | 3 cliques em `MENUS_ATE_O_RELATORIO` |
| Cada item de menu carrega seu código (`5-2-10`) | selecionado por código, não por texto |
| Tipo de relatório e Fabricante são widgets **select2** | clicar → buscar → escolher |
| Datas são `<input type="date">`, em formato ISO | `FORMATO_DATA = "%Y-%m-%d"` |
| Fabricante é buscado por **código** (`13963` → `(13963) EUROFARMA`) | `codigo` no `fabricantes.yaml` |
| **Gerar** abre um popup e dispara o download | popup fechado automaticamente |

### Armadilhas já resolvidas

Cada uma custou uma execução falha até ser identificada. Não reintroduza:

- **Texto do menu vem duplicado.** O `textContent` do link é `"Relatórios Relatórios"`, porque
  o ícone SVG tem um `<title>` igual ao rótulo, e `:text-is("Relatórios")` acha **zero**. Por
  isso os menus são selecionados pelo código (`5-0-0`).
- **`[class~=]`, nunca `[class*=]`.** `5-0-0` é substring de `15-0-0`, que é o botão **Sair**.
- **Fabricante é select2 de múltipla escolha.** O elemento com o id é o `<ul>` interno, vazio e
  de altura zero, e o Playwright recusa clicar nele. O alvo é a caixa em volta (`:has(...)`).
- **A busca do select2 múltiplo é `<textarea>`, não `<input>`.** Um seletor com `input.` acha
  zero.
- **A opção casa por trecho, não exato.** `role=option[name="(13963)"]` não acha
  `(13963) EUROFARMA`; use `[role=option]:has-text(...)`.
- **O `.xls` gerado é HTML** com formatação Excel (`mso-number-format`), e os números vêm como
  texto em pt-BR. É por isso que existe o formatador.
- **Escolher o tipo de relatório carrega um modelo salvo por AJAX** e repovoa o formulário
  inteiro, **redefinindo as datas para o mês corrente**. Foi a falha mais perigosa: o relatório
  saía com dados e parecia certo, mas vinha do mês errado. Duas defesas: esperar
  `#vazia_nome_selecao` deixar de estar vazio (sinal de que o modelo carregou) e preencher as
  datas **por último**, conferindo-as logo antes de clicar em Gerar.
