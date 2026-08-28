"""Abertura do navegador, login no Geweb e reaproveitamento da sessao autenticada.

Execucao isolada para validar so o login (etapa 3 do plano):

    python -m src.geweb.session
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, sync_playwright

from src.config import Config, carregar_config
from src.geweb import seletores
from src.geweb.localizador import localizar

log = logging.getLogger(__name__)

TIMEOUT_CHECAGEM_LOGIN_MS = 5_000
"""Espera curta: so decide se a sessao salva ainda vale."""


class FalhaDeLogin(Exception):
    """Nao foi possivel autenticar no Geweb."""


class SessaoJaAberta(FalhaDeLogin):
    """O Geweb aceita uma sessao por usuario e ja existe outra ativa."""


def _capturar_avisos(page: Page) -> list[str]:
    """Guarda os alert()/confirm() do Geweb, que o Playwright descartaria em silencio.

    Sem isto, "Usuario ja logado no sistema" some sem deixar rastro e a falha aparece
    como um timeout generico.
    """
    avisos: list[str] = []

    def _tratar(dialogo) -> None:
        avisos.append(dialogo.message.strip())
        dialogo.accept()

    page.on("dialog", _tratar)
    return avisos


def esta_logado(page: Page) -> bool:
    """True se a marca de sessao autenticada esta visivel na pagina atual."""
    try:
        localizar(page, seletores.MARCA_LOGADO).first.wait_for(
            state="visible", timeout=TIMEOUT_CHECAGEM_LOGIN_MS
        )
        return True
    except PlaywrightTimeout:
        return False


def fazer_login(page: Page, cfg: Config) -> None:
    """Preenche usuario/senha e confirma que a sessao foi aberta."""
    log.info("Autenticando no Geweb como %s", cfg.usuario)
    avisos = _capturar_avisos(page)

    localizar(page, seletores.LOGIN_USUARIO).fill(cfg.usuario)
    localizar(page, seletores.LOGIN_SENHA).fill(cfg.senha)
    localizar(page, seletores.LOGIN_BOTAO).click()

    try:
        localizar(page, seletores.MARCA_LOGADO).first.wait_for(
            state="visible", timeout=cfg.timeout_ms
        )
    except PlaywrightTimeout as erro:
        recado = " | ".join(avisos)
        if "logado" in recado.lower():
            raise SessaoJaAberta(
                f"O Geweb recusou o login: {recado}. "
                "Esse ERP aceita uma sessao por usuario. Saia do Geweb no navegador, "
                "ou use um usuario dedicado a automacao."
            ) from erro
        # A senha nao entra na mensagem, e a URL pode conter dados de sessao — so o host.
        raise FalhaDeLogin(
            "Login nao concluido: a marca de sessao autenticada nao apareceu."
            + (f" O Geweb avisou: {recado}." if recado else "")
            + " Verifique GEWEB_USUARIO/GEWEB_SENHA no .env e o seletor MARCA_LOGADO. "
            "Se o Geweb pedir 2FA ou captcha, o login automatico nao e viavel — "
            "veja a secao 'Sessao manual' do README."
        ) from erro
    log.info("Login concluido")


TENTATIVAS_ABERTURA = 3
"""O Geweb as vezes demora a responder. Numa tarefa agendada ninguem esta la para repetir."""


def _abrir_pagina_inicial(page: Page, cfg: Config) -> None:
    """Abre a pagina de login, repetindo se o Geweb nao responder."""
    for tentativa in range(1, TENTATIVAS_ABERTURA + 1):
        try:
            page.goto(cfg.url_base, wait_until="domcontentloaded")
            return
        except PlaywrightTimeout:
            if tentativa == TENTATIVAS_ABERTURA:
                raise
            log.warning(
                "Geweb nao respondeu (tentativa %d de %d). Nova tentativa em 5s.",
                tentativa,
                TENTATIVAS_ABERTURA,
            )
            page.wait_for_timeout(5_000)


def garantir_login(page: Page, cfg: Config) -> None:
    """Reaproveita a sessao salva; so faz login de novo se ela tiver expirado."""
    _abrir_pagina_inicial(page, cfg)
    if esta_logado(page):
        log.info("Sessao salva ainda valida — login dispensado")
        return
    fazer_login(page, cfg)


@contextmanager
def sessao_geweb(cfg: Config, apenas_login: bool = False) -> Iterator[Page]:
    """Abre o navegador ja autenticado e devolve a pagina pronta para uso.

    A sessao e gravada em .auth/state.json ao final, para a proxima rodada nao precisar logar.
    """
    seletores.validar(apenas_login=apenas_login)
    cfg.auth_state_path.parent.mkdir(parents=True, exist_ok=True)
    estado_salvo = str(cfg.auth_state_path) if cfg.auth_state_path.exists() else None

    with sync_playwright() as playwright:
        navegador = playwright.chromium.launch(headless=cfg.headless, slow_mo=cfg.slow_mo_ms)
        contexto = navegador.new_context(accept_downloads=True, storage_state=estado_salvo)
        contexto.set_default_timeout(cfg.timeout_ms)
        page = contexto.new_page()
        try:
            garantir_login(page, cfg)
            contexto.storage_state(path=str(cfg.auth_state_path))
            yield page
        finally:
            contexto.close()
            navegador.close()


def _testar_login() -> int:
    """Valida so o login, com o navegador visivel. Retorna o codigo de saida do processo."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = carregar_config(headless_override=False)
    log.info("Config: %s", cfg.mascarar())
    with sessao_geweb(cfg, apenas_login=True) as page:
        log.info("Autenticado. Titulo da pagina: %s", page.title())
        page.wait_for_timeout(3_000)  # tempo para conferir a tela a olho
    return 0


if __name__ == "__main__":
    raise SystemExit(_testar_login())
