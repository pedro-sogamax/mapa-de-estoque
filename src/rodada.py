"""Manifesto da ultima extracao — a ponte entre a rodada e o comando de disparo.

`main.py` grava aqui o que acabou de extrair; `python -m src.disparo` le isto para saber
quais arquivos montar. E so um registro do que ja aconteceu: gravar o manifesto nao envia
nada nem dispara nada. Quem envia e o comando de disparo — a mao, ou chamado logo depois da
extracao pelo `src.main --enviar`, que le este mesmo arquivo pelo caminho normal.

O formato (ultima-rodada.json, na raiz) e legivel de proposito, para conferir num editor:

    {
      "em": "2026-08-18T07:12:33",
      "itens": [
        {"fabricante": "MARJAN", "motivo": "semanal/segunda",
         "periodo": "01/08/2026 a 16/08/2026", "rotulo": "2026-08-01_a_2026-08-16",
         "arquivo": "...\0056_MARJAN_....xls", "formatado": "...\0056_MARJAN_....xlsx"}
      ]
    }
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ItemDaRodada:
    """Um relatorio extraido com sucesso, pronto para virar mensagem."""

    fabricante: str
    motivo: str
    periodo: str
    rotulo: str
    arquivo: Path
    formatado: Path | None = None

    @property
    def anexo(self) -> Path:
        """O que vai anexado: o .xlsx formatado; o bruto so se a formatacao tiver falhado."""
        return self.formatado or self.arquivo


def gravar(caminho: Path, itens: list[ItemDaRodada]) -> None:
    """Regrava o manifesto com a rodada que acabou de terminar.

    Grava em temporario e troca, como src/estado.py: uma interrupcao no meio nao deixa um
    manifesto pela metade, so mantem o anterior.
    """
    conteudo = {
        "em": datetime.now().isoformat(timespec="seconds"),
        "itens": [
            {
                "fabricante": item.fabricante,
                "motivo": item.motivo,
                "periodo": item.periodo,
                "rotulo": item.rotulo,
                "arquivo": str(item.arquivo),
                "formatado": str(item.formatado) if item.formatado else None,
            }
            for item in itens
        ],
    }
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(".json.tmp")
    temporario.write_text(json.dumps(conteudo, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporario, caminho)


def ler(caminho: Path) -> list[ItemDaRodada]:
    """Devolve os itens da ultima rodada, ou lista vazia se nao houver manifesto legivel."""
    if not caminho.exists():
        return []
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        itens = dados.get("itens", [])
        if not isinstance(itens, list):
            raise ValueError("campo 'itens' nao e uma lista")
    except (ValueError, TypeError, json.JSONDecodeError):
        # Sem manifesto o disparo ainda funciona com --periodo, entao avisar basta.
        log.warning("%s ilegivel — use --periodo para escolher a leva.", caminho.name)
        return []

    return [
        ItemDaRodada(
            fabricante=str(item["fabricante"]),
            motivo=str(item.get("motivo", "")),
            periodo=str(item.get("periodo", "")),
            rotulo=str(item.get("rotulo", "")),
            arquivo=Path(item["arquivo"]),
            formatado=Path(item["formatado"]) if item.get("formatado") else None,
        )
        for item in itens
        if isinstance(item, dict) and item.get("fabricante") and item.get("arquivo")
    ]
