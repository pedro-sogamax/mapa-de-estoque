"""Canal de WhatsApp por API nao oficial.

O provedor ainda nao foi contratado, entao o adaptador e por PERFIL: as rotas e os nomes dos
campos ficam numa tabela, e trocar de provedor e acrescentar uma entrada — sem mexer no
roteador nem no resto do canal.

O perfil `zapi` foi preenchido a partir da documentacao oficial da Z-API:

    texto     POST {base}/instances/{instancia}/token/{token}/send-text
              {"phone": "5511999999999", "message": "..."}
    documento POST {base}/instances/{instancia}/token/{token}/send-document/xlsx
              {"phone": ..., "document": "data:<mime>;base64,...", "fileName": ..., "caption": ...}
    header    Client-Token: <token da conta>
    resposta  {"zaapId": ..., "messageId": ..., "id": ...}

O telefone vai so com digitos (DDI+DDD+numero). O cadastro guarda em E.164 ("+5511..."), e o
"+" sai aqui.

> NAO implemente outro provedor por analogia com este. Uzapi, Z-API e similares divergem nos
> nomes dos campos e nas rotas; cada um precisa do seu perfil, conferido na documentacao
> oficial. E a advertencia registrada na secao 7 do docs/disparo.md.

RISCO, repetido de proposito: isto contraria os termos de uso da Meta e o numero pode ser
banido sem aviso. Use um numero dedicado, nunca o pessoal do comprador nem o principal da
empresa. A sessao tambem cai sozinha e so volta com QR Code presencial — por isso toda falha
aqui e ruidosa, nunca silenciosa.
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from src.config import Config
from src.disparo.canais.base import Destino, Envio, FalhaNoEnvio, Mensagem
from src.disparo.eml import mime_do_anexo

log = logging.getLogger(__name__)

_TIMEOUT_S = 30


@dataclass(frozen=True)
class Perfil:
    """As rotas e os nomes de campo de um provedor."""

    rota_texto: str
    rota_documento: str
    campo_telefone: str
    campo_texto: str
    campo_documento: str
    campo_nome_arquivo: str
    campo_legenda: str
    header_token: str
    campos_id: tuple[str, ...]


PERFIS = {
    "zapi": Perfil(
        rota_texto="{base}/instances/{instancia}/token/{token}/send-text",
        rota_documento="{base}/instances/{instancia}/token/{token}/send-document/{extensao}",
        campo_telefone="phone",
        campo_texto="message",
        campo_documento="document",
        campo_nome_arquivo="fileName",
        campo_legenda="caption",
        header_token="Client-Token",
        campos_id=("messageId", "zaapId", "id"),
    )
}


def so_digitos(telefone: str) -> str:
    """+5511988887777 -> 5511988887777. E o formato que a API espera."""
    return "".join(c for c in telefone if c.isdigit())


class CanalWhatsApp:
    """Envia texto e, quando o laboratorio pede, o proprio arquivo."""

    nome = "whatsapp"

    def __init__(self, cfg: Config, com_anexo: bool = False) -> None:
        self.cfg = cfg
        self.com_anexo = com_anexo
        self.perfil = PERFIS.get(cfg.whatsapp_provedor)

    def disponivel(self) -> str | None:
        if self.perfil is None:
            return (
                f"provedor {self.cfg.whatsapp_provedor!r} desconhecido "
                f"(conhecidos: {', '.join(sorted(PERFIS))})"
            )
        if not self.cfg.whatsapp_instancia or not self.cfg.whatsapp_token:
            return "ZAPI_INSTANCIA/ZAPI_TOKEN nao configurados no .env (provedor nao contratado)"
        return None

    def _url(self, rota: str, **extra: str) -> str:
        return rota.format(
            base=self.cfg.whatsapp_url_base,
            instancia=self.cfg.whatsapp_instancia,
            token=self.cfg.whatsapp_token,
            **extra,
        )

    def _postar(self, url: str, corpo: dict) -> dict:
        dados = json.dumps(corpo).encode("utf-8")
        cabecalhos = {"Content-Type": "application/json"}
        if self.cfg.whatsapp_client_token:
            cabecalhos[self.perfil.header_token] = self.cfg.whatsapp_client_token

        requisicao = urllib.request.Request(url, data=dados, headers=cabecalhos, method="POST")
        try:
            with urllib.request.urlopen(requisicao, timeout=_TIMEOUT_S) as resposta:
                return json.loads(resposta.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as erro:
            detalhe = erro.read().decode("utf-8", errors="replace")[:300]
            raise FalhaNoEnvio(
                f"O provedor respondeu {erro.code}: {detalhe or erro.reason}. "
                "Se for 401/403, confira o token; se falar em sessao, o QR Code caiu."
            ) from erro
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as erro:
            raise FalhaNoEnvio(f"Nao consegui falar com o provedor: {erro}") from erro

    def _identificador(self, resposta: dict) -> str:
        for campo in self.perfil.campos_id:
            if resposta.get(campo):
                return str(resposta[campo])
        return "sem id"

    def enviar(self, destino: Destino, mensagem: Mensagem, anexo: Path | None) -> Envio:
        indisponivel = self.disponivel()
        if indisponivel:
            raise FalhaNoEnvio(indisponivel)
        if not destino.telefones:
            raise FalhaNoEnvio(f"{destino.fabricante} nao tem telefone de destino.")

        identificadores: list[str] = []
        for telefone in destino.telefones:
            numero = so_digitos(telefone)
            if self.com_anexo and anexo is not None:
                resposta = self._enviar_documento(numero, mensagem.corpo, anexo)
            else:
                resposta = self._postar(
                    self._url(self.perfil.rota_texto),
                    {self.perfil.campo_telefone: numero, self.perfil.campo_texto: mensagem.corpo},
                )
            identificadores.append(self._identificador(resposta))
            log.debug("WhatsApp para %s: %s", telefone, identificadores[-1])

        return Envio(
            canal=self.nome,
            destinatarios=tuple(destino.telefones),
            identificadores=tuple(identificadores),
        )

    def _enviar_documento(self, numero: str, legenda: str, anexo: Path) -> dict:
        tipo, subtipo = mime_do_anexo(anexo)
        conteudo = base64.b64encode(anexo.read_bytes()).decode("ascii")
        url = self._url(self.perfil.rota_documento, extensao=anexo.suffix.lstrip(".").lower())
        return self._postar(
            url,
            {
                self.perfil.campo_telefone: numero,
                self.perfil.campo_documento: f"data:{tipo}/{subtipo};base64,{conteudo}",
                self.perfil.campo_nome_arquivo: anexo.name,
                self.perfil.campo_legenda: legenda,
            },
        )
