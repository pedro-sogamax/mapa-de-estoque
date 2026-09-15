"""Extracao automatica do Mapa de Estoque (Compras/Vendas por Produto) do Geweb.

Uso:
    python -m src.main                                       # o que a agenda manda hoje
    python -m src.main --planejar                            # so mostra o plano, sem abrir o Geweb
    python -m src.main --planejar --hoje 2026-09-01          # simula outra data
    python -m src.main --mes 2026-07                         # mes cheio especifico, todos
    python -m src.main --inicio 2026-07-01 --fim 2026-07-07  # periodo livre
    python -m src.main --fabricante EUROFARMA_RX             # so um fabricante
    python -m src.main --headless                            # sem janela (agendamento)
    python -m src.main --headless --enviar                   # extrai e ja manda os e-mails

Sem --mes/--inicio, a rodada consulta a agenda: o mensal so dispara no 1o dia util do mes,
e o semanal so nos dias marcados de cada fabricante. Por isso a tarefa agendada pode rodar
todo dia util — nos dias sem envio ela nao gera nada e sai com codigo 0.

Codigo de saida: 0 se todos os relatorios do dia sairam, 1 se houve qualquer falha. Com
--enviar, um envio que nao saiu devolve 3 — o mesmo codigo de `python -m src.disparo`,
para o log do agendador distinguir "nao gerei" de "gerei e nao entreguei".
"""

from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src import alerta
from src.agenda import Tarefa, tarefas_com_periodo_fixo, tarefas_do_dia
from src.config import (
    RAIZ_PROJETO,
    Config,
    ConfiguracaoInvalida,
    carregar_config,
    carregar_fabricantes_com_problemas,
)
from src.estado import EstadoDaAgenda
from src.formatador import caminho_formatado, formatar
from src.geweb.relatorio_page import RelatorioComprasVendas, RelatorioSemDados
from src.geweb.seletores import SeletoresIncompletos
from src.geweb.session import sessao_geweb
from src.log import configurar as configurar_log
from src.periodo import PeriodoInvalido, parsear_data, resolver_periodo
from src.rodada import ItemDaRodada
from src.rodada import gravar as gravar_rodada
from src.sequencia import Sequencia

log = logging.getLogger("mapa-estoque")

_CARACTERES_INVALIDOS = re.compile(r'[<>:"/\\|?*]+')

# O mesmo codigo que `python -m src.disparo` usa para "gerei, mas nao entreguei".
CODIGO_FALHA_DE_ENVIO = 3


@dataclass
class Resultado:
    """Desfecho da extracao de uma tarefa (um fabricante num periodo)."""

    fabricante: str
    motivo: str
    periodo: str
    rotulo: str = ""
    # O .xls do Geweb. So continua em disco quando a formatacao falhou — veja _descartar_bruto.
    arquivo: Path | None = None
    formatado: Path | None = None
    erro: str | None = None
    aviso: str | None = None

    @property
    def ok(self) -> bool:
        # De proposito nao olha `aviso`: sem o .xlsx formatado ainda existe o .xls bruto,
        # que e exatamente o arquivo que o comprador enviava antes. Nao e uma rodada perdida.
        return self.erro is None


def _nome_de_pasta(nome: str) -> str:
    """Remove caracteres que o Windows nao aceita em nome de pasta."""
    return _CARACTERES_INVALIDOS.sub("-", nome).strip() or "sem-nome"


def _configurar_log(nivel: int = logging.INFO) -> None:
    configurar_log("execucao.log", nivel)


def _formatar(arquivo: Path, cfg: Config) -> tuple[Path | None, str | None]:
    """Gera o .xlsx formatado a partir do arquivo bruto. Devolve (caminho, aviso).

    Falhar aqui nao derruba a tarefa: o .xls do Geweb ja esta salvo e continua sendo um
    arquivo valido para enviar. O operador ve o aviso no resumo e formata esse a mao.
    """
    destino = caminho_formatado(arquivo, cfg.download_dir, cfg.formatado_dir)
    try:
        formatado = formatar(arquivo, destino)
    except Exception as erro:
        log.warning("    AVISO: formatacao falhou (%s). O arquivo bruto esta em %s", erro, arquivo)
        log.debug("Detalhe da falha ao formatar %s", arquivo, exc_info=True)
        return None, f"formatacao falhou: {erro}"

    log.info("    formatado -> %s", formatado)
    return formatado, None


def _descartar_bruto(arquivo: Path, raiz: Path) -> bool:
    """Apaga o .xls do Geweb depois que o .xlsx formatado saiu. Devolve True se apagou.

    So o formatado e guardado: e ele que vai para a industria. Quem chama so descarta com o
    formatado ja salvo — sem ele, o bruto e o unico arquivo que resta para enviar.

    As pastas de fabricante e periodo que ficarem vazias saem junto, subindo ate `raiz` (o
    DOWNLOAD_DIR), que nunca e removida. Falhar aqui so deixa um arquivo a mais em disco.
    """
    try:
        arquivo.unlink()
    except OSError as erro:
        log.warning("    Nao consegui apagar o arquivo bruto %s: %s", arquivo, erro)
        return False

    raiz = raiz.resolve()
    pasta = arquivo.parent.resolve()
    while pasta != raiz and raiz in pasta.parents:
        try:
            pasta.rmdir()  # so remove pasta vazia
        except OSError:
            break
        pasta = pasta.parent
    log.debug("    bruto descartado: %s", arquivo)
    return True


def _registrar_entrega(estado: EstadoDaAgenda | None, tarefa: Tarefa) -> None:
    """Marca o mensal como entregue. Rodadas manuais (--mes) nao mexem na agenda."""
    if estado is not None and tarefa.motivo == "mensal":
        estado.registrar_mensal(tarefa.fabricante.nome, tarefa.periodo.rotulo)


def extrair_todos(
    cfg: Config, tarefas: list[Tarefa], estado: EstadoDaAgenda | None = None
) -> list[Resultado]:
    """Executa as tarefas do dia numa unica sessao. A falha de uma nao interrompe as demais.

    Cada mensal so e dado como entregue depois de o arquivo existir. Uma falha nao registra
    nada, e a rodada do dia seguinte tenta esse fabricante de novo.
    """
    resultados: list[Resultado] = []
    # As duas arvores: com o bruto descartado, a numeracao ja usada so aparece no formatado.
    sequencia = Sequencia(cfg.sequencia_path, cfg.download_dir, cfg.formatado_dir)

    with sessao_geweb(cfg) as page:
        tela = RelatorioComprasVendas(page, cfg)

        for indice, tarefa in enumerate(tarefas, start=1):
            fabricante, periodo = tarefa.fabricante, tarefa.periodo
            log.info("[%d/%d] %s", indice, len(tarefas), tarefa)
            pasta = _nome_de_pasta(fabricante.nome)
            numero = sequencia.proximo()
            destino = (
                cfg.download_dir
                / pasta
                / periodo.pasta_do_mes
                / f"{numero:04d}_{pasta}_{periodo.rotulo}.xlsx"
            )
            try:
                arquivo = tela.extrair(fabricante, periodo, destino)
                log.info("    OK -> %s", arquivo)
                # A entrega e registrada pela extracao, nao pela formatacao: um tropeco na
                # conversao nao pode fazer o script reextrair o mesmo mes amanha.
                _registrar_entrega(estado, tarefa)
                formatado, aviso = _formatar(arquivo, cfg)
                if formatado is not None and _descartar_bruto(arquivo, cfg.download_dir):
                    bruto = None
                else:
                    bruto = arquivo
                resultados.append(
                    Resultado(
                        fabricante.nome,
                        tarefa.motivo,
                        str(periodo),
                        rotulo=periodo.rotulo,
                        arquivo=bruto,
                        formatado=formatado,
                        aviso=aviso,
                    )
                )
            except RelatorioSemDados as erro:
                sequencia.devolver(numero)
                log.warning("    SEM DADOS: %s", erro)
                # O Geweb respondeu, so nao havia movimento. Insistir todo dia so faria ruido.
                _registrar_entrega(estado, tarefa)
                resultados.append(
                    Resultado(
                        fabricante.nome,
                        tarefa.motivo,
                        str(periodo),
                        rotulo=periodo.rotulo,
                        erro=f"sem dados: {erro}",
                    )
                )
            except Exception as erro:  # falha isolada: segue para a proxima tarefa
                sequencia.devolver(numero)
                log.error("    FALHOU: %s", erro)
                log.debug("Detalhe da falha em %s", fabricante.nome, exc_info=True)
                resultados.append(
                    Resultado(
                        fabricante.nome,
                        tarefa.motivo,
                        str(periodo),
                        rotulo=periodo.rotulo,
                        erro=str(erro),
                    )
                )

    return resultados


def _registrar_rodada(cfg: Config, resultados: list[Resultado]) -> list[ItemDaRodada]:
    """Anota o que esta rodada gerou, para o comando de disparo saber o que montar.

    So registra. Gravar o manifesto nao envia nada: quem envia e `python -m src.disparo`,
    a mao, ou o `--enviar` desta rodada, que e opt-in. Falhar aqui nao pode custar a
    extracao, que ja esta salva em disco. Devolve os itens gravados.
    """
    itens = [
        ItemDaRodada(
            fabricante=r.fabricante,
            motivo=r.motivo,
            periodo=r.periodo,
            rotulo=r.rotulo,
            arquivo=r.arquivo,
            formatado=r.formatado,
        )
        for r in resultados
        if r.ok and (r.formatado or r.arquivo)
    ]
    try:
        gravar_rodada(cfg.rodada_path, itens)
    except OSError as erro:
        log.warning("Nao consegui gravar %s: %s", cfg.rodada_path.name, erro)
    return itens


def _disparar_email(quantos: int) -> int:
    """Encadeia o envio por e-mail logo apos a extracao. So com --enviar.

    Roda em processo separado de proposito. O disparo tem o proprio log (o logs/disparo.log) e
    o proprio codigo de saida; chamado dentro deste processo, o `logging.basicConfig` ja
    consumido aqui jogaria tudo dentro de execucao.log e o disparo.log ficaria mudo.

    O canal e fixo em e-mail. O WhatsApp continua so no comando manual: nao ha trava de
    teste preenchida para ele, e um canal que pode fazer um numero ser banido nao entra numa
    tarefa agendada por tabela.

    A confirmacao `SIM` nao existe aqui — e o que o --enviar troca por automacao. O que
    segura o resto continua valendo: envios.json (nao reenvia), teto por rodada, cota
    horaria, disjuntor e a trava DESTINATARIO_TESTE.
    """
    comando = [sys.executable, "-m", "src.disparo", "--canal", "email", "--sim"]
    log.info("-" * 72)
    log.info("--enviar: chamando o disparo por e-mail para %d relatorio(s) extraido(s).", quantos)
    try:
        return subprocess.run(comando, cwd=RAIZ_PROJETO).returncode
    except OSError as erro:
        # Nao conseguir sequer iniciar o disparo e falha de envio, nao de extracao: os
        # arquivos estao salvos e `python -m src.disparo` continua disponivel a mao.
        log.error("Nao consegui iniciar o disparo: %s", erro)
        return CODIGO_FALHA_DE_ENVIO


def _imprimir_resumo(resultados: list[Resultado]) -> None:
    sucessos = [r for r in resultados if r.ok]
    sem_formatar = [r for r in resultados if r.aviso]

    log.info("-" * 72)
    log.info("RESUMO — %d de %d extraidos com sucesso", len(sucessos), len(resultados))
    for resultado in resultados:
        marca = "ok   " if resultado.ok else "FALHA"
        log.info(
            "  %s %-26s %-16s %s",
            marca,
            resultado.fabricante,
            resultado.motivo,
            resultado.periodo,
        )
        if not resultado.ok:
            log.info("        %s", resultado.erro)
        elif resultado.aviso:
            log.info("        %s", resultado.aviso)
    if sem_formatar:
        log.info(
            "%d relatorio(s) sairam so no formato bruto do Geweb — formate a mao antes de enviar.",
            len(sem_formatar),
        )
    log.info("-" * 72)


def _imprimir_plano(tarefas: list[Tarefa], avisos: list[str]) -> None:
    """Mostra o que a rodada faria, sem tocar no Geweb."""
    log.info("-" * 72)
    if tarefas:
        log.info("PLANO — %d relatorio(s) a gerar:", len(tarefas))
        for tarefa in tarefas:
            log.info(
                "  %-26s %-16s %s  [%s]",
                tarefa.fabricante.nome,
                tarefa.motivo,
                tarefa.periodo,
                tarefa.fabricante.resumo_codigos,
            )
    else:
        log.info("PLANO — nenhum relatorio a gerar hoje.")
    for aviso in avisos:
        log.info("  · %s", aviso)
    log.info("-" * 72)


def _parsear_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mapa-estoque",
        description="Baixa o relatorio Compras/Vendas por Produto do Geweb para cada fabricante.",
    )
    parser.add_argument("--mes", help="Mes cheio do relatorio (AAAA-MM). Padrao: mes anterior.")
    parser.add_argument("--inicio", help="Inicio de um periodo livre (AAAA-MM-DD). Use com --fim.")
    parser.add_argument("--fim", help="Fim de um periodo livre (AAAA-MM-DD). Use com --inicio.")
    parser.add_argument(
        "--fabricante",
        help="Processa apenas este fabricante (campo 'nome' do fabricantes.yaml).",
    )
    parser.add_argument(
        "--planejar",
        action="store_true",
        help="Mostra o que a rodada geraria e sai, sem abrir o navegador.",
    )
    parser.add_argument(
        "--hoje",
        help="Simula outra data (AAAA-MM-DD) para conferir a agenda. Use com --planejar.",
    )
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Roda sem abrir a janela do navegador. Padrao: valor de HEADLESS no .env.",
    )
    parser.add_argument(
        "--enviar",
        action="store_true",
        help="Ao fim da extracao, ja envia os e-mails as industrias, sem perguntar. "
        "So o canal e-mail. Sem esta flag a rodada nao envia nada.",
    )
    parser.add_argument("--debug", action="store_true", help="Log detalhado.")
    return parser.parse_args(argv)


def _linhas_do_alerta(
    resultados: list[Resultado],
    problemas_de_cadastro: list[str],
    codigo_envio: int | None = None,
    erro_geral: str = "",
) -> list[str]:
    """Corpo do alerta: o que falhou, nomeado, e o que ficou pendente. Uma tela, no maximo."""
    linhas: list[str] = []

    if erro_geral:
        linhas += ["A rodada foi interrompida e NENHUM relatorio foi gerado:", f"  {erro_geral}", ""]

    falhas = [r for r in resultados if not r.ok]
    if falhas:
        linhas.append(f"{len(falhas)} de {len(resultados)} relatorio(s) NAO sairam:")
        linhas += [f"  {r.fabricante} ({r.motivo}, {r.periodo}): {r.erro}" for r in falhas]
        linhas.append("")

    sem_formatar = [r for r in resultados if r.aviso]
    if sem_formatar:
        linhas.append(
            f"{len(sem_formatar)} sairam so no formato bruto do Geweb (formate a mao antes de enviar):"
        )
        linhas += [f"  {r.fabricante}: {r.aviso}" for r in sem_formatar]
        linhas.append("")

    if problemas_de_cadastro:
        linhas.append(
            f"{len(problemas_de_cadastro)} fabricante(s) ficaram DE FORA por erro no "
            "fabricantes.yaml — nao receberam nada:"
        )
        linhas += [f"  {p}" for p in problemas_de_cadastro]
        linhas.append("")

    if codigo_envio:
        linhas += [
            f"O envio por e-mail terminou com codigo {codigo_envio} — algum laboratorio "
            "pode nao ter recebido.",
            "Confira logs/disparo.log e, se preciso, rode `python -m src.disparo`.",
            "",
        ]

    return linhas


def main(argv: list[str] | None = None) -> int:
    args = _parsear_argumentos(argv)
    _configurar_log(logging.DEBUG if args.debug else logging.INFO)

    try:
        cfg = carregar_config(headless_override=args.headless)
        fabricantes, problemas_de_cadastro = carregar_fabricantes_com_problemas()
        periodo = resolver_periodo(args.mes, args.inicio, args.fim)
        hoje = parsear_data(args.hoje, "--hoje") if args.hoje else None
    except (ConfiguracaoInvalida, PeriodoInvalido) as erro:
        # Aqui ainda nao ha Config utilizavel — pode ser justamente o .env que esta quebrado —
        # entao nao ha como avisar por e-mail. Fica o log e o codigo de saida.
        log.error("%s", erro)
        return 2

    def avisar(codigo: int, resultados: list[Resultado], envio: int | None = None, erro: str = "") -> None:
        """Manda o alerta quando a rodada nao terminou limpa. Nunca derruba nada."""
        if args.planejar:
            return
        linhas = _linhas_do_alerta(resultados, problemas_de_cadastro, envio, erro)
        if not linhas:
            return
        quantas = len([r for r in resultados if not r.ok]) or len(problemas_de_cadastro)
        assunto = (
            f"[Mapa de Estoque] FALHA na rodada de {date.today():%d/%m/%Y}"
            f" — {quantas} pendencia(s), codigo {codigo}"
        )
        alerta.enviar(cfg, assunto, linhas)

    if args.fabricante:
        alvo = args.fabricante.strip().casefold()
        fabricantes = [f for f in fabricantes if f.nome.casefold() == alvo]
        if not fabricantes:
            log.error(
                "Fabricante %r nao encontrado entre os ativos do fabricantes.yaml.", args.fabricante
            )
            return 2

    estado: EstadoDaAgenda | None = None
    if periodo is None:
        # Vale tambem em --planejar: so assim da para simular a recuperacao de um mes
        # perdido. O plano nunca grava nada — quem registra e a extracao concluida.
        estado = EstadoDaAgenda(cfg.estado_path)
        tarefas, avisos = tarefas_do_dia(fabricantes, hoje, estado)
    else:
        # --mes / --inicio+--fim: rodada manual, ignora a agenda de propósito.
        tarefas, avisos = tarefas_com_periodo_fixo(fabricantes, periodo), []

    log.info("Config: %s", cfg.mascarar())
    _imprimir_plano(tarefas, avisos)

    if args.planejar:
        return 0
    if not tarefas:
        log.info("Nada a fazer hoje — o Geweb nem sera aberto.")
        # Um cadastro quebrado precisa ser avisado mesmo num dia sem extracao: e justamente
        # o dia em que ninguem olharia o log.
        avisar(0, [])
        return 0

    try:
        resultados = extrair_todos(cfg, tarefas, estado)
    except SeletoresIncompletos as erro:
        log.error("%s", erro)
        avisar(2, [], erro=str(erro))
        return 2
    except Exception as erro:  # falha de sessao/login: nada foi extraido
        log.error("Execucao interrompida: %s", erro)
        log.debug("Detalhe", exc_info=True)
        avisar(1, [], erro=str(erro))
        return 1

    itens = _registrar_rodada(cfg, resultados)
    _imprimir_resumo(resultados)
    codigo = 0 if all(r.ok for r in resultados) else 1

    if not args.enviar:
        avisar(codigo, resultados)
        return codigo
    if not itens:
        # Todos falharam: nao ha anexo nenhum. Chamar o disparo aqui so o faria reler o
        # manifesto da rodada anterior — que o envios.json ja marcou como entregue.
        log.info("Nada extraido nesta rodada — o envio nao foi chamado.")
        avisar(codigo, resultados)
        return codigo

    codigo_envio = _disparar_email(len(itens))
    if codigo_envio == 0:
        avisar(codigo, resultados)
        return codigo
    if codigo != 0:
        # Os dois falharam. O 3 prevalece porque e o desfecho mais tardio e o mais caro de
        # descobrir tarde: a extracao ausente reaparece no resumo acima e a rodada seguinte
        # a refaz sozinha, mas o e-mail nao entregue nao tem recuperacao automatica.
        log.error(
            "A extracao falhou (codigo %d) E o envio falhou (codigo %d). Saindo com %d.",
            codigo,
            codigo_envio,
            codigo_envio,
        )
    avisar(codigo_envio, resultados, envio=codigo_envio)
    return codigo_envio


if __name__ == "__main__":
    raise SystemExit(main())
