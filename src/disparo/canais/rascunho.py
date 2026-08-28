"""Canal Rascunho — monta em disco, nao envia.

Era o comportamento padrao do comando antes de existirem os canais de verdade. Continua
valendo por dois motivos:

- **contingencia**: se o SMTP recusar ou a sessao do WhatsApp cair, o comprador ainda consegue
  entregar o mapa no mesmo dia, abrindo os .eml e clicando em Enviar;
- **homologacao**: da para conferir destinatarios e redacao sem tocar em ninguem.

Acesso por `python -m src.disparo --rascunho`.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.config import Config
from src.disparo import eml, whatsapp
from src.disparo.canais.base import Destino, Envio, Mensagem

log = logging.getLogger(__name__)


class CanalRascunhoEmail:
    """Grava um .eml por laboratorio, que o Outlook abre pronto para enviar."""

    nome = "email"

    def __init__(self, cfg: Config, pasta: Path) -> None:
        self.cfg = cfg
        self.pasta = pasta

    def disponivel(self) -> str | None:
        return None  # escrever arquivo nao depende de credencial nenhuma

    def enviar(self, destino: Destino, mensagem: Mensagem, anexo: Path | None) -> Envio:
        arquivo = eml.escrever(
            destino=self.pasta / eml.nome_de_arquivo(destino.fabricante),
            para=list(destino.emails),
            copia=list(destino.copia),
            assunto=mensagem.assunto,
            corpo=mensagem.corpo,
            anexo=anexo,
            remetente=self.cfg.remetente,
            responder_para=destino.responder_para or self.cfg.responder_para,
            corpo_html=mensagem.corpo_html,
            assinatura_dir=self.cfg.templates_dir / "assinatura",
        )
        return Envio(
            canal=self.nome, destinatarios=tuple(destino.emails), identificadores=(arquivo.name,)
        )


class CanalRascunhoWhatsApp:
    """Acumula os avisos e grava uma pagina com um link wa.me por laboratorio.

    O link nao carrega arquivo — por isso o rascunho de WhatsApp e sempre so o aviso, mesmo
    para laboratorios marcados com `whatsapp_anexo: true`. Nesses casos o resumo avisa.
    """

    nome = "whatsapp"

    def __init__(self, cfg: Config, pasta: Path, titulo: str) -> None:
        self.cfg = cfg
        self.pasta = pasta
        self.titulo = titulo
        self._avisos: list[whatsapp.Aviso] = []

    def disponivel(self) -> str | None:
        return None

    def enviar(self, destino: Destino, mensagem: Mensagem, anexo: Path | None) -> Envio:
        for telefone in destino.telefones:
            self._avisos.append(whatsapp.Aviso(destino.fabricante, telefone, mensagem.corpo))
        return Envio(
            canal=self.nome, destinatarios=tuple(destino.telefones), identificadores=("wa.me",)
        )

    def finalizar(self) -> Path | None:
        """Grava a pagina com tudo que foi acumulado. None se nao houve aviso nenhum."""
        if not self._avisos:
            return None
        return whatsapp.escrever(self.pasta / "whatsapp.html", self.titulo, self._avisos)
