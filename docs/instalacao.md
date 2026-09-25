# Instalação

Como preparar uma máquina para rodar o Mapa de Estoque, validar a instalação e migrar a
automação para outro computador ou servidor.

## Requisitos

| Item | Detalhe |
|---|---|
| Sistema | Windows 10/11 ou Windows Server |
| Python | 3.12 (é a versão em uso; as dependências estão fixadas em [requirements.txt](../requirements.txt)) |
| Navegador | Chromium do Playwright, instalado pelo próprio projeto (~150 MB) |
| Rede | Acesso ao Geweb (`sistemas.sogamax.com.br`) e ao SMTP da Locaweb (`email-ssl.com.br:465`) |
| Geweb | Usuário dedicado à automação. Veja [Uma sessão por usuário](solucao-de-problemas.md#uma-sessão-por-usuário) |
| Pasta de saída | Onde os compradores leem os mapas, local ou de rede (`FORMATADO_DIR`) |

## 1. Instalar

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\playwright install chromium
```

## 2. Configurar

```powershell
copy .env.example .env
notepad .env
```

Preencha pelo menos as credenciais do Geweb (`GEWEB_URL`, `GEWEB_USUARIO`, `GEWEB_SENHA`).
Para enviar e-mails, também `SMTP_USUARIO` e `SMTP_SENHA`. Todas as chaves estão descritas
em [configuracao.md](configuracao.md#o-arquivo-env).

> ⚠️ Enquanto a homologação não terminar, mantenha o `DESTINATARIO_TESTE` preenchido. Com
> ele vazio, os mapas vão para as indústrias de verdade.

## 3. Validar

Siga esta ordem. Cada passo depende do anterior.

1. `.venv\Scripts\python -m pytest` → verde. Não abre navegador, roda em menos de um segundo,
   e o último teste confere que o `fabricantes.yaml` de produção continua válido. Exige as
   dependências de desenvolvimento (veja [desenvolvimento.md](desenvolvimento.md#testes)).
2. `.venv\Scripts\python -m src.geweb.session` → o navegador loga e para na home.
3. Um fabricante, um mês (`python -m src.main --fabricante EUROFARMA_RX --mes 2026-07`) →
   **abra o Excel e compare com o relatório gerado à mão**. Este é o teste que realmente
   importa. Confira também o cabeçalho da última coluna: precisa dizer o mês pedido
   (`JULHO_2026`), e não o mês corrente.
4. Rodada completa → um arquivo por fabricante e o resumo no final.
5. Coloque um `codigo` inválido num fabricante → os demais devem concluir normalmente e ele
   aparecer como falha no resumo.
6. Ponha um e-mail sem `@` no `contatos` de um fabricante → ele deve ficar **de fora** com
   `CADASTRO IGNORADO` no log, os demais rodarem normalmente, e chegar um e-mail em
   `ALERTA_PARA` nomeando quem ficou de fora. Desfaça a edição depois.
7. Repita com `--headless` → resultado idêntico. É comum quebrar aqui na primeira vez.
8. `python -m src.disparo --dry-run` → confira destinatários, travas e cotas.
9. Só então crie ou habilite a tarefa agendada. Veja [agendamento.md](agendamento.md).

## Migrar para outra máquina ou servidor

O repositório tem o código e o cadastro. O que é **local de cada instalação** fica fora do
git e precisa ser copiado à parte:

| O quê | Por que importa |
|---|---|
| `.env` | Credenciais do Geweb e do SMTP, e as travas de teste |
| `dados\` | Registro do que já foi extraído e enviado (`estado.json`, `envios.json`, `sequencia.json`, `ultima-rodada.json`). **Sem ele, a máquina nova reenvia mapas às indústrias e reinicia a numeração dos arquivos** |
| `logs\historico.jsonl` e `logs\envios.jsonl` | Histórico das rodadas e a contagem da cota horária de envio. Opcional, mas sem eles a planilha de histórico recomeça do zero |

Não copie `.venv\` nem `.auth\`: o ambiente é recriado pela instalação, e a sessão do Geweb é
refeita no primeiro login.

Passo a passo:

1. **Desabilite a tarefa agendada na máquina antiga.** Duas máquinas rodando ao mesmo tempo
   enviam em dobro e disputam a sessão do Geweb.
   ```powershell
   schtasks /Change /TN "Mapa de Estoque - Geweb" /DISABLE
   ```
2. Na máquina nova, clone o repositório e faça os passos 1 e 2 acima.
3. Copie o `.env` e a pasta `dados\` da máquina antiga.
4. Ajuste no `.env` os caminhos que mudaram, principalmente o `FORMATADO_DIR`. Numa pasta de
   rede, use o caminho UNC (`\\servidor\pasta`), **nunca** uma unidade mapeada (`Z:`): a tarefa
   agendada roda sem usuário conectado e não enxerga unidades mapeadas.
5. Confirme que o usuário da tarefa agendada tem permissão de escrita na pasta de saída.
6. Rode a validação (passos 2, 4 e 8 são o mínimo) e confira que o `--planejar` não propõe
   reenviar nada que já saiu.
7. Crie a tarefa agendada na máquina nova, com o caminho novo. Veja
   [agendamento.md](agendamento.md#criar-a-tarefa).

## Atualizar

```powershell
git pull
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m pytest
```

Se o `requirements.txt` mudou a versão do Playwright, rode também
`.venv\Scripts\playwright install chromium`.
