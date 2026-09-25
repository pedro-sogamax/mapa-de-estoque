"""Converte o relatorio que o Geweb entrega num .xlsx de verdade, ja formatado.

O Geweb chama o arquivo de ".xls", mas o conteudo e HTML com estilo do Excel — abre no
Excel, so que sem formatacao nenhuma e com os numeros gravados como texto em pt-BR
("1.269,92"). Ate hoje alguem abria esse arquivo e formatava a mao antes de mandar para a
industria.

Este modulo faz esse trabalho. O layout de saida foi medido celula a celula em
docs/referencia/MAPA.xlsx, que e justamente um relatorio deste script formatado a mao (a aba dele se
chama "0017_HERBAMED_2026-07").

Como utilitario de conferencia, sem abrir o Geweb:

    python -m src.formatador downloads\\...\\0001_EUROFARMA_RX_2026-07.xls saida.xlsx
"""

from __future__ import annotations

import html
import logging
import re
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter

log = logging.getLogger(__name__)


class FormatacaoFalhou(Exception):
    """O arquivo baixado nao tem a cara do relatorio Compras/Vendas por Produto."""


# O Geweb nao fecha a tag <table>, entao nada de procurar a tabela: varremos linha a linha.
_LINHA = re.compile(r"<tr\b.*?</tr>", re.S | re.I)
_CELULA = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_ESPACOS = re.compile(r"\s+")

# Colunas que sao texto mesmo quando parecem numero (codigo de barras nao e quantidade).
_COLUNAS_TEXTO = ("DESCRICAO", "MARCA")

_FONTE = Font(name="Arial", size=9)
_FONTE_CABECALHO = Font(name="Arial", size=9, bold=True)
_FINA = Side(style="thin")
_BORDA = Border(left=_FINA, right=_FINA, top=_FINA, bottom=_FINA)
_CENTRO = Alignment(horizontal="center")
_ESQUERDA = Alignment(horizontal="left")
_CABECALHO = Alignment(horizontal="center", vertical="center", wrap_text=True)

_ALTURA_CABECALHO = 35.4
_LARGURA_MINIMA = 8.0
_LARGURA_MAXIMA = 80.0
_FOLGA_LARGURA = 2.5
_MAX_NOME_ABA = 31  # limite do proprio Excel

_FORMATO_EAN = "0"
_FORMATO_VALOR = "#,##0.00_);[Red](#,##0.00)"


def _sem_acento(texto: str) -> str:
    """Compara cabecalhos sem depender da acentuacao que o Geweb mandou."""
    tabela = str.maketrans("ÁÀÃÂÄÉÈÊËÍÌÎÏÓÒÕÔÖÚÙÛÜÇ", "AAAAAEEEEIIIIOOOOOUUUUC")
    return texto.upper().translate(tabela)


def _celulas(linha: str) -> list[str]:
    """Texto de cada celula, com os espacos colapsados.

    O Geweb manda descricoes com espaco duplo ("...17 VIT E MIN  SABOR..."). Como o arquivo e
    HTML, o Excel colapsava isso ao abrir — entao o mapa que a industria recebe ha anos tem um
    espaco so. Colapsar aqui mantem o texto exatamente igual ao que sempre foi enviado.
    """
    return [_ESPACOS.sub(" ", html.unescape(_TAG.sub("", c))).strip() for c in _CELULA.findall(linha)]


def ler_relatorio(origem: Path) -> tuple[list[str], list[list[str]]]:
    """Extrai cabecalho e linhas do HTML que o Geweb entregou.

    Levanta FormatacaoFalhou se o arquivo nao for o relatorio esperado — melhor recusar do
    que gravar um .xlsx vazio ou torto e mandar isso para a industria.
    """
    bruto = origem.read_text(encoding="utf-8", errors="replace")
    linhas = [_celulas(linha) for linha in _LINHA.findall(bruto)]
    linhas = [linha for linha in linhas if linha]

    if not linhas:
        raise FormatacaoFalhou(
            f"{origem.name} nao tem nenhuma linha de tabela — o Geweb pode ter devolvido "
            "uma pagina de erro em vez do relatorio."
        )

    cabecalho, dados = linhas[0], linhas[1:]
    if not dados:
        raise FormatacaoFalhou(f"{origem.name} tem cabecalho mas nenhuma linha de produto.")

    fora_do_padrao = [i for i, linha in enumerate(dados, start=2) if len(linha) != len(cabecalho)]
    if fora_do_padrao:
        raise FormatacaoFalhou(
            f"{origem.name}: {len(fora_do_padrao)} linha(s) com numero de colunas diferente "
            f"do cabecalho ({len(cabecalho)}); a primeira e a linha {fora_do_padrao[0]}."
        )

    return cabecalho, dados


def _converter(texto: str, coluna: str) -> str | int | float:
    """Texto do HTML -> valor do Excel. Numeros vem em pt-BR: 1.269,92."""
    if _sem_acento(coluna) in _COLUNAS_TEXTO:
        return texto

    candidato = texto.replace(".", "").replace(",", ".")
    try:
        return int(candidato)
    except ValueError:
        pass
    try:
        return float(candidato)
    except ValueError:
        return texto


def _formato_da_coluna(coluna: str) -> str | None:
    nome = _sem_acento(coluna)
    if nome == "EAN":
        return _FORMATO_EAN
    if nome.endswith("VALOR"):
        return _FORMATO_VALOR
    return None


def _nome_da_aba(destino: Path) -> str:
    """O nome do arquivo vira o nome da aba, como no MAPA.xlsx formatado a mao.

    Os rotulos semanais passam de 31 caracteres ("0002_EUROFARMA_RX_SEMANAL_2026-07-27_a_
    2026-07-31" tem 48) e o Excel nao aceita — a aba trunca, o arquivo mantem o nome inteiro.
    """
    return destino.stem[:_MAX_NOME_ABA]


def formatar(origem: Path, destino: Path) -> Path:
    """Le o .xls do Geweb e grava o .xlsx formatado em `destino`. Devolve o caminho."""
    cabecalho, dados = ler_relatorio(origem)

    wb = Workbook()
    ws = wb.active
    ws.title = _nome_da_aba(destino)

    ws.append(cabecalho)
    for linha in dados:
        ws.append([_converter(valor, coluna) for valor, coluna in zip(linha, cabecalho)])

    for indice, coluna in enumerate(cabecalho, start=1):
        letra = get_column_letter(indice)
        formato = _formato_da_coluna(coluna)
        alinhamento = _ESQUERDA if _sem_acento(coluna) == "DESCRICAO" else _CENTRO
        maior = len(coluna)

        for celula in ws[letra][1:]:
            celula.font = _FONTE
            celula.border = _BORDA
            celula.alignment = alinhamento
            if formato:
                celula.number_format = formato
            maior = max(maior, len(str(celula.value if celula.value is not None else "")))

        topo = ws.cell(row=1, column=indice)
        topo.font = _FONTE_CABECALHO
        topo.border = _BORDA
        topo.alignment = _CABECALHO

        largura = min(max(maior + _FOLGA_LARGURA, _LARGURA_MINIMA), _LARGURA_MAXIMA)
        ws.column_dimensions[letra].width = largura

    ws.row_dimensions[1].height = _ALTURA_CABECALHO
    ws.freeze_panes = "A2"  # o cabecalho acompanha a rolagem
    ws.sheet_view.showGridLines = False

    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(destino))
    log.debug("Formatado %s -> %s (%d linhas)", origem.name, destino, len(dados))
    return destino


def caminho_formatado(bruto: Path, download_dir: Path, formatado_dir: Path) -> Path:
    """Espelha o caminho do arquivo bruto na arvore dos formatados, trocando a extensao.

        downloads\\EUROFARMA_RX\\2026-07\\0001_EUROFARMA_RX_2026-07.xls
        formatado\\EUROFARMA_RX\\2026-07\\0001_EUROFARMA_RX_2026-07.xlsx

    Se o arquivo estiver fora do download_dir (rodada manual apontando outro caminho), so o
    nome e aproveitado — o formatado cai na raiz de formatado_dir.
    """
    try:
        relativo = bruto.resolve().relative_to(download_dir.resolve())
    except ValueError:
        relativo = Path(bruto.name)
    return (formatado_dir / relativo).with_suffix(".xlsx")


def main(argv: list[str] | None = None) -> int:
    """Conferencia manual: converte um arquivo ja baixado, sem passar pelo Geweb."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print(__doc__)
        return 2

    origem, destino = Path(args[0]), Path(args[1])
    if not origem.exists():
        log.error("Arquivo nao encontrado: %s", origem)
        return 2

    try:
        arquivo = formatar(origem, destino)
    except FormatacaoFalhou as erro:
        log.error("%s", erro)
        return 1

    log.info("OK -> %s", arquivo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
