"""Pagina local com um botao por laboratorio, para avisar pelo WhatsApp.

Nao ha API nem envio automatico: cada botao e um link wa.me que abre a conversa com o texto
ja escrito. Quem clica em enviar e a pessoa. Isso evita contratar servico, dedicar um numero
e correr risco de banimento — os problemas registrados na secao 7 do docs/disparo.md.

O link wa.me nao carrega anexo. Por isso o texto avisa que o mapa foi por e-mail, em vez de
tentar transportar o arquivo.
"""

from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Aviso:
    fabricante: str
    telefone: str
    texto: str

    @property
    def link(self) -> str:
        """wa.me exige o numero so com digitos — o "+" do E.164 sai fora."""
        return f"https://wa.me/{self.telefone.lstrip('+')}?text={quote(self.texto)}"


_PAGINA = """<!doctype html>
<meta charset="utf-8">
<title>Avisos de WhatsApp — {titulo}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: Segoe UI, system-ui, sans-serif; max-width: 46rem;
         margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }}
  h1 {{ font-size: 1.3rem; margin-bottom: .2rem; }}
  p.sub {{ margin-top: 0; opacity: .7; font-size: .9rem; }}
  ol {{ list-style: none; padding: 0; }}
  li {{ display: flex; align-items: center; gap: 1rem; padding: .7rem 0;
        border-bottom: 1px solid rgba(128,128,128,.3); }}
  a.bt {{ background: #25d366; color: #05291a; text-decoration: none; font-weight: 600;
          padding: .5rem 1.1rem; border-radius: 999px; white-space: nowrap; }}
  a.bt:hover {{ filter: brightness(1.08); }}
  .nome {{ font-weight: 600; flex: 1; }}
  .fone {{ opacity: .7; font-variant-numeric: tabular-nums; font-size: .9rem; }}
  .txt {{ width: 100%; font-size: .85rem; opacity: .75; margin: .1rem 0 0; }}
  footer {{ margin-top: 2rem; font-size: .85rem; opacity: .7; }}
</style>
<h1>Avisos de WhatsApp — {titulo}</h1>
<p class="sub">Clique no botao: o WhatsApp abre a conversa com o texto pronto.
Confira e envie. Nada e enviado por este arquivo.</p>
<ol>
{linhas}
</ol>
<footer>O mapa vai por e-mail — o WhatsApp e so o aviso de que chegou.</footer>
"""

_LINHA = """  <li>
    <span class="nome">{fabricante}</span>
    <span class="fone">{telefone}</span>
    <a class="bt" href="{link}" target="_blank" rel="noopener">Abrir WhatsApp</a>
    <p class="txt">{texto}</p>
  </li>"""


def escrever(destino: Path, titulo: str, avisos: list[Aviso]) -> Path:
    """Grava a pagina com todos os avisos da leva. Devolve o caminho."""
    linhas = "\n".join(
        _LINHA.format(
            fabricante=html.escape(aviso.fabricante),
            telefone=html.escape(aviso.telefone),
            link=html.escape(aviso.link, quote=True),
            texto=html.escape(aviso.texto),
        )
        for aviso in avisos
    )
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        _PAGINA.format(titulo=html.escape(titulo), linhas=linhas), encoding="utf-8"
    )
    log.debug("Pagina de avisos gravada em %s", destino)
    return destino
