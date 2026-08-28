"""Montagem da mensagem de e-mail, e a gravacao dela como arquivo .eml.

Duas saidas para a mesma mensagem:

- `montar_mensagem` devolve o EmailMessage, usado pelo canal SMTP para enviar de verdade;
- `escrever` grava esse mesmo objeto em disco como .eml, o canal Rascunho.

O header **X-Unsent: 1** so entra no arquivo. Ele existe para o Outlook abrir o .eml em modo
de composicao, com botao Enviar, em vez de tratar como mensagem recebida. Numa mensagem
enviada de verdade ele nao faz sentido — e por isso o parametro `rascunho`.
"""

from __future__ import annotations

import logging
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

log = logging.getLogger(__name__)

_MIME_XLSX = ("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet")
_MIME_XLS = ("application", "vnd.ms-excel")

_INVALIDOS = r'<>:"/\|?*'

# Imagens da assinatura, embutidas na mensagem. A chave e o cid usado no email.html
# (src="cid:logo"); o valor e o arquivo em templates/assinatura/.
# Embutir, e nao apontar para uma URL, e o que faz a assinatura aparecer sem o cliente
# precisar "baixar imagens" — e o que evita que ela seja lida como pixel de rastreamento.
IMAGENS_ASSINATURA = {
    "logo": "logo.png",
    "facebook": "facebook.png",
    "linkedin": "linkedin.png",
    "instagram": "instagram.png",
    "site": "site.jpg",
}


def nome_de_arquivo(fabricante: str) -> str:
    """Nome do .eml a partir do laboratorio, sem o que o Windows recusa."""
    limpo = "".join("-" if c in _INVALIDOS else c for c in fabricante).strip()
    return f"{limpo or 'sem-nome'}.eml"


def mime_do_anexo(anexo: Path) -> tuple[str, str]:
    return _MIME_XLSX if anexo.suffix.lower() == ".xlsx" else _MIME_XLS


def montar_mensagem(
    para: list[str],
    copia: list[str],
    assunto: str,
    corpo: str,
    anexo: Path | None,
    remetente: str = "",
    responder_para: str = "",
    rascunho: bool = True,
    corpo_html: str = "",
    assinatura_dir: Path | None = None,
) -> EmailMessage:
    """Monta a mensagem completa, com anexo. Nao envia nem grava nada.

    Com `corpo_html`, a mensagem sai em duas versoes na mesma entrega (multipart/alternative):
    o texto puro e o HTML com a assinatura. Quem nao renderiza HTML — cliente antigo, leitor
    de tela, filtro corporativo — continua lendo o texto, com a mesma informacao.

    As imagens da assinatura sao anexadas ao corpo HTML como `related`, com o Content-ID que
    o template referencia. Isso precisa acontecer ANTES do anexo do relatorio: `add_attachment`
    transforma a mensagem em multipart/mixed, e depois disso o payload do HTML nao esta mais
    onde `add_related` o procura.
    """
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["To"] = ", ".join(para)
    if copia:
        msg["Cc"] = ", ".join(copia)
    if remetente:
        msg["From"] = remetente
    if responder_para:
        msg["Reply-To"] = responder_para
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=_dominio(remetente))
    if rascunho:
        # Ver o docstring do modulo: sem isto o Outlook abre em modo leitura.
        msg["X-Unsent"] = "1"

    msg.set_content(corpo)

    if corpo_html:
        msg.add_alternative(corpo_html, subtype="html")
        if assinatura_dir is not None:
            # get_payload()[1] e a parte HTML recem-adicionada; e nela que as imagens entram.
            parte_html = msg.get_payload()[1]
            for cid, arquivo in IMAGENS_ASSINATURA.items():
                caminho = assinatura_dir / arquivo
                if not caminho.exists():
                    log.warning("Imagem da assinatura ausente: %s", caminho)
                    continue
                subtipo = "jpeg" if caminho.suffix.lower() in (".jpg", ".jpeg") else "png"
                parte_html.add_related(
                    caminho.read_bytes(), maintype="image", subtype=subtipo, cid=f"<{cid}>"
                )

    if anexo is not None:
        tipo, subtipo = mime_do_anexo(anexo)
        msg.add_attachment(
            anexo.read_bytes(), maintype=tipo, subtype=subtipo, filename=anexo.name
        )
    return msg


def _dominio(remetente: str) -> str | None:
    """Dominio do Message-ID. Sem remetente, deixa o Python usar o nome da maquina."""
    if "@" in remetente:
        return remetente.rsplit("@", 1)[1].strip(">")
    return None


def escrever(
    destino: Path,
    para: list[str],
    copia: list[str],
    assunto: str,
    corpo: str,
    anexo: Path | None,
    remetente: str = "",
    responder_para: str = "",
    corpo_html: str = "",
    assinatura_dir: Path | None = None,
) -> Path:
    """Grava a mensagem como .eml, para abrir no Outlook. Devolve o caminho.

    O rascunho leva a mesma assinatura do envio automatico: o comprador abre o arquivo no
    Outlook e ve exatamente o que a industria veria, sem ter que colar a assinatura a mao.
    """
    msg = montar_mensagem(
        para=para,
        copia=copia,
        assunto=assunto,
        corpo=corpo,
        anexo=anexo,
        remetente=remetente,
        responder_para=responder_para,
        rascunho=True,
        corpo_html=corpo_html,
        assinatura_dir=assinatura_dir,
    )
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(msg.as_bytes())
    log.debug("Rascunho gravado em %s", destino)
    return destino
