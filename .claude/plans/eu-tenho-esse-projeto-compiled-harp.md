# Cadastro guiado de fornecedores para o comprador

## Contexto

Hoje o cadastro de fornecedores — códigos do Geweb, e-mails, cópia, dias da semana, ativo/inativo —
mora em [fabricantes.yaml](fabricantes.yaml), 211 linhas editadas à mão pelo TI. A intenção é passar
essa manutenção para os compradores. A opção de portal web foi descartada; o caminho escolhido é um
**comando de cadastro guiado** com `.bat` de duplo clique, rodando sobre o script atual.

A razão de ser um comando guiado, e não uma planilha ou o YAML na mão: o campo `codigos` é o código
interno do ERP (`106975`, `13963`). Um dígito errado não dá erro nenhum — gera o relatório de **outro
fabricante** e o envia para a indústria certa. Falha silenciosa, externa e difícil de descobrir. No
comando guiado o comprador busca o fornecedor **por nome** na lista real do Geweb e escolhe da lista;
nunca digita um código.

**Restrição do usuário:** não desconfigurar o script que já roda em produção. Todo o trabalho fica
isolado até ser homologado.

---

## Fase 0 — criar o isolamento (não existe hoje)

Não há como "trabalhar numa branch": o projeto **não é um repositório git**. Existe um `.gitignore`
completo e correto (protege `.env`, `.auth/`, os JSONs de estado e as saídas), o que sugere que a
intenção existiu, mas `git rev-parse` confirma que não há `.git`.

1. `git init` na pasta atual + commit inicial da versão que roda hoje. Esta é a linha de retorno: sem
   ela, qualquer alteração no projeto é irreversível.
2. **Desenvolver numa cópia da pasta, não numa branch aqui.** A tarefa agendada das 07:00 executa a
   partir *deste* diretório — um `git checkout` nesta pasta troca o código que roda amanhã de manhã.
   Clonar para `..\mapa-de-estoque-dev`, trabalhar lá, e a pasta de produção nunca sai do `main`.
   A homologação vira um `git pull` aqui, no momento que você escolher.
3. Preparar o `.env` da cópia de trabalho:
   - `DESTINATARIO_TESTE` preenchido (nenhuma indústria é tocada);
   - `DOWNLOAD_DIR` / `FORMATADO_DIR` apontando para pastas locais da cópia, **fora do ownCloud** —
     hoje apontam para `C:\Users\pedro.veloso\ownCloud\Relatório Automático - Teste[- Formatado]`, que
     é o destino de produção.
   - Os JSONs de estado são gitignored, então a cópia nasce sem eles. Isso é o desejado: testar não
     pode marcar um mês como entregue em produção.
4. **Cuidado com a sessão do Geweb:** o ERP aceita uma sessão por usuário. Testes na cópia que abram o
   navegador não podem coincidir com a rodada das 07:00. O grosso da validação do cadastro usa
   `--planejar`, que não abre o Geweb.

Item avulso, independente disso: [executar.bat](executar.bat) ainda documenta o caminho antigo
`Documents\script-test` nas linhas 15-16. Vale conferir para onde a tarefa agendada aponta hoje
(`schtasks /Query /TN "Mapa de Estoque - Geweb" /V /FO LIST`).

## Fase 1 — o comando de cadastro (aditivo, não toca no que roda)

Arquivos **novos**: `src/cadastro.py` e `cadastrar.bat`. Nenhum arquivo existente é modificado nesta
fase — o script de produção continua idêntico mesmo depois do merge.

**Menu** (`python -m src.cadastro`, numerado, em português):
1. Listar fornecedores — nome, códigos, agenda (`resumo_envio` já existe em
   [config.py:172](src/config.py#L172)), e-mails, ativo/inativo;
2. Adicionar fornecedor;
3. Editar fornecedor;
4. Ativar / desativar;
5. Conferir o cadastro (chama `carregar_fabricantes()` e mostra o resultado);
6. Ver o plano dos próximos dias (`tarefas_do_dia`, sem abrir o Geweb).

**Reuso — nada de regra nova.** O comando usa o que já existe:
- `carregar_fabricantes()` para ler ([config.py:386](src/config.py#L386));
- as dataclasses `Fabricante` / `Contatos` / `Comprador` ([config.py:95-175](src/config.py#L95-L175))
  como modelo;
- `normalizar_dia`, `DIAS_SEMANA`, `JANELAS_SEMANAIS` de `src/periodo.py` para os dias;
- as mesmas checagens de e-mail e E.164 de `_ler_contatos` / `_ler_comprador`, aplicadas **no
  momento da digitação**, com a mensagem de erro na hora em que dá para corrigir.

**Escolha do fornecedor sem digitar código:** busca por trecho do nome em
`logs/fabricantes-geweb.txt` (as 1140 linhas geradas por `python -m src.descobrir --fabricantes`),
apresenta os resultados numerados e o comprador escolhe. Um fornecedor pode ter vários códigos (um por
divisão/CD) — o menu permite marcar mais de um, que é o que o `codigos: [...]` significa. Se o arquivo
não existir ou estiver velho, o menu oferece regerá-lo.

**Gravação do YAML — round-trip, preservando o arquivo.** O `fabricantes.yaml` tem 60 linhas de
comentário-documentação no topo e âncoras (`&eurofarma` / `*eurofarma`, usadas onde o mesmo
laboratório aparece em duas entradas: EUROFARMA/EUROFARMA_RX, as duas Brace Pharma, ACHE/BIOSINTETICA).
Um `yaml.dump()` destrói as duas coisas — e expandir uma âncora transforma um dado compartilhado em
duas cópias que passam a divergir na próxima edição.

Por isso: **nova dependência `ruamel.yaml`**, em modo round-trip, que preserva comentários e âncoras ao
reescrever. É a sexta dep de um projeto que tem cinco, e é exatamente a ferramenta para este problema.
O ciclo de gravação segue o padrão atômico já usado em `src/estado.py` e `src/rodada.py`:

1. escreve num temporário;
2. **valida relendo com `carregar_fabricantes()`** — um YAML que não passa na própria validação do
   script nunca chega ao disco;
3. arquiva a versão anterior em `historico/fabricantes-AAAA-MM-DD-HHMM.yaml` (rollback é copiar um
   arquivo de volta);
4. `os.replace`.

`cadastrar.bat` — duplo clique, ativa o venv e chama o módulo, no mesmo molde de `executar.bat`.

## Fase 2 — endurecer a validação (toca código existente, commit separado)

Esta é a única alteração em código de produção, e a mais importante antes de entregar o cadastro a
outra pessoa. Hoje `carregar_fabricantes()` levanta `ConfiguracaoInvalida` no primeiro erro e
[main.py:341](src/main.py#L341) sai com código 2 **antes de abrir o navegador**: um e-mail digitado
errado impede a rodada dos 23 laboratórios, e não existe alerta ativo para avisar ninguém.

1. Antes de mexer: `pytest` como dep de desenvolvimento e testes cobrindo cada regra de validação de
   `carregar_fabricantes()` e os casos de `tarefas_do_dia()` ([agenda.py:47](src/agenda.py#L47)) —
   mensal recuperável, 1º dia útil, semanal, fim de semana. Hoje não existe teste nenhum no projeto.
2. Trocar o "aborta tudo" por: fabricante inválido é **desativado com `log.error` bem visível** e a
   rodada segue com os demais. Só aborta se nenhum fabricante válido sobrar — preservando o
   `if not ativos` que já existe em [config.py:461](src/config.py#L461).
3. Commit e merge separados da Fase 1, para poder homologar uma coisa de cada vez.

## Fase 3 — em aberto: onde o script vai rodar

Decisão ainda não tomada, e ela não bloqueia as fases acima. O que precisa ser resolvido antes de o
comprador rodar o script na máquina dele:

- **O `.env` vai junto** — senha do Geweb (`automacao`), senha SMTP de `confirmacao@sogamax.com.br` e
  tokens da Z-API em texto plano. Quem tem o arquivo manda e-mail como a empresa.
- **Duas máquinas rodando = envio duplicado.** `envios.json` é o que impede reenviar um período já
  entregue, e é local a cada máquina. Somado à sessão única do Geweb, rodar nos dois lugares é a falha
  mais cara possível: a indústria recebe o mapa duas vezes.
- **A tarefa das 07:00 precisa de dono**, e a máquina dele precisa estar ligada no horário.
- **Instalação:** Python 3.12 + venv + Playwright/Chromium não é duplo clique.
- **`DESTINATARIO_TESTE`** é hoje a única coisa entre o sistema e as indústrias.

---

## Verificação

**Fase 0** — `git log` mostra o commit inicial; a cópia de trabalho roda
`python -m src.main --planejar` e produz o mesmo plano da produção; confirmar que a cópia não escreve
nas pastas do ownCloud.

**Fase 1** — na cópia de trabalho:
1. `python -m src.cadastro` → listar, e conferir que os 24 fornecedores aparecem com a mesma agenda do
   YAML atual;
2. adicionar um fornecedor fictício buscando por nome, e conferir no YAML que os códigos gravados
   batem com `logs/fabricantes-geweb.txt`;
3. tentar cadastrar um e-mail sem `@` e um telefone fora do padrão `+55...` — o comando precisa recusar
   na hora, sem gravar;
4. editar o e-mail da EUROFARMA e conferir com `git diff` que **apenas aquela linha mudou** — os
   comentários do topo e as âncoras continuam intactos;
5. conferir o backup em `historico/` e restaurá-lo;
6. `python -m src.main --planejar` depois de cada edição.

**Fase 2** — `pytest` verde; introduzir um e-mail inválido em um fabricante e confirmar que a rodada
segue com os outros 22 e registra o erro no log, em vez de sair com código 2.

**Merge para produção** — só depois de 1 e 2 homologados, com `git pull` na pasta de produção fora da
janela das 07:00, seguido de `python -m src.main --planejar` para confirmar que o plano do dia não
mudou.
