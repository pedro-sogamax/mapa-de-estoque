"""Diagnostico da interface do Geweb: descobre a estrutura real do menu e dos campos.

    python -m src.descobrir                 # janela visivel
    python -m src.descobrir --headless      # sem janela

Faz login e grava em logs/descoberta.log:
  1. todos os links do menu relacionados ao relatorio, com visibilidade e href;
  2. os menus sanfona (aria-expanded) que talvez precisem ser abertos antes;
  3. se conseguir entrar na tela, os ids reais dos campos select2 e dos inputs.

Nao gera relatorio nem altera nada no Geweb — so le a estrutura da pagina.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError, Page

from src.config import RAIZ_PROJETO, carregar_config
from src.geweb import seletores
from src.geweb.session import sessao_geweb

log = logging.getLogger("descobrir")

TERMO = "compras/vendas"
ALVO = "Compras/Vendas por Produto"

_JS_LINKS = """
(corpo, termo) => Array.from(document.querySelectorAll('a')).map(a => ({
    texto: (a.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 90),
    proprio: Array.from(a.childNodes)
        .filter(n => n.nodeType === 3)
        .map(n => n.textContent.trim())
        .join(' ')
        .replace(/\\s+/g, ' ')
        .trim()
        .slice(0, 90),
    href: a.getAttribute('href'),
    id: a.id,
    classe: (a.className || '').toString().slice(0, 60),
    expandido: a.getAttribute('aria-expanded'),
    visivel: !!(a.offsetParent || a.getClientRects().length),
    filhos: a.querySelectorAll('a').length,
    onclick: (a.getAttribute('onclick') || '').slice(0, 120),
})).filter(x =>
    (x.texto + ' ' + (x.href || '') + ' ' + x.onclick).toLowerCase().includes(termo)
)
"""

_JS_SANFONAS = """
(corpo) => Array.from(document.querySelectorAll('[aria-expanded], [data-bs-toggle], [data-toggle]'))
    .map(el => ({
        tag: el.tagName.toLowerCase(),
        texto: (el.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 60),
        id: el.id,
        alvo: el.getAttribute('data-bs-target') || el.getAttribute('href') || '',
        expandido: el.getAttribute('aria-expanded'),
        visivel: !!(el.offsetParent || el.getClientRects().length),
    }))
    .filter(x => x.texto && x.visivel)
"""

_JS_CAMINHO = """
(corpo, alvo) => {
    const texto = el => (el.innerText || '').replace(/\\s+/g, ' ').trim();
    const link = Array.from(document.querySelectorAll('a')).find(a => texto(a) === alvo);
    if (!link) return null;

    const cadeia = [];
    let el = link;
    let nivel = 0;
    while (el && el !== document.body && nivel < 12) {
        const anterior = el.previousElementSibling;
        const paiLink = el.parentElement ? el.parentElement.querySelector(':scope > a') : null;
        cadeia.push({
            nivel: nivel,
            tag: el.tagName.toLowerCase(),
            id: el.id,
            classe: (el.className || '').toString().slice(0, 70),
            visivel: !!(el.offsetParent || el.getClientRects().length),
            irmaoAnterior: anterior && anterior.tagName === 'A' ? texto(anterior).slice(0, 50) : '',
            linkDoPai: paiLink && paiLink !== el ? texto(paiLink).slice(0, 50) : '',
        });
        el = el.parentElement;
        nivel += 1;
    }
    return cadeia;
}
"""

_JS_TOPO = """
(corpo) => Array.from(document.querySelectorAll('.sb-item-list > .sb-item > a')).map(a => {
    const r = a.getBoundingClientRect();
    const s = getComputedStyle(a);
    return {
        texto: (a.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 40),
        textContent: (a.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 40),
        largura: Math.round(r.width),
        altura: Math.round(r.height),
        display: s.display,
        visibility: s.visibility,
        opacity: s.opacity,
        pointer: s.pointerEvents,
        html: a.outerHTML.replace(/\\s+/g, ' ').slice(0, 240),
    };
})
"""

_JS_SIDEBAR_VISIVEL = """
(corpo) => Array.from(document.querySelectorAll('.sidebar a'))
    .filter(a => a.offsetParent || a.getClientRects().length)
    .map(a => ({
        texto: (a.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 45),
        codigo: a.getAttribute('data-link') || (a.className || '').toString().match(/\\d+-\\d+-\\d+/)?.[0] || '',
    }))
"""

_JS_SELECT2 = """
(corpo) => Array.from(document.querySelectorAll("[id^='select2-'][id$='-container']"))
    .map((el, i) => {
        const campo = el.closest('.form-group, .col, .mb-3, div');
        const label = campo ? (campo.querySelector('label')?.innerText || '').trim() : '';
        return { ordem: i, id: el.id, rotulo: label, texto: (el.innerText || '').trim().slice(0, 50) };
    })
"""

_JS_INPUTS = """
(corpo) => Array.from(document.querySelectorAll('input:not([type=hidden])'))
    .map(el => ({
        id: el.id,
        nome: el.name,
        tipo: el.type,
        placeholder: el.placeholder,
        rotulo: (el.labels && el.labels[0] ? el.labels[0].innerText : '').trim(),
    }))
"""


def _configurar_log() -> Path:
    destino = RAIZ_PROJETO / "logs" / "descoberta.log"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.unlink(missing_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(destino, encoding="utf-8")],
    )
    return destino


def _titulo(texto: str) -> None:
    log.info("")
    log.info("=" * 78)
    log.info(texto)
    log.info("=" * 78)


def _listar_menu(page: Page) -> None:
    corpo = page.locator("body").first

    _titulo(f"LINKS QUE CONTEM {TERMO!r}")
    links = corpo.evaluate(_JS_LINKS, TERMO)
    if not links:
        log.info("  (nenhum link encontrado — o menu pode ser montado por JS apos algum clique)")
    for link in links:
        marca = "VISIVEL " if link["visivel"] else "oculto  "
        log.info("  %s id=%-18s href=%s", marca, link["id"] or "-", link["href"] or "-")
        log.info("      texto completo : %s", link["texto"])
        log.info("      texto proprio  : %s", link["proprio"] or "(so tem filhos)")
        log.info("      links dentro   : %s | aria-expanded=%s", link["filhos"], link["expandido"])
        if link["onclick"]:
            log.info("      onclick        : %s", link["onclick"])
        log.info("      classe         : %s", link["classe"])

    _titulo("CAMINHO DO DOM ATE 'Compras/Vendas por Produto'")
    cadeia = corpo.evaluate(_JS_CAMINHO, ALVO)
    if not cadeia:
        log.info("  (link nao encontrado pelo texto exato %r)", ALVO)
    else:
        for no in cadeia:
            marca = "VISIVEL" if no["visivel"] else "oculto "
            log.info(
                "  nivel %-2s %s <%s> id=%s classe=%s",
                no["nivel"],
                marca,
                no["tag"],
                no["id"] or "-",
                no["classe"] or "-",
            )
            if no["irmaoAnterior"]:
                log.info("           <- link irmao anterior: %s", no["irmaoAnterior"])
            if no["linkDoPai"]:
                log.info("           <- link do pai        : %s", no["linkDoPai"])

    _titulo("MENUS DE PRIMEIRO NIVEL — HTML REAL")
    for item in corpo.evaluate(_JS_TOPO):
        log.info("  %r", item["texto"])
        log.info("      textContent : %r", item["textContent"])
        log.info(
            "      caixa       : %sx%s  display=%s visibility=%s opacity=%s pointer-events=%s",
            item["largura"],
            item["altura"],
            item["display"],
            item["visibility"],
            item["opacity"],
            item["pointer"],
        )
        log.info("      html        : %s", item["html"])

    _titulo("CONTAGEM POR SELETOR CANDIDATO")
    candidatos = [
        'a:text-is("Relatórios")',
        'a:text-is("Relatórios"):visible',
        'a:has-text("Relatórios")',
        '.sb-item-list > .sb-item > a',
        'text="Relatórios"',
    ]
    for candidato in candidatos:
        try:
            loc = page.locator(candidato)
            total = loc.count()
            visivel = loc.first.is_visible() if total else False
            log.info("  %-45s -> %s ocorrencia(s), primeira visivel=%s", candidato, total, visivel)
        except PlaywrightError as erro:
            log.info("  %-45s -> ERRO %s", candidato, str(erro).splitlines()[0])


def _listar_campos(page: Page) -> None:
    frame = page.frame_locator(seletores.IFRAME_RELATORIO or "iframe")
    corpo = frame.locator("body").first

    # A tela carrega dentro do iframe depois do clique — sem esperar, o dump sai vazio.
    _titulo("AGUARDANDO A TELA DO RELATORIO CARREGAR")
    try:
        frame.locator(seletores.SELECT2_TIPO_RELATORIO).first.wait_for(
            state="visible", timeout=30_000
        )
        log.info("  OK    %s apareceu", seletores.SELECT2_TIPO_RELATORIO)
    except PlaywrightError:
        log.info("  FALHA %s nao apareceu em 30s", seletores.SELECT2_TIPO_RELATORIO)
        log.info("        (o dump abaixo mostra o que existe de fato na tela)")
        corpo.wait_for(state="visible", timeout=10_000)

    _titulo("CAMPOS SELECT2 (na ordem em que aparecem na tela)")
    for campo in corpo.evaluate(_JS_SELECT2):
        log.info("  #%s", campo["id"])
        log.info("      rotulo : %s", campo["rotulo"] or "(sem label)")
        log.info("      valor  : %s", campo["texto"])

    _titulo("INPUTS VISIVEIS")
    for campo in corpo.evaluate(_JS_INPUTS):
        log.info(
            "  id=%-28s tipo=%-9s rotulo=%s",
            campo["id"] or "-",
            campo["tipo"],
            campo["rotulo"] or campo["placeholder"] or "-",
        )


_JS_SONDA_SELECT2 = """
(corpo) => {
    const caminho = el => {
        const partes = [];
        let atual = el.parentElement;
        for (let i = 0; i < 4 && atual; i++) {
            partes.push(atual.tagName.toLowerCase() + '.' + (atual.className || '').toString().trim().replace(/\\s+/g, '.').slice(0, 60));
            atual = atual.parentElement;
        }
        return partes.join('  <  ');
    };
    return {
        buscas: Array.from(document.querySelectorAll('.select2-search__field, [placeholder="Selecione"]')).map(el => ({
            tag: el.tagName.toLowerCase(),
            classe: (el.className || '').toString(),
            placeholder: el.placeholder,
            visivel: !!(el.offsetParent || el.getClientRects().length),
            pai: caminho(el),
        })),
        abertos: Array.from(document.querySelectorAll('.select2-container--open')).map(el => ({
            classe: (el.className || '').toString().slice(0, 80),
            visivel: !!(el.offsetParent || el.getClientRects().length),
        })),
        dropdowns: Array.from(document.querySelectorAll('.select2-dropdown, .select2-results')).map(el => ({
            classe: (el.className || '').toString().slice(0, 60),
            visivel: !!(el.offsetParent || el.getClientRects().length),
            opcoes: el.querySelectorAll('[role=option]').length,
        })),
    };
}
"""


def _sondar_fabricante(page: Page) -> None:
    """Clica na caixa do Fabricante e mostra onde foi parar a caixa de busca."""
    frame = page.frame_locator(seletores.IFRAME_RELATORIO or "iframe")
    corpo = frame.locator("body").first

    _titulo("SONDA DO CAMPO FABRICANTE (depois do clique na caixa)")
    frame.locator(seletores.SELECT2_FABRICANTE).first.click(timeout=15_000)
    page.wait_for_timeout(1_000)

    _relatar_sonda(corpo.evaluate(_JS_SONDA_SELECT2))

    _titulo("SONDA DEPOIS DE ESCOLHER O PRIMEIRO CODIGO (13963)")
    frame.locator(seletores.SELECT2_BUSCA).first.fill("13963")
    frame.locator(seletores.OPCAO_SELECT2.format(texto="(13963)")).first.click()
    page.wait_for_timeout(1_000)
    log.info("  --- estado logo apos a selecao, SEM clicar de novo ---")
    _relatar_sonda(corpo.evaluate(_JS_SONDA_SELECT2))

    log.info("  --- estado depois de clicar na caixa outra vez ---")
    try:
        frame.locator(seletores.SELECT2_FABRICANTE).first.click(timeout=10_000)
        page.wait_for_timeout(1_000)
        _relatar_sonda(corpo.evaluate(_JS_SONDA_SELECT2))
    except PlaywrightError as erro:
        log.info("      clique falhou: %s", str(erro).splitlines()[0])


def _relatar_sonda(sonda: dict) -> None:
    log.info("  containers com classe --open: %s", len(sonda["abertos"]))
    for item in sonda["abertos"]:
        log.info("      visivel=%-5s %s", item["visivel"], item["classe"])

    log.info("  dropdowns/resultados: %s", len(sonda["dropdowns"]))
    for item in sonda["dropdowns"]:
        log.info("      visivel=%-5s opcoes=%-4s %s", item["visivel"], item["opcoes"], item["classe"])

    log.info("  caixas de busca: %s", len(sonda["buscas"]))
    for item in sonda["buscas"]:
        log.info(
            "      <%s> visivel=%-5s placeholder=%r classe=%r",
            item["tag"],
            item["visivel"],
            item["placeholder"],
            item["classe"],
        )
        log.info("          ancestrais: %s", item["pai"])


_JS_OPCOES_FABRICANTE = """
(corpo) => Array.from(document.querySelectorAll('[role=option]'))
    .map(el => (el.innerText || '').replace(/\\s+/g, ' ').trim())
    .filter(t => t)
"""


def _listar_fabricantes(page: Page) -> Path:
    """Extrai a lista completa do campo Fabricante para um arquivo de consulta."""
    frame = page.frame_locator(seletores.IFRAME_RELATORIO or "iframe")
    frame.locator(seletores.SELECT2_TIPO_RELATORIO).first.wait_for(state="visible", timeout=30_000)
    frame.locator(seletores.SELECT2_FABRICANTE).first.click(timeout=15_000)
    page.wait_for_timeout(1_000)

    opcoes = frame.locator("body").first.evaluate(_JS_OPCOES_FABRICANTE)
    destino = RAIZ_PROJETO / "logs" / "fabricantes-geweb.txt"
    destino.parent.mkdir(parents=True, exist_ok=True)

    linhas = ["# Fornecedores cadastrados no Geweb (campo Fabricante).", "# formato: (codigo) NOME", ""]
    linhas.extend(opcoes)
    destino.write_text("\n".join(linhas), encoding="utf-8")

    log.info("")
    log.info("%s fornecedores gravados em %s", len(opcoes), destino)
    return destino


_JS_VALORES = """
(corpo) => ({
    inputs: Array.from(document.querySelectorAll('input:not([type=hidden])'))
        .filter(el => el.id)
        .map(el => ({ id: el.id, valor: el.value })),
    select2: Array.from(document.querySelectorAll("[id^='select2-'][id$='-container']"))
        .map(el => ({ id: el.id, texto: (el.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 60) })),
})
"""


def _mostrar_valores(corpo, momento: str) -> None:
    dados = corpo.evaluate(_JS_VALORES)
    log.info("  --- %s ---", momento)
    for campo in dados["inputs"]:
        if campo["valor"]:
            log.info("      %-28s = %r", campo["id"], campo["valor"])
    for campo in dados["select2"]:
        if campo["texto"] and campo["texto"] != "Selecione":
            log.info("      %-28s = %r", campo["id"], campo["texto"])


def _sondar_fluxo(page: Page) -> None:
    """Roda o fluxo real passo a passo, lendo os campos entre cada etapa.

    Serve para achar em que momento um filtro ja preenchido e perdido.
    """
    from src.config import carregar_fabricantes
    from src.geweb.relatorio_page import RelatorioComprasVendas
    from src.periodo import resolver_periodo

    cfg = carregar_config(headless_override=True)
    tela = RelatorioComprasVendas(page, cfg)
    corpo = page.frame_locator(seletores.IFRAME_RELATORIO or "iframe").locator("body").first
    periodo = resolver_periodo("2026-07")
    fabricante = carregar_fabricantes()[0]

    _titulo("FLUXO PASSO A PASSO (o que sobra nos campos a cada etapa)")
    tela.navegar()
    _mostrar_valores(corpo, "1. depois de escolher o tipo de relatorio")

    tela.preencher_periodo(periodo)
    _mostrar_valores(corpo, "2. depois de preencher as datas")

    tela.selecionar_fabricante(fabricante)
    _mostrar_valores(corpo, "3. depois de escolher o fabricante (antes de Gerar)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="descobrir", description="Mapeia a interface do Geweb.")
    parser.add_argument("--headless", action="store_true", help="Nao abre janela do navegador.")
    parser.add_argument(
        "--fabricantes",
        action="store_true",
        help="So extrai a lista de fornecedores para logs/fabricantes-geweb.txt.",
    )
    parser.add_argument(
        "--fluxo",
        action="store_true",
        help="Roda o fluxo passo a passo lendo os campos entre as etapas (sem gerar).",
    )
    args = parser.parse_args(argv)

    if args.fluxo:
        destino = _configurar_log()
        cfg = carregar_config(headless_override=args.headless or None)
        with sessao_geweb(cfg) as page:
            _sondar_fluxo(page)
        log.info("")
        log.info("Relatorio gravado em %s", destino)
        return 0

    if args.fabricantes:
        _configurar_log()
        cfg = carregar_config(headless_override=args.headless or None)
        with sessao_geweb(cfg) as page:
            for seletor in seletores.MENUS_ATE_O_RELATORIO:
                page.locator(seletor).first.click(timeout=15_000)
            _listar_fabricantes(page)
        return 0

    destino = _configurar_log()
    cfg = carregar_config(headless_override=args.headless or None)

    with sessao_geweb(cfg, apenas_login=True) as page:
        _listar_menu(page)

        _titulo("TENTATIVA DE ENTRAR NA TELA DO RELATORIO")
        corpo = page.locator("body").first
        for seletor in seletores.MENUS_ATE_O_RELATORIO:
            try:
                total = page.locator(seletor).count()
                page.locator(seletor).first.click(timeout=10_000)
                log.info("  OK    %s   (%s ocorrencia(s))", seletor, total)
                log.info("        links visiveis na sidebar depois deste clique:")
                for item in corpo.evaluate(_JS_SIDEBAR_VISIVEL):
                    log.info("          %-10s %s", item["codigo"] or "-", item["texto"])
            except PlaywrightError as erro:
                log.info("  FALHA %s", seletor)
                for linha in str(erro).splitlines()[:18]:
                    log.info("        %s", linha)
                log.info("  -> use a lista de links acima para corrigir MENUS_ATE_O_RELATORIO")
                log.info("")
                log.info("Relatorio gravado em %s", destino)
                return 1

        try:
            _listar_campos(page)
            _sondar_fabricante(page)
        except PlaywrightError as erro:
            log.info("  Nao foi possivel ler os campos: %s", str(erro).splitlines()[0])

    log.info("")
    log.info("Relatorio gravado em %s", destino)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
