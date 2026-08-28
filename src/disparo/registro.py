"""Registro do que ja foi entregue (envios.json).

Espelha src/estado.py: mesmo formato legivel, mesma gravacao atomica, mesma tolerancia a
arquivo corrompido.

Grava **a cada envio**, nao ao fim da leva. Uma queda no meio de 24 mensagens nao pode fazer
a rodada seguinte reenviar o que ja saiu — reenvio para a industria e visivel e constrangedor,
diferente de um download repetido.

Cada entrada guarda o identificador que o provedor devolveu (Message-ID do SMTP, messageId da
API de WhatsApp). Sem isso nao ha como conferir depois se a mensagem realmente saiu.

    {
      "enviados": {
        "MARJAN|2026-07|email":    {"em": "2026-08-01T07:12:33", "id": "<...@sogamax.com.br>"},
        "MARJAN|2026-07|whatsapp": {"em": "2026-08-01T07:12:40", "id": "D241XXXX732339502B68"}
      }
    }
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)


class RegistroDeEnvios:
    """Lembra o que ja foi entregue, para nao mandar duas vezes para a industria."""

    def __init__(self, arquivo: Path) -> None:
        self.arquivo = arquivo
        self._enviados: dict[str, dict[str, str]] = self._carregar()

    @staticmethod
    def chave(fabricante: str, rotulo: str, canal: str) -> str:
        return f"{fabricante}|{rotulo}|{canal}"

    def _carregar(self) -> dict[str, dict[str, str]]:
        if not self.arquivo.exists():
            return {}
        try:
            dados = json.loads(self.arquivo.read_text(encoding="utf-8"))
            enviados = dados.get("enviados", {})
            if not isinstance(enviados, dict):
                raise ValueError("campo 'enviados' nao e um dicionario")
        except (ValueError, TypeError, json.JSONDecodeError):
            # Aqui a escolha e o contrario da do estado.py: perder este registro faria
            # reenviar para a industria. Melhor recusar a leva do que duplicar o envio.
            raise RegistroIlegivel(
                f"{self.arquivo} esta ilegivel. Como ele e o que impede reenviar o mesmo mapa "
                "duas vezes, a leva foi interrompida. Confira o arquivo (ou apague-o, "
                "sabendo que tudo sera considerado nao enviado)."
            ) from None
        return {str(k): dict(v) if isinstance(v, dict) else {} for k, v in enviados.items()}

    def enviado_em(self, fabricante: str, rotulo: str, canal: str) -> str | None:
        entrada = self._enviados.get(self.chave(fabricante, rotulo, canal))
        return entrada.get("em") if entrada else None

    def registrar(self, fabricante: str, rotulo: str, canal: str, identificador: str) -> None:
        """Marca como entregue e grava na hora — uma queda depois disto nao reenvia."""
        self._enviados[self.chave(fabricante, rotulo, canal)] = {
            "em": datetime.now().isoformat(timespec="seconds"),
            "id": identificador,
        }
        self._gravar()

    def _gravar(self) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        temporario = self.arquivo.with_suffix(".json.tmp")
        conteudo = {"enviados": dict(sorted(self._enviados.items()))}
        temporario.write_text(json.dumps(conteudo, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporario, self.arquivo)


class RegistroIlegivel(Exception):
    """envios.json corrompido — a leva para, para nao arriscar reenvio."""
