"""Page Object da tela "Compras/Vendas por Produto" do Geweb.

Concentra TODA a interacao com essa tela. Se o layout do Geweb mudar, o impacto fica aqui
e nos seletores — main.py nao muda.

Particularidades do Geweb tratadas aqui:
  - o conteudo vive dentro do iframe #IFrameConteudo;
  - tipo de relatorio e fabricante sao widgets select2 (clicar -> buscar -> escolher);
  - o botao Gerar abre uma aba popup e dispara o download.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from playwright.sync_api import Download, FrameLocator, Locator, Page, expect

from src.config import Config, Fabricante
from src.geweb import seletores
from src.geweb.localizador import localizar
from src.periodo import Periodo

log = logging.getLogger(__name__)

_INTERVALO_POLL_MS = 250


class FalhaNaGeracao(Exception):
    """O relatorio nao foi gerado ou o download nao ocorreu."""


class RelatorioSemDados(Exception):
    """O Geweb respondeu, mas nao havia registros no periodo/fabricante."""


def _capturar_download(
    page: Page,
    acao: Callable[[], None],
    timeout_ms: int,
    sem_dados: Callable[[], bool] | None = None,
) -> Download:
    """Executa `acao` e devolve o download resultante.

    Registra o listener ANTES do clique e escuta tambem em abas novas — o Geweb abre um
    popup ao gerar. As abas abertas no processo sao fechadas ao final, para nao acumular
    uma janela por fabricante.
    """
    capturados: list[Download] = []
    contexto = page.context
    inscritos: list[Page] = []
    novas_abas: list[Page] = []

    def _guardar(download: Download) -> None:
        capturados.append(download)

    def _escutar(alvo: Page) -> None:
        alvo.on("download", _guardar)
        inscritos.append(alvo)
        if alvo is not page:
            novas_abas.append(alvo)

    _escutar(page)
    contexto.on("page", _escutar)

    try:
        acao()
        decorrido = 0
        while not capturados and decorrido < timeout_ms:
            if sem_dados is not None and sem_dados():
                raise RelatorioSemDados("O Geweb informou que nao ha registros para este filtro.")
            page.wait_for_timeout(_INTERVALO_POLL_MS)
            decorrido += _INTERVALO_POLL_MS

        if not capturados:
            raise FalhaNaGeracao(
                f"Nenhum download em {timeout_ms // 1000}s apos clicar em Gerar. "
                "Aumente TIMEOUT_RELATORIO_MS no .env ou confira o seletor BOTAO_GERAR."
            )
        return capturados[0]
    finally:
        contexto.remove_listener("page", _escutar)
        for alvo in inscritos:
            alvo.remove_listener("download", _guardar)
        for aba in novas_abas:
            if not aba.is_closed():
                aba.close()


class RelatorioComprasVendas:
    """Fluxo: navegar -> tipo do relatorio -> periodo -> fabricante -> gerar."""

    def __init__(self, page: Page, cfg: Config) -> None:
        self.page = page
        self.cfg = cfg

    @property
    def raiz(self) -> Page | FrameLocator:
        """O iframe onde vive o relatorio (ou a propria pagina, se nao houver iframe)."""
        if seletores.IFRAME_RELATORIO:
            return self.page.frame_locator(seletores.IFRAME_RELATORIO)
        return self.page

    def _no_iframe(self, seletor: str) -> Locator:
        return localizar(self.raiz, seletor).first

    def _abrir_select2(self, container: str) -> None:
        """Abre a lista de um widget select2.

        Cuidado: o clique e um interruptor. Com a lista ja aberta, ele FECHA — por isso
        `selecionar_fabricante` abre uma unica vez e depois so marca as opcoes.
        """
        self._no_iframe(container).click()

    def _marcar_opcao(self, texto_opcao: str, busca: str | None = None) -> None:
        """Com a lista aberta, filtra pela busca (se houver) e clica na opcao."""
        if busca is not None:
            self._no_iframe(seletores.SELECT2_BUSCA).fill(busca)
        self._no_iframe(seletores.OPCAO_SELECT2.format(texto=texto_opcao)).click()

    def _escolher_select2(self, container: str, texto_opcao: str, busca: str | None = None) -> None:
        """Abre um select2 e escolhe uma unica opcao.

        O select2 substitui o <select> nativo, entao `select_option` nao funciona:
        e preciso abrir a lista e clicar no item.
        """
        self._abrir_select2(container)
        self._marcar_opcao(texto_opcao, busca)

    def navegar(self) -> None:
        """Vai do menu ate a tela do relatorio e seleciona o tipo Mensal (Varejo).

        Os cliques de menu sao na pagina principal — o menu fica FORA do iframe.
        """
        log.debug("Navegando ate Compras/Vendas por Produto")
        for seletor in seletores.MENUS_ATE_O_RELATORIO:
            localizar(self.page, seletor).first.click()

        self._escolher_select2(seletores.SELECT2_TIPO_RELATORIO, seletores.TEXTO_TIPO_RELATORIO)

        # A escolha acima dispara um AJAX que repovoa o formulario com o modelo salvo e
        # zera as datas. Sem esperar aqui, tudo que for preenchido antes e perdido.
        expect(self._no_iframe(seletores.CAMPO_MODELO_CARREGADO)).not_to_have_value(
            "", timeout=self.cfg.timeout_ms
        )
        log.debug("Modelo salvo carregado")

    def preencher_periodo(self, periodo: Periodo) -> None:
        inicio = periodo.inicio.strftime(seletores.FORMATO_DATA)
        fim = periodo.fim.strftime(seletores.FORMATO_DATA)
        log.debug("Periodo %s a %s", inicio, fim)
        self._no_iframe(seletores.CAMPO_DATA_INICIO).fill(inicio)
        self._no_iframe(seletores.CAMPO_DATA_FIM).fill(fim)

    def selecionar_fabricante(self, fabricante: Fabricante) -> None:
        """Marca todos os codigos do laboratorio — a lista mostra "(13963) EUROFARMA...".

        O campo aceita multipla escolha, mas fecha a lista a cada item escolhido: por isso
        cada codigo exige um novo ciclo de abrir -> buscar -> clicar.
        """
        log.debug("Fabricante %s (codigos %s)", fabricante.nome, fabricante.resumo_codigos)
        self._abrir_select2(seletores.SELECT2_FABRICANTE)
        for codigo in fabricante.codigos:
            self._marcar_opcao(texto_opcao=f"({codigo})", busca=codigo)
        # A lista fica aberta apos cada escolha e cobriria o botao Gerar.
        self.page.keyboard.press("Escape")

    def _sem_dados(self) -> bool:
        """True se o Geweb esta exibindo a mensagem de 'nenhum registro'."""
        if not seletores.MENSAGEM_SEM_DADOS:
            return False
        return self._no_iframe(seletores.MENSAGEM_SEM_DADOS).is_visible()

    def gerar_e_baixar(self, destino: Path) -> Path:
        """Clica em Gerar, aguarda o download e salva o arquivo em `destino`."""
        destino.parent.mkdir(parents=True, exist_ok=True)
        botao = self._no_iframe(seletores.BOTAO_GERAR)

        download = _capturar_download(
            self.page,
            botao.click,
            timeout_ms=self.cfg.timeout_relatorio_ms,
            sem_dados=self._sem_dados,
        )

        # Preserva a extensao que o proprio Geweb entregou (.xlsx, .xls ou .csv).
        extensao = Path(download.suggested_filename).suffix or ".xlsx"
        arquivo = destino.with_suffix(extensao)
        download.save_as(str(arquivo))
        log.debug("Arquivo salvo em %s", arquivo)
        return arquivo

    def conferir_periodo(self, periodo: Periodo) -> None:
        """Le de volta as datas na tela e falha se nao forem as pedidas.

        Existe porque o Geweb ja sobrescreveu silenciosamente as datas com o mes corrente:
        o relatorio saia com dados, parecia certo, e vinha do periodo errado. Melhor falhar
        alto do que enviar um mapa errado para a industria.
        """
        na_tela = (
            self._no_iframe(seletores.CAMPO_DATA_INICIO).input_value(),
            self._no_iframe(seletores.CAMPO_DATA_FIM).input_value(),
        )
        esperado = (
            periodo.inicio.strftime(seletores.FORMATO_DATA),
            periodo.fim.strftime(seletores.FORMATO_DATA),
        )
        if na_tela != esperado:
            raise FalhaNaGeracao(
                f"O Geweb alterou o periodo: esperado {esperado[0]} a {esperado[1]}, "
                f"a tela esta com {na_tela[0]} a {na_tela[1]}. Relatorio nao gerado."
            )

    def extrair(self, fabricante: Fabricante, periodo: Periodo, destino: Path) -> Path:
        """Fluxo completo para um fabricante. Devolve o caminho do arquivo salvo.

        As datas sao preenchidas POR ULTIMO, ja que cada interacao com o formulario pode
        disparar um recarregamento que as redefine para o mes corrente.
        """
        self.navegar()
        self.selecionar_fabricante(fabricante)
        self.preencher_periodo(periodo)
        self.conferir_periodo(periodo)
        return self.gerar_e_baixar(destino)
