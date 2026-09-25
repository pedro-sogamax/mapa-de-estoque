# Mapa de Estoque

Gera os relatórios de estoque no ERP **Geweb**, formata cada um em Excel e os entrega às
indústrias parceiras por e-mail, sem ninguém clicar em nada.

O trabalho que isso substitui: abrir o Geweb, preencher o filtro de um fabricante, gerar o
relatório, abrir o `.xls` no Excel, formatar coluna a coluna, anexar num e-mail e enviar.
Quarenta e seis vezes por semana, entre quatro compradores.

| | |
|---|---|
| **Situação** | Em homologação: extração em produção, envio real travado pelo `DESTINATARIO_TESTE` |
| **Laboratórios** | 46 ativos, em 4 carteiras de compradores (setembro/2026) |
| **Rodada mais pesada** | segunda-feira: 46 relatórios em ~3min40 |
| **Canais** | e-mail (em uso) e WhatsApp (implementado, sem provedor contratado) |
| **Responsável técnico** | Pedro Veloso ([pedro@sogamax.com.br](mailto:pedro@sogamax.com.br)) |

## Como funciona

```
  Geweb                formatador           agenda              disparo
  (Playwright)         (openpyxl)           (calendário)        (SMTP / API)
      |                     |                    |                   |
  login, menus          .xls do Geweb      quem recebe hoje     e-mail com anexo,
  e filtros por      -> (HTML) vira     -> e de que período  -> travas, cotas e
  código                .xlsx formatado     (mensal/semanal)     registro por envio
      |                                                              |
      +--------> <FORMATADO_DIR>\<COMPRADOR>\<LAB>\<mês>\ <----------+
                                    |
                                    +-- logs\<AAAA-MM>.xlsx   (o que saiu e o que falhou)
```

Uma tarefa agendada roda todo dia útil às 07:00. O script decide sozinho o que cada dia
gera: o **mensal** no 1º dia útil do mês e os **semanais** nos dias cadastrados para cada
laboratório. Num dia sem envio ele sai em menos de um segundo, sem abrir o navegador.

## Quatro coisas que evitam susto

- **Rodar de novo não duplica.** Dez execuções no mesmo dia geram e enviam uma vez só.
- **Dia perdido se recupera.** Máquina desligada no 1º dia útil não faz o mensal sumir em
  silêncio: a próxima rodada o gera, avisando no log.
- **Falha isolada não derruba a rodada.** Um laboratório com problema fica de fora, nomeado
  no resumo e num e-mail de alerta; os demais seguem.
- **`DESTINATARIO_TESTE` no `.env` é a única coisa entre o sistema e as indústrias.**
  Preenchido, tudo vai para os endereços de teste. Esvaziá-lo é a ação que libera o envio
  real. Confira antes com `python -m src.disparo --dry-run`.

## Requisitos

- Windows 10/11 ou Windows Server
- Python 3.12
- Acesso de rede ao Geweb (`sistemas.sogamax.com.br`) e ao SMTP da Locaweb
  (`email-ssl.com.br`, porta 465)
- Um usuário do Geweb dedicado à automação (o Geweb aceita uma sessão por usuário)

## Início rápido

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\playwright install chromium

copy .env.example .env
notepad .env                                   # credenciais do Geweb e do SMTP

.venv\Scripts\python -m src.geweb.session      # valida o login
.venv\Scripts\python -m src.main --planejar    # o que a rodada faria hoje, sem abrir o Geweb
```

O passo a passo completo, incluindo a implantação num servidor, está em
[docs/instalacao.md](docs/instalacao.md).

## Uso

```powershell
# rodada normal: o que a agenda mandar hoje
.venv\Scripts\python -m src.main

# um fabricante, um mês (use para conferir os números)
.venv\Scripts\python -m src.main --fabricante EUROFARMA_RX --mes 2026-07

# enviar o que a última extração gerou: mostra, pergunta e envia
.venv\Scripts\python -m src.disparo --dry-run
.venv\Scripts\python -m src.disparo

# o que a tarefa agendada faz: extrai sem janela e envia os e-mails
.venv\Scripts\python -m src.main --headless --enviar
```

Todas as opções estão em [docs/operacao.md](docs/operacao.md) (extração) e
[docs/envio.md](docs/envio.md) (disparo).

### Códigos de saída

| Código | Significado |
|---|---|
| `0` | Tudo certo, inclusive o dia sem envio e o `--planejar` |
| `1` | Algum fabricante falhou na extração, ou o login caiu |
| `2` | Erro de configuração que impede a rodada |
| `3` | Os relatórios saíram, mas algum envio não foi entregue |

## Documentação

| Se você quer... | Leia |
|---|---|
| instalar numa máquina nova ou migrar para um servidor | [Instalação](docs/instalacao.md) |
| mudar o `.env`, incluir, tirar ou mudar um laboratório | [Configuração](docs/configuracao.md) |
| entender a agenda, a saída e o histórico em Excel | [Operação](docs/operacao.md) |
| entender ou mexer no envio às indústrias | [Envio](docs/envio.md) |
| deixar rodando sozinho | [Agendamento](docs/agendamento.md) |
| resolver uma falha ou ajustar o script a uma tela nova do Geweb | [Solução de problemas](docs/solucao-de-problemas.md) |
| mexer no código ou rodar os testes | [Desenvolvimento](docs/desenvolvimento.md) |
| saber o que mudou e quando | [CHANGELOG](CHANGELOG.md) |

O índice completo, com o desenho do sistema e as propostas em aberto, está em
[docs/README.md](docs/README.md).

## Segurança

O `.env` e o `.auth\state.json` guardam credenciais e **nunca** devem ser versionados nem
compartilhados. Os dois estão no `.gitignore`, mas isso não protege contra cópia da pasta,
backup ou sincronização em nuvem. A pasta `dados\` guarda o registro do que já foi enviado:
perdê-la faz a automação reenviar mapas às indústrias.

## Suporte

Falhas da rodada chegam por e-mail ao endereço em `ALERTA_PARA`. Para dúvidas ou ajustes,
fale com o responsável técnico acima. Uso interno da Sogamax.
