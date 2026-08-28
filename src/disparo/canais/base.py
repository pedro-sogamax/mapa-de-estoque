"""Contrato entre o roteador e os canais de envio.

Duas regras que sustentam o desenho (secao 2 do docs/disparo.md):

1. **O canal nao sabe de agenda nem de Geweb.** Recebe destino, texto e caminho do anexo.
2. **O roteador nao sabe de SMTP nem de HTTP.** Decide o que, para quem, e se ja foi enviado.

Trocar de provedor e escrever outro modulo aqui dentro; nada mais muda.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class FalhaNoEnvio(Exception):
    """O canal nao conseguiu entregar. Nao derruba a leva — o proximo laboratorio segue."""


class FalhaFatal(FalhaNoEnvio):
    """A leva inteira precisa parar.

    Reservada para o que nao adianta tentar de novo e cujo retentar e nocivo: credencial
    recusada, acima de tudo. Repetir um login errado 24 vezes e o padrao que faz um provedor
    bloquear a conta — melhor abortar na primeira.
    """


@dataclass(frozen=True)
class Destino:
    """Para quem vai. `emails`/`copia` para o canal de e-mail, `telefones` para o WhatsApp."""

    fabricante: str
    emails: tuple[str, ...] = ()
    copia: tuple[str, ...] = ()
    telefones: tuple[str, ...] = ()
    # Resolvido pelo roteador: o comprador deste laboratorio, ou o RESPONDER_PARA do .env.
    # Viaja aqui porque o canal nao conhece fabricante nem cadastro — so o destino.
    responder_para: str = ""


@dataclass(frozen=True)
class Mensagem:
    assunto: str
    corpo: str
    # Mesmo corpo em HTML, com a assinatura. Vazio = a mensagem sai so em texto puro.
    # O canal de WhatsApp ignora este campo; so o e-mail o usa.
    corpo_html: str = ""


@dataclass(frozen=True)
class Envio:
    """Prova de que saiu. `identificadores` guarda o que o provedor devolveu.

    E o que vai para o envios.json: sem um id do provedor nao ha como conferir depois se a
    mensagem realmente saiu.
    """

    canal: str
    destinatarios: tuple[str, ...]
    identificadores: tuple[str, ...] = field(default_factory=tuple)

    @property
    def resumo(self) -> str:
        return ", ".join(self.identificadores) or ", ".join(self.destinatarios)


class Canal(Protocol):
    """O que todo canal precisa saber fazer."""

    nome: str

    def disponivel(self) -> str | None:
        """None se da para usar; senao, a razao (falta credencial, provedor desconhecido)."""
        ...

    def enviar(self, destino: Destino, mensagem: Mensagem, anexo: Path | None) -> Envio:
        """Entrega. Levanta FalhaNoEnvio se nao conseguir."""
        ...
