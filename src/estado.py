"""Registro do que a agenda ja entregou, para o mensal nao se perder nem se repetir.

O mapa mensal dispara no 1o dia util do mes. Sem memoria, uma maquina desligada nesse dia
faria os 24 relatorios simplesmente nao sairem — e em silencio, porque no dia seguinte a
checagem de data recusaria a rodada.

Com este registro a regra vira "o mes anterior ainda nao foi gerado", entao a primeira
rodada de qualquer dia util recupera o que ficou para tras. O comportamento normal nao muda:
no 1o dia util nada esta registrado, e tudo roda como antes.

O arquivo (dados/estado.json) e um dicionario legivel — fabricante -> ultimo mes gerado:

    {"mensal": {"ACHE": "2026-07", "ASPEN": "2026-07"}}

Apagar o arquivo faz o mes anterior ser gerado de novo. Nao e destrutivo: cada extracao vira
um arquivo novo, com numero de sequencia proprio.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)


class EstadoDaAgenda:
    """Lembra qual foi o ultimo mes entregue a cada fabricante."""

    def __init__(self, arquivo: Path) -> None:
        self.arquivo = arquivo
        self._mensal: dict[str, str] = self._carregar()

    def _carregar(self) -> dict[str, str]:
        if not self.arquivo.exists():
            return {}
        try:
            dados = json.loads(self.arquivo.read_text(encoding="utf-8"))
            mensal = dados.get("mensal", {})
            if not isinstance(mensal, dict):
                raise ValueError("campo 'mensal' nao e um dicionario")
            return {str(k): str(v) for k, v in mensal.items()}
        except (ValueError, TypeError, json.JSONDecodeError):
            # Perder o registro custa uma repeticao do mes; travar a rodada custa o mes inteiro.
            log.warning(
                "%s ilegivel — seguindo como se nada tivesse sido gerado. "
                "O mes anterior pode sair em duplicata.",
                self.arquivo.name,
            )
            return {}

    def ja_gerou_mensal(self, fabricante: str, rotulo: str) -> bool:
        return self._mensal.get(fabricante) == rotulo

    def registrar_mensal(self, fabricante: str, rotulo: str) -> None:
        """Marca o mes como entregue. Grava na hora: uma queda no meio nao perde o registro."""
        if self._mensal.get(fabricante) == rotulo:
            return
        self._mensal[fabricante] = rotulo
        self._gravar()

    def _gravar(self) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        # Grava num temporario e troca: uma interrupcao no meio da escrita nao corrompe o
        # arquivo, ela so deixa o anterior intacto.
        temporario = self.arquivo.with_suffix(".json.tmp")
        conteudo = {"mensal": dict(sorted(self._mensal.items()))}
        temporario.write_text(json.dumps(conteudo, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporario, self.arquivo)
