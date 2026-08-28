"""Configuracao unica do log dos comandos.

Tres comandos montavam o proprio log com o mesmo codigo copiado — src/main.py,
src/disparo/__main__.py e src/descobrir.py — e nenhum deles tinha rotacao: execucao.log
ja passava de 200 KB e disparo.log de 100 KB, crescendo para sempre numa maquina que
ninguem limpa. Arquivo de log sem teto nunca e problema ate o dia em que e.

Cada comando continua com o SEU arquivo (execucao.log, disparo.log, descoberta.log): sao
processos separados, e o disparo roda em subprocess justamente para nao misturar os dois.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
PASTA_LOGS = RAIZ_PROJETO / "logs"

# 1 MB por arquivo e 5 geracoes guardadas: cabe varios meses de rodadas em ~6 MB, e o
# arquivo atual nunca fica grande demais para abrir no Bloco de Notas quando algo falha.
TAMANHO_MAXIMO_BYTES = 1_000_000
GERACOES = 5

FORMATO = "%(asctime)s %(levelname)-7s %(message)s"


def _forcar_utf8_no_console() -> None:
    """O console do Windows abre em cp1252 e transforma cada travessao e acento em "?".

    O arquivo de log ja era UTF-8, entao sem isto a MESMA linha sai legivel no arquivo e
    quebrada na tela — o que confunde justamente na hora de ler uma mensagem de erro.
    """
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8")
        except (AttributeError, OSError, ValueError):
            # stdout redirecionado para algo que nao aceita reconfigure: o log em arquivo
            # continua correto, so a tela fica como estava. Nao vale derrubar a rodada.
            pass


def configurar(
    arquivo: str,
    nivel: int = logging.INFO,
    formato: str = FORMATO,
    reiniciar: bool = False,
) -> Path:
    """Liga o log em stdout e em logs/<arquivo>, com rotacao. Devolve o caminho do arquivo.

    `reiniciar=True` apaga o log anterior antes de comecar — usado so pela descoberta, que
    e um diagnostico da tela atual do Geweb: ali interessa a ultima execucao, nao o
    historico.
    """
    PASTA_LOGS.mkdir(parents=True, exist_ok=True)
    destino = PASTA_LOGS / arquivo

    if reiniciar:
        destino.unlink(missing_ok=True)

    _forcar_utf8_no_console()

    logging.basicConfig(
        level=nivel,
        format=formato,
        handlers=[
            logging.StreamHandler(sys.stdout),
            RotatingFileHandler(
                destino,
                maxBytes=TAMANHO_MAXIMO_BYTES,
                backupCount=GERACOES,
                encoding="utf-8",
            ),
        ],
    )
    return destino
