"""Aplica os templates de texto ao relatorio extraido.

Os textos vivem em templates/email.txt e templates/whatsapp.txt, versionados fora do codigo
para o comprador ajustar a redacao sem mexer em Python.

No template de e-mail, a **primeira linha e o assunto**; o resto, depois de uma linha em
branco, e o corpo. Variaveis disponiveis: {FABRICANTE}, {PERIODO}, {COMPRADOR}, {DATA} e,
so no WhatsApp, {EMAILS} (para quem o mapa foi por e-mail).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.rodada import ItemDaRodada


class TemplateInvalido(Exception):
    """O arquivo de template nao existe ou nao tem assunto e corpo."""


@dataclass(frozen=True)
class Mensagem:
    assunto: str
    corpo: str
    # Versao HTML do mesmo corpo, com a assinatura. Vazia = a mensagem sai so em texto puro.
    corpo_html: str = ""


def _preencher(
    texto: str,
    item: ItemDaRodada,
    comprador: str,
    emails: str = "",
    cargo: str = "",
    telefones: str = "",
    email_comprador: str = "",
) -> str:
    return (
        texto.replace("{FABRICANTE}", item.fabricante)
        .replace("{PERIODO}", item.periodo)
        .replace("{COMPRADOR}", comprador)
        .replace("{DATA}", date.today().strftime("%d/%m/%Y"))
        .replace("{EMAILS}", emails)
        .replace("{CARGO}", cargo)
        .replace("{TELEFONES}", telefones)
        .replace("{EMAIL_COMPRADOR}", email_comprador)
    )


def _ler_template(caminho: Path) -> str:
    if not caminho.exists():
        raise TemplateInvalido(
            f"Template nao encontrado: {caminho}. Ele guarda o texto da mensagem e pode ser "
            "editado num bloco de notas."
        )
    return caminho.read_text(encoding="utf-8")


def para_email(
    templates_dir: Path,
    item: ItemDaRodada,
    comprador: str,
    cargo: str = "",
    telefones: str = "",
    email_comprador: str = "",
) -> Mensagem:
    """Monta assunto e corpo. O assunto sai sempre do email.txt, tambem no modo HTML.

    O email.html e opcional: sem ele a mensagem sai so em texto puro, como antes.
    """
    bruto = _ler_template(templates_dir / "email.txt")
    assunto, _, corpo = bruto.partition("\n")
    if not assunto.strip() or not corpo.strip():
        raise TemplateInvalido(
            "templates/email.txt precisa ter o assunto na primeira linha e o corpo abaixo, "
            "separados por uma linha em branco."
        )

    dados = dict(cargo=cargo, telefones=telefones, email_comprador=email_comprador)
    html = ""
    caminho_html = templates_dir / "email.html"
    if caminho_html.exists():
        html = _preencher(caminho_html.read_text(encoding="utf-8"), item, comprador, **dados)

    return Mensagem(
        assunto=_preencher(assunto.strip(), item, comprador, **dados),
        corpo=_preencher(corpo.lstrip("\n"), item, comprador, **dados),
        corpo_html=html,
    )


def para_whatsapp(templates_dir: Path, item: ItemDaRodada, comprador: str, emails: str) -> str:
    bruto = _ler_template(templates_dir / "whatsapp.txt")
    return _preencher(bruto.strip(), item, comprador, emails=emails)
