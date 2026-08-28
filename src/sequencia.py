"""Numeracao sequencial dos relatorios gerados.

Cada arquivo baixado recebe um numero unico e crescente, que nunca se repete — nem entre
fabricantes, nem entre periodos, nem quando o mesmo relatorio e extraido de novo.

O contador vive em sequencia.json, na raiz do projeto. Se o arquivo sumir, ele se recompoe
a partir do maior numero encontrado na pasta de downloads, para nunca reaproveitar um
numero ja usado.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

_PADRAO_NUMERO = re.compile(r"^(\d+)_")


class Sequencia:
    """Contador persistente. Grava a cada retirada, para uma queda no meio nao repetir numero."""

    def __init__(self, arquivo: Path, pasta_downloads: Path) -> None:
        self.arquivo = arquivo
        self.pasta_downloads = pasta_downloads
        self._ultimo = self._carregar()

    def _carregar(self) -> int:
        gravado = 0
        if self.arquivo.exists():
            try:
                gravado = int(json.loads(self.arquivo.read_text(encoding="utf-8"))["ultimo"])
            except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                log.warning("%s ilegivel; recompondo pelo conteudo de downloads.", self.arquivo.name)

        # Rede de seguranca: mesmo com o contador perdido, nunca repetir um numero existente.
        nos_arquivos = self._maior_numero_ja_usado()
        if nos_arquivos > gravado:
            log.warning(
                "Contador em %s (%d) atras dos arquivos ja gerados (%d). Seguindo pelo maior.",
                self.arquivo.name,
                gravado,
                nos_arquivos,
            )
        return max(gravado, nos_arquivos)

    def _maior_numero_ja_usado(self) -> int:
        if not self.pasta_downloads.exists():
            return 0
        numeros = [
            int(casamento.group(1))
            for caminho in self.pasta_downloads.rglob("*")
            if caminho.is_file() and (casamento := _PADRAO_NUMERO.match(caminho.name))
        ]
        return max(numeros, default=0)

    def _gravar(self) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        self.arquivo.write_text(json.dumps({"ultimo": self._ultimo}), encoding="utf-8")

    def proximo(self) -> int:
        """Reserva e devolve o proximo numero, ja persistido."""
        self._ultimo += 1
        self._gravar()
        return self._ultimo

    def devolver(self, numero: int) -> None:
        """Cancela uma reserva que nao virou arquivo, para nao abrir buraco na sequencia.

        So tem efeito se for o ultimo numero reservado — numeros mais antigos ja podem ter
        sido usados por outra extracao.
        """
        if numero == self._ultimo:
            self._ultimo -= 1
            self._gravar()
