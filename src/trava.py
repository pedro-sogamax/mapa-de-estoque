"""Trava entre a rodada e a conferencia de leitura de hora em hora.

As duas gravam no mesmo dados/revisoes.json e reescrevem a mesma planilha de historico. Se
a conferencia das 08:00 caisse no meio de uma rodada de segunda demorada, uma sobrescreveria
o que a outra acabou de gravar.

A trava e um lock do sistema operacional sobre dados/rodada.trava, e nao a simples
existencia do arquivo: se o processo morrer no meio, o Windows solta o lock sozinho e a
proxima execucao nao fica presa por uma trava orfa.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import IO

log = logging.getLogger(__name__)

if os.name == "nt":
    import msvcrt

    def _travar(arquivo: IO) -> None:
        arquivo.seek(0)
        msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)

    def _destravar(arquivo: IO) -> None:
        arquivo.seek(0)
        msvcrt.locking(arquivo.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _travar(arquivo: IO) -> None:
        fcntl.flock(arquivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _destravar(arquivo: IO) -> None:
        fcntl.flock(arquivo.fileno(), fcntl.LOCK_UN)


class Trava:
    """Lock exclusivo e nao bloqueante sobre um arquivo."""

    def __init__(self, arquivo: Path) -> None:
        self.arquivo = arquivo
        self._aberto: IO | None = None

    def adquirir(self, espera_s: float = 0) -> bool:
        """Tenta travar, insistindo por ate `espera_s` segundos. Devolve True se conseguiu."""
        limite = time.monotonic() + espera_s
        while True:
            try:
                self.arquivo.parent.mkdir(parents=True, exist_ok=True)
                aberto = self.arquivo.open("a+")
            except OSError as erro:
                log.warning("Nao consegui abrir %s: %s", self.arquivo, erro)
                return False
            try:
                _travar(aberto)
            except OSError:
                aberto.close()
                if time.monotonic() >= limite:
                    return False
                time.sleep(1)
                continue
            self._aberto = aberto
            return True

    def liberar(self) -> None:
        if self._aberto is None:
            return
        try:
            _destravar(self._aberto)
        except OSError:
            pass  # fechar o arquivo solta o lock de qualquer jeito
        self._aberto.close()
        self._aberto = None
