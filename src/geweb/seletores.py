"""Seletores da interface do Geweb (sistemas.sogamax.com.br).

ESTE E O UNICO ARQUIVO QUE PRECISA SER AJUSTADO QUANDO A TELA DO GEWEB MUDAR.
Preenchido a partir de uma gravacao do `playwright codegen` do fluxo real.

FORMAS ACEITAS (ver src/geweb/localizador.py)
---------------------------------------------
    "label=Data Inicial"          <- campo ligado a um <label>: a forma mais estavel
    "placeholder=Usuario"         <- campo com placeholder
    'role=button[name="Gerar"]'   <- papel + nome acessivel
    "#IFrameConteudo"             <- CSS / id
    'a:has-text("...")'           <- CSS + texto visivel

Para regravar o fluxo:
    .venv\\Scripts\\playwright codegen --target python -o gravacao.py \\
        https://sistemas.sogamax.com.br/sistema/login.php
"""

from __future__ import annotations

PREENCHER = "<<PREENCHER>>"
"""Sentinela. Qualquer constante com este valor faz o script parar com erro claro."""


# ---------------------------------------------------------------------------
# Estrutura da pagina
# ---------------------------------------------------------------------------

IFRAME_RELATORIO: str | None = "#IFrameConteudo"
"""O Geweb renderiza todo o conteudo dentro deste iframe.

Os menus da esquerda ficam FORA dele; os filtros e o botao Gerar, DENTRO.
"""


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

LOGIN_USUARIO = "placeholder=Usuário"
LOGIN_SENHA = "placeholder=Senha"
LOGIN_BOTAO = 'role=button[name="Entrar"]'

MARCA_LOGADO = "#IFrameConteudo"
"""O iframe principal so existe depois do login — serve como prova de sessao valida."""


# ---------------------------------------------------------------------------
# Navegacao ate o relatorio (cliques na pagina principal, FORA do iframe)
# ---------------------------------------------------------------------------

MENUS_ATE_O_RELATORIO: tuple[str, ...] = (
    'a[data-link="5-0-0"], a[class~="5-0-0"]',      # Relatórios
    'a[data-link="5-2-0"], a[class~="5-2-0"]',      # Movimentação
    'a[data-link="5-2-10"], a[class~="5-2-10"]',    # Compras/Vendas por Produto
)
"""Sequencia de cliques na sidebar ate a tela do relatorio (FORA do iframe).

A sidebar e uma sanfona aninhada: cada nivel so fica visivel depois de clicar no pai.
Cada item carrega o proprio codigo de menu (menu-submenu-item), ora em data-link, ora
como classe — dai os dois seletores separados por virgula. E mais estavel que o texto,
que vem duplicado pelo <title> do icone ("Relatórios Relatórios").

    5-0-0    Relatórios
      5-2-0    Movimentação
        5-2-10   Compras/Vendas por Produto

ATENCAO ao alterar: use [class~="..."] (palavra exata), nunca [class*="..."] —
"5-0-0" e substring de "15-0-0", que e o botao Sair.

Para redescobrir os codigos apos uma mudanca de menu: python -m src.descobrir
"""


# ---------------------------------------------------------------------------
# Tipo de relatorio (widget select2)
# ---------------------------------------------------------------------------

SELECT2_TIPO_RELATORIO = "#select2-vazia_id_selecao-container"
TEXTO_TIPO_RELATORIO = "RELATÓRIO MENSAL - COMPRAS/VENDA ( VAREJO)"
"""Texto da opcao exatamente como aparece na lista (o espaco em "( VAREJO)" e do sistema)."""

CAMPO_MODELO_CARREGADO = "#vazia_nome_selecao"
"""Sinal de que o modelo salvo terminou de carregar.

Escolher o tipo de relatorio dispara um AJAX que repovoa o formulario INTEIRO com a
configuracao salva pelo comprador (empresas, tipos de movimento, grupos, layout) e
REDEFINE as datas para o mes corrente. Este campo comeca vazio e recebe o nome do modelo
quando a carga termina — preencher qualquer filtro antes disso e perder o que foi digitado.
"""


# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------

CAMPO_DATA_INICIO = "#vazia_data_ini"
CAMPO_DATA_FIM = "#vazia_data_fim"
"""Alternativa equivalente, caso os ids mudem: "label=Data Inicial" / "label=Data Final"."""

FORMATO_DATA = "%Y-%m-%d"
"""Os campos sao <input type="date">: aceitam ISO (2026-07-01), nao dd/mm/aaaa."""

SELECT2_FABRICANTE = ".select2-selection:has(#select2-vazia_id_prod_fornecedor-container)"
"""Caixa clicavel do campo "Fabricante".

O id "#select2-vazia_id_prod_fornecedor-container" (confirmado por `src.descobrir`) e o
<ul> INTERNO: como este campo aceita multipla escolha, esse <ul> comeca vazio, com altura
zero, e o Playwright recusa clicar nele. O alvo e a caixa ao redor — por isso o :has().

Assim se combina o melhor dos dois: a estabilidade do id com o elemento certo. Nao use o
seletor posicional do codegen ("div:nth-child(8) > ..."), que quebra se algum filtro for
inserido antes deste no formulario.
"""

SELECT2_BUSCA = ".select2-container--open .select2-search__field:visible"
"""Caixa de busca da lista aberta. Restrita ao dropdown aberto, entao nunca ambigua.

Sem prefixo de tag de proposito: no campo Fabricante (multipla escolha) o select2 usa
<textarea>, nao <input> — exigir "input." faz o seletor achar zero elementos.
"""

OPCAO_SELECT2 = '[role=option]:has-text("{texto}")'
"""Molde da opcao dentro da lista aberta. {texto} e substituido em tempo de execucao.

Duas escolhas deliberadas:
  - `:has-text(...)` casa por TRECHO. Com 'role=option[name="..."]' o casamento e exato,
    e "(13963)" nunca acharia a opcao "(13963) EUROFARMA".
  - `[role=option]` exclui os cabecalhos de grupo do select2, que sao role=group.

O trecho buscado inclui os parenteses — "(13963)" nao casa com "(139631) OUTRO".

No campo Fabricante a lista CONTINUA ABERTA apos cada escolha (e de multipla escolha),
o que permite marcar varios codigos em sequencia. Nao reabra a lista entre um codigo e
outro: o clique na caixa e um interruptor e fecharia tudo.
"""


# ---------------------------------------------------------------------------
# Geracao
# ---------------------------------------------------------------------------

BOTAO_GERAR = 'role=button[name="Gerar"]'
"""Abre uma aba popup e dispara o download do Excel. O popup e fechado pelo script."""

MENSAGEM_SEM_DADOS: str | None = None
"""Seletor da mensagem de "nenhum registro encontrado", se o Geweb exibir uma.

Serve para distinguir "relatorio vazio" de "script travou". Opcional — preencha se
aparecer uma mensagem desse tipo em algum fabricante sem movimento no periodo.
"""


# ---------------------------------------------------------------------------
# Validacao
# ---------------------------------------------------------------------------

_OBRIGATORIOS_LOGIN = ("LOGIN_USUARIO", "LOGIN_SENHA", "LOGIN_BOTAO", "MARCA_LOGADO")

_OBRIGATORIOS_RELATORIO = (
    "SELECT2_TIPO_RELATORIO",
    "TEXTO_TIPO_RELATORIO",
    "CAMPO_DATA_INICIO",
    "CAMPO_DATA_FIM",
    "SELECT2_FABRICANTE",
    "SELECT2_BUSCA",
    "OPCAO_SELECT2",
    "BOTAO_GERAR",
)


class SeletoresIncompletos(Exception):
    """Ha seletores ainda nao preenchidos — regrave o fluxo com o codegen."""


def validar(apenas_login: bool = False) -> None:
    """Falha cedo e com mensagem clara se algum seletor continuar como sentinela."""
    escopo = _OBRIGATORIOS_LOGIN if apenas_login else _OBRIGATORIOS_LOGIN + _OBRIGATORIOS_RELATORIO
    pendentes = [nome for nome in escopo if globals()[nome] == PREENCHER]

    if not apenas_login and not MENUS_ATE_O_RELATORIO:
        pendentes.append("MENUS_ATE_O_RELATORIO")

    if pendentes:
        raise SeletoresIncompletos(
            "Seletores nao preenchidos em src/geweb/seletores.py: " + ", ".join(pendentes)
        )
