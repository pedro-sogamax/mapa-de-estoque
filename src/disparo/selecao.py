"""Decide o que entra na leva de envios.

Duas origens, nessa ordem:

1. **O manifesto da ultima rodada** (ultima-rodada.json) — o caso normal: "monte o que
   acabou de sair". E preciso, porque a extracao registra exatamente o que gerou.
2. **A varredura do FORMATADO_DIR por rotulo de periodo** (`--periodo 2026-07`) — para
   recuperar uma leva antiga, ou quando o manifesto nao existe.

Na varredura, quando o mesmo fabricante tem mais de um arquivo do mesmo periodo (reextracao
gera numero de sequencia novo, `0001_` e `0042_` convivem), vence o de numero maior — que e
sempre o mais recente.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.config import Config
from src.rodada import ItemDaRodada, ler as ler_rodada

log = logging.getLogger(__name__)


def _numero(arquivo: Path) -> int:
    """O prefixo de sequencia do nome (0042_MARJAN_2026-07.xlsx -> 42)."""
    prefixo = arquivo.stem.split("_", 1)[0]
    return int(prefixo) if prefixo.isdigit() else -1


def _rotulo_do_arquivo(arquivo: Path) -> str | None:
    """Rotulo do periodo lido do NOME do arquivo: 0112_MARJAN_2026-09-01_a_2026-09-13.xlsx.

    A pasta nao diz mais o periodo — ela e o mes (MARJAN\\2026-09\\), onde convivem o mensal
    e todos os acumulados daquele mes. O fabricante vem da pasta de cima, e nao de um split
    no "_", porque o proprio nome pode ter "_" (EMS_RX).
    """
    prefixo, achou, rotulo = arquivo.stem.partition(f"_{arquivo.parent.parent.name}_")
    if not achou or not prefixo.isdigit() or not rotulo:
        return None
    return rotulo


def _periodo_por_extenso(rotulo: str) -> str:
    """Rotulo do periodo -> texto para a mensagem: "2026-07" vira "julho/2026"."""
    meses = (
        "janeiro", "fevereiro", "marco", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
    )
    partes = rotulo.split("_a_")
    if len(partes) == 1 and rotulo.count("-") == 1:
        ano, mes = rotulo.split("-")
        if mes.isdigit() and 1 <= int(mes) <= 12:
            return f"{meses[int(mes) - 1]}/{ano}"
    if len(partes) == 2:
        inicio, fim = (f"{p[8:10]}/{p[5:7]}/{p[0:4]}" for p in partes)
        return f"{inicio} a {fim}"
    return rotulo


def da_ultima_rodada(cfg: Config) -> list[ItemDaRodada]:
    return ler_rodada(cfg.rodada_path)


def do_periodo(cfg: Config, rotulo: str) -> list[ItemDaRodada]:
    """Varre o FORMATADO_DIR atras dos relatorios de um periodo."""
    melhor: dict[str, Path] = {}
    for arquivo in cfg.formatado_dir.glob("*/*/*.xlsx"):
        if _rotulo_do_arquivo(arquivo) != rotulo:
            continue
        fabricante = arquivo.parent.parent.name
        atual = melhor.get(fabricante)
        if atual is None or _numero(arquivo) > _numero(atual):
            melhor[fabricante] = arquivo

    return [
        ItemDaRodada(
            fabricante=fabricante,
            motivo="manual",
            periodo=_periodo_por_extenso(rotulo),
            rotulo=rotulo,
            arquivo=arquivo,
            formatado=arquivo,
        )
        for fabricante, arquivo in sorted(melhor.items())
    ]


def periodos_disponiveis(cfg: Config) -> list[str]:
    """Rotulos que existem no FORMATADO_DIR — para sugerir na mensagem de erro."""
    rotulos = {_rotulo_do_arquivo(p) for p in cfg.formatado_dir.glob("*/*/*.xlsx")}
    return sorted((r for r in rotulos if r), reverse=True)
