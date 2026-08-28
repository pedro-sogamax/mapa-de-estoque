"""Traducao dos seletores de `seletores.py` para locators do Playwright.

Permite que o arquivo de seletores use a forma mais estavel de cada caso, sem depender
de ids gerados:

    "label=Data Inicial"                -> get_by_label("Data Inicial")
    "placeholder=Usuario"               -> get_by_placeholder("Usuario")
    "texto=Compras/Vendas"              -> get_by_text("Compras/Vendas")
    'role=button[name="Entrar"]'        -> locator(...)  (engine nativo do Playwright)
    "#IFrameConteudo"                   -> locator(...)  (CSS)
"""

from __future__ import annotations

from playwright.sync_api import FrameLocator, Locator, Page

Raiz = Page | FrameLocator | Locator


def localizar(raiz: Raiz, seletor: str) -> Locator:
    """Devolve o Locator correspondente ao seletor, dentro da raiz informada."""
    if seletor.startswith("label="):
        return raiz.get_by_label(seletor.removeprefix("label="))
    if seletor.startswith("placeholder="):
        return raiz.get_by_placeholder(seletor.removeprefix("placeholder="))
    if seletor.startswith("texto="):
        return raiz.get_by_text(seletor.removeprefix("texto="))
    return raiz.locator(seletor)
