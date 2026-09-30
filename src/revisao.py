"""Revisao semanal: o relatorio da semana a revisora, e a conferencia de que ela o abriu.

A diretoria quer registrado que o historico das rodadas foi visto toda semana, sem nenhuma
etapa manual. A proposta aprovada esta em docs/propostas/revisao-semanal.md; o resumo:

1. A rodada de segunda, no fim, manda a revisora o resumo da semana (terca a segunda) no
   corpo do e-mail, com a planilha da semana anexa. Se a rodada quebrar, o relatorio sai
   mesmo assim, contando a falha. Se nao sair na segunda (maquina desligada, SMTP fora), a
   rodada seguinte manda o que ficou para tras — como o mensal.
2. Quando a revisora abre o e-mail, o servidor da Locaweb marca a mensagem como lida
   (\\Seen). Esta automacao entra na caixa dela por IMAP e confere essa marca.
3. Lido: a aba Revisoes registra. Nao lido no prazo (dias uteis): registra "Sem leitura" e
   avisa a gerente — e continua conferindo ate o relatorio seguinte; lido depois disso vira
   "Lido apos o prazo".

**A conferencia nunca pode marcar nada como lido.** Cada pasta e aberta com EXAMINE (so
leitura) e so os FLAGS sao lidos. Um SELECT, ou um FETCH do corpo sem PEEK, marcaria o
relatorio como lido e forjaria a confirmacao.

O estado fica em dados/revisoes.json: e o que impede reenviar o relatorio da semana ou
repetir o alerta. A aba Revisoes da planilha de historico e projecao dele.

Uso (a tarefa agendada de hora em hora chama o primeiro):
    python -m src.revisao            # confere a leitura do relatorio pendente
    python -m src.revisao --status   # mostra o registro, sem conectar a nada
"""

from __future__ import annotations

import argparse
import imaplib
import json
import logging
import os
import re
from dataclasses import asdict, dataclass, fields
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from src import alerta, historico
from src.config import Config, ConfiguracaoInvalida, carregar_config
from src.disparo.canais.base import Destino, FalhaNoEnvio, Mensagem
from src.disparo.canais.email_smtp import CanalEmail
from src.periodo import eh_dia_util
from src.trava import Trava

log = logging.getLogger(__name__)

AGUARDANDO = "Aguardando leitura"
LIDO = "Lido"
SEM_LEITURA = "Sem leitura"
LIDO_APOS_O_PRAZO = "Lido após o prazo"

# O relatorio precisa caber numa leitura: o detalhe esta na planilha anexa.
MAX_PENDENCIAS = 30


class FalhaNaConferencia(Exception):
    """Nao deu para conferir a caixa — o que e diferente de a mensagem nao ter sido lida."""


@dataclass
class Relatorio:
    """Um relatorio semanal enviado, e o que se sabe da leitura dele."""

    inicio: str  # AAAA-MM-DD, a terca que abre a semana
    fim: str  # AAAA-MM-DD, a segunda que a fecha
    message_id: str
    enviado_em: str  # AAAA-MM-DDTHH:MM:SS
    para: list[str]
    situacao: str = AGUARDANDO
    lido_ate: str = ""  # hora da conferencia que achou a marca de lida; a leitura foi antes
    alerta_em: str = ""

    @property
    def rotulo(self) -> str:
        inicio, fim = date.fromisoformat(self.inicio), date.fromisoformat(self.fim)
        return f"{inicio:%d/%m} a {fim:%d/%m/%Y}"

    @property
    def encerrado(self) -> bool:
        return self.situacao in (LIDO, LIDO_APOS_O_PRAZO)


class Registro:
    """dados/revisoes.json: os relatorios enviados, do mais antigo para o mais recente."""

    def __init__(self, arquivo: Path) -> None:
        self.arquivo = arquivo
        self._ilegivel = False
        self.relatorios: list[Relatorio] = []
        self.falha_avisada_em = ""  # data do ultimo alerta tecnico, um por dia no maximo
        self._carregar()

    def _carregar(self) -> None:
        if not self.arquivo.exists():
            return
        try:
            dados = json.loads(self.arquivo.read_text(encoding="utf-8"))
            nomes = {f.name for f in fields(Relatorio)}
            self.relatorios = [
                Relatorio(**{k: v for k, v in item.items() if k in nomes})
                for item in dados.get("relatorios", [])
            ]
            self.falha_avisada_em = str(dados.get("falha_avisada_em", ""))
        except (ValueError, TypeError, AttributeError, json.JSONDecodeError):
            # Seguir e melhor que travar a rodada; o arquivo ruim e guardado ao lado na
            # proxima gravacao, em vez de sobrescrito, para ninguem perder o historico.
            log.warning(
                "%s ilegivel — seguindo como se nenhum relatorio tivesse saido. O relatorio "
                "da semana pode sair em duplicata.",
                self.arquivo.name,
            )
            self._ilegivel = True
            self.relatorios = []

    def da_semana(self, fim: date) -> Relatorio | None:
        return next((r for r in self.relatorios if r.fim == fim.isoformat()), None)

    def ultimo(self) -> Relatorio | None:
        return max(self.relatorios, key=lambda r: r.fim, default=None)

    def gravar(self) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        if self._ilegivel and self.arquivo.exists():
            os.replace(self.arquivo, self.arquivo.with_suffix(".json.ilegivel"))
            self._ilegivel = False
        temporario = self.arquivo.with_suffix(".json.tmp")
        conteudo = {
            "relatorios": [asdict(r) for r in sorted(self.relatorios, key=lambda r: r.fim)],
            "falha_avisada_em": self.falha_avisada_em,
        }
        temporario.write_text(json.dumps(conteudo, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporario, self.arquivo)


# --- Datas -----------------------------------------------------------------------------


def semana_de(hoje: date) -> tuple[date, date]:
    """(terca, segunda) da ultima semana fechada ate hoje. Na segunda, a que fecha hoje."""
    fim = hoje - timedelta(days=hoje.weekday())
    return fim - timedelta(days=6), fim


def dias_uteis_desde(inicio: date, hoje: date) -> int:
    """Dias uteis depois de `inicio`, ate `hoje` inclusive. Segunda -> quinta da 3."""
    return sum(
        eh_dia_util(inicio + timedelta(days=d)) for d in range(1, (hoje - inicio).days + 1)
    )


def prazo_vencido(relatorio: Relatorio, hoje: date, prazo: int) -> bool:
    enviado = date.fromisoformat(relatorio.enviado_em[:10])
    return dias_uteis_desde(enviado, hoje) >= prazo


# --- O relatorio -----------------------------------------------------------------------


def eventos_da_semana(eventos: list[dict[str, Any]], inicio: date, fim: date) -> list[dict[str, Any]]:
    de, ate = inicio.isoformat(), fim.isoformat()
    return [e for e in eventos if de <= str(e.get("em", ""))[:10] <= ate]


def _contagem(eventos: list[dict[str, Any]], tipo: str) -> dict[str, int]:
    conta: dict[str, int] = {}
    for evento in eventos:
        if evento.get("tipo") == tipo:
            resultado = str(evento.get("resultado", ""))
            conta[resultado] = conta.get(resultado, 0) + 1
    return conta


def _pendencias(eventos: list[dict[str, Any]]) -> list[str]:
    """O que falhou ou nem foi tentado, na ordem em que aconteceu."""
    linhas = []
    for evento in sorted(eventos, key=lambda e: str(e.get("em", ""))):
        tipo, resultado = evento.get("tipo"), evento.get("resultado")
        if resultado not in ("falha", "nao tentado"):
            continue
        em = str(evento.get("em", ""))
        etapa = "extração" if tipo == "extracao" else "envio"
        marca = " [não tentado]" if resultado == "nao tentado" else ""
        linhas.append(
            f"  - {em[8:10]}/{em[5:7]} {etapa:<8} {evento.get('laboratorio', '')} "
            f"({evento.get('periodo', '')}): {evento.get('motivo', '') or 'sem motivo registrado'}"
            f"{marca}"
        )
    return linhas


def montar_relatorio(
    eventos: list[dict[str, Any]],
    inicio: date,
    fim: date,
    erro_da_rodada: str = "",
    com_anexo: bool = True,
) -> tuple[str, str]:
    """(assunto, corpo) do relatorio da semana. Texto puro: e o que a revisora le."""
    extracoes = _contagem(eventos, "extracao")
    envios = _contagem(eventos, "envio")
    pendencias = _pendencias(eventos)

    assunto = f"[Mapa de Estoque] Revisão semanal — {inicio:%d/%m} a {fim:%d/%m/%Y}"
    if pendencias or erro_da_rodada:
        assunto += f" — {len(pendencias) + bool(erro_da_rodada)} pendência(s)"

    linhas = [f"Revisão semanal do Mapa de Estoque — terça {inicio:%d/%m} a segunda {fim:%d/%m/%Y}.", ""]
    if erro_da_rodada:
        linhas += [
            f"ATENÇÃO: a rodada de {fim:%d/%m} foi interrompida e não extraiu nada:",
            f"  {erro_da_rodada}",
            "",
        ]
    if not eventos:
        linhas += ["Nenhuma extração ou envio registrado na semana.", ""]
    else:
        linhas += [
            f"Extrações: {extracoes.get('ok', 0)} ok, {extracoes.get('falha', 0)} falha(s), "
            f"{extracoes.get('sem dados', 0)} sem dados ({sum(extracoes.values())} no total)",
            f"Envios:    {envios.get('ok', 0)} ok, {envios.get('falha', 0)} falha(s), "
            f"{envios.get('nao tentado', 0)} não tentado(s) ({sum(envios.values())} no total)",
            "",
        ]
        if pendencias:
            linhas.append("Pendências da semana:")
            linhas += pendencias[:MAX_PENDENCIAS]
            if len(pendencias) > MAX_PENDENCIAS:
                linhas.append(f"  ... e mais {len(pendencias) - MAX_PENDENCIAS} — veja a planilha anexa.")
        else:
            linhas.append("Nenhuma falha na semana.")
        linhas.append("")

    if com_anexo:
        linhas.append("A planilha anexa traz cada extração e cada envio da semana.")
    else:
        linhas.append(
            "A planilha da semana não pôde ser gerada; o detalhe está na planilha de "
            "histórico do mês."
        )
    linhas += [
        "",
        "-" * 62,
        "Mensagem automática do Mapa de Estoque. A abertura deste e-mail fica registrada",
        "na planilha de histórico (aba Revisoes).",
    ]
    return assunto, "\n".join(linhas)


def enviar_relatorio(cfg: Config, hoje: date | None = None, erro_da_rodada: str = "") -> bool:
    """Manda o relatorio da ultima semana fechada, se ainda nao saiu. Devolve True se enviou.

    Recuperavel: a semana e a que fechou na ultima segunda, e o registro diz se ela ja
    saiu. Na segunda sai no fim da rodada; se falhar, a rodada seguinte tenta de novo.
    `erro_da_rodada` so entra no texto quando a rodada que quebrou e a da propria segunda.
    """
    if not cfg.revisao_ligada:
        return False
    hoje = hoje or date.today()
    inicio, fim = semana_de(hoje)
    registro = Registro(cfg.revisoes_path)
    if registro.da_semana(fim) is not None:
        log.debug("Revisao: o relatorio de %s a %s ja saiu.", inicio, fim)
        return False
    if not cfg.email_configurado:
        log.warning("Revisao: relatorio semanal nao enviado — SMTP nao configurado no .env.")
        return False

    eventos = eventos_da_semana(historico.ler(cfg.historico_path), inicio, fim)
    anexo = historico.gravar_planilha(
        eventos, cfg.revisoes_dir / f"historico-semana-{inicio:%Y-%m-%d}_a_{fim:%Y-%m-%d}.xlsx"
    )
    assunto, corpo = montar_relatorio(
        eventos, inicio, fim, erro_da_rodada if hoje == fim else "", com_anexo=anexo is not None
    )
    destino = Destino(
        fabricante="revisao semanal",
        emails=cfg.revisao_para,
        copia_oculta=cfg.revisao_copia_para,
    )
    try:
        with CanalEmail(cfg) as canal:
            envio = canal.enviar(destino, Mensagem(assunto=assunto, corpo=corpo), anexo)
    except (FalhaNoEnvio, OSError) as erro:
        log.error("Revisao: o relatorio semanal nao saiu (%s). A proxima rodada tenta de novo.", erro)
        return False

    registro.relatorios.append(
        Relatorio(
            inicio=inicio.isoformat(),
            fim=fim.isoformat(),
            message_id=envio.identificadores[0],
            enviado_em=datetime.now().isoformat(timespec="seconds"),
            para=list(cfg.revisao_para),
        )
    )
    registro.gravar()
    log.info("Revisao: relatorio de %s a %s enviado para %s.", inicio, fim, ", ".join(cfg.revisao_para))
    _atualizar_planilhas(cfg)
    return True


# --- A conferencia -----------------------------------------------------------------------

_LINHA_DO_LIST = re.compile(r'^\((?P<marcas>[^)]*)\) (?P<separador>"[^"]*"|NIL) (?P<nome>.+)$')


def _pastas(imap: imaplib.IMAP4) -> list[str]:
    """Todas as pastas selecionaveis da caixa, ja no formato que o SELECT/EXAMINE espera."""
    tipo, linhas = imap.list()
    if tipo != "OK":
        raise FalhaNaConferencia(f"o servidor nao listou as pastas: {linhas!r}")
    pastas = []
    for bruta in linhas:
        if not isinstance(bruta, bytes):
            continue
        casamento = _LINHA_DO_LIST.match(bruta.decode("utf-8", errors="replace"))
        if not casamento or "\\noselect" in casamento["marcas"].lower():
            continue
        nome = casamento["nome"].strip()
        pastas.append(nome if nome.startswith('"') else f'"{nome}"')
    return pastas


def verificar_leitura(cfg: Config, message_id: str) -> bool | None:
    """Procura a mensagem em todas as pastas da caixa da revisora.

    True: achou marcada como lida. False: achou, e nao esta lida. None: nao achou em lugar
    nenhum (apagada e a lixeira esvaziada). Levanta FalhaNaConferencia se nao conseguiu
    olhar — credencial recusada, servidor fora.

    Somente leitura: EXAMINE, SEARCH e FETCH (FLAGS). Nada disso marca a mensagem como lida.
    """
    if not (cfg.revisao_imap_usuario and cfg.revisao_imap_senha):
        raise FalhaNaConferencia("REVISAO_IMAP_USUARIO/REVISAO_IMAP_SENHA nao configurados no .env")
    if not cfg.imap_host:
        raise FalhaNaConferencia("IMAP_HOST (ou SMTP_HOST) nao configurado no .env")

    try:
        imap = imaplib.IMAP4_SSL(cfg.imap_host, cfg.imap_porta, timeout=30)
    except (OSError, imaplib.IMAP4.error) as erro:
        raise FalhaNaConferencia(f"nao consegui conectar em {cfg.imap_host}:{cfg.imap_porta}: {erro}") from erro

    try:
        try:
            imap.login(cfg.revisao_imap_usuario, cfg.revisao_imap_senha)
        except imaplib.IMAP4.error as erro:
            raise FalhaNaConferencia(
                f"o servidor recusou as credenciais de {cfg.revisao_imap_usuario} — a senha mudou?"
            ) from erro

        achou = False
        for pasta in _pastas(imap):
            tipo, _ = imap.select(pasta, readonly=True)  # readonly=True e o EXAMINE
            if tipo != "OK":
                continue
            tipo, numeros = imap.search(None, "HEADER", "Message-ID", f'"{message_id}"')
            if tipo != "OK" or not numeros or not numeros[0]:
                continue
            for numero in numeros[0].split():
                tipo, resposta = imap.fetch(numero, "(FLAGS)")
                if tipo != "OK":
                    continue
                marcas = b" ".join(p if isinstance(p, bytes) else b"" for p in resposta)
                if b"\\Seen" in marcas:
                    return True
                achou = True
        return False if achou else None
    except (OSError, imaplib.IMAP4.error) as erro:
        raise FalhaNaConferencia(f"a conexao com {cfg.imap_host} falhou: {erro}") from erro
    finally:
        try:
            imap.logout()
        except (OSError, imaplib.IMAP4.error):
            pass


Verificador = Callable[[Config, str], "bool | None"]


def conferir(
    cfg: Config, agora: datetime | None = None, verificar: Verificador = verificar_leitura
) -> bool:
    """Confere o relatorio mais recente e atualiza o registro. Devolve True se algo mudou.

    Sem relatorio pendente — a maior parte da semana — sai sem conectar a nada. So grava o
    registro e regrava as planilhas quando algo muda: regravar toda hora faria o ownCloud
    sincronizar o arquivo toda hora, e falharia com a planilha aberta no Excel.
    """
    if not cfg.revisao_ligada:
        return False
    registro = Registro(cfg.revisoes_path)
    relatorio = registro.ultimo()
    if relatorio is None or relatorio.encerrado:
        log.debug("Revisao: nenhum relatorio aguardando leitura.")
        return False

    agora = agora or datetime.now()
    if cfg.revisao_imap_usuario.casefold() not in {p.casefold() for p in relatorio.para}:
        log.warning(
            "Revisao: a caixa conferida (%s) nao e a que recebeu o relatorio (%s). Confira "
            "REVISAO_IMAP_USUARIO e REVISAO_PARA no .env.",
            cfg.revisao_imap_usuario,
            ", ".join(relatorio.para),
        )

    try:
        lido = verificar(cfg, relatorio.message_id)
    except FalhaNaConferencia as erro:
        log.error("Revisao: nao consegui conferir a leitura: %s", erro)
        _avisar_falha_tecnica(cfg, registro, relatorio, str(erro), agora)
        return False

    mudou = False
    if lido:
        relatorio.situacao = LIDO_APOS_O_PRAZO if relatorio.situacao == SEM_LEITURA else LIDO
        relatorio.lido_ate = agora.isoformat(timespec="seconds")
        mudou = True
        log.info("Revisao: relatorio de %s — %s (ate %s).", relatorio.rotulo, relatorio.situacao, f"{agora:%d/%m %H:%M}")
    elif prazo_vencido(relatorio, agora.date(), cfg.revisao_prazo_dias):
        if relatorio.situacao == AGUARDANDO:
            relatorio.situacao = SEM_LEITURA
            mudou = True
            log.info("Revisao: relatorio de %s sem leitura no prazo.", relatorio.rotulo)
        if not relatorio.alerta_em and _avisar_sem_leitura(cfg, relatorio, encontrado=lido is not None):
            relatorio.alerta_em = agora.isoformat(timespec="seconds")
            mudou = True

    if mudou:
        registro.gravar()
        _atualizar_planilhas(cfg)
    return mudou


def _avisar_sem_leitura(cfg: Config, relatorio: Relatorio, encontrado: bool) -> bool:
    enviado = datetime.fromisoformat(relatorio.enviado_em)
    prazo = cfg.revisao_prazo_dias
    linhas = [
        f"O relatório semanal de {relatorio.rotulo}, enviado a {', '.join(relatorio.para)} "
        f"em {enviado:%d/%m/%Y às %H:%M}, ainda não foi aberto.",
        f"O prazo de {prazo} dia{'s' if prazo > 1 else ''} út{'eis' if prazo > 1 else 'il'} venceu.",
        "",
        "A automação continua conferindo a caixa até o relatório da próxima semana. Se ele "
        'for aberto, a planilha de histórico passa a mostrar "Lido após o prazo".',
    ]
    if not encontrado:
        linhas += ["", "Observação: a mensagem não foi encontrada em nenhuma pasta da caixa — pode ter sido apagada."]
    return alerta.enviar(
        cfg,
        f"[Mapa de Estoque] Relatório semanal sem leitura — {relatorio.rotulo}",
        linhas,
        destinatarios=cfg.revisao_alerta_destinatarios,
        rodape_tecnico=False,
    )


def _avisar_falha_tecnica(
    cfg: Config, registro: Registro, relatorio: Relatorio, erro: str, agora: datetime
) -> None:
    """Avisa quem opera a automacao, uma vez por dia no maximo — a conferencia roda de hora em hora."""
    hoje = agora.date().isoformat()
    if registro.falha_avisada_em == hoje:
        return
    enviado = alerta.enviar(
        cfg,
        "[Mapa de Estoque] Conferência de leitura falhou",
        [
            f"Não consegui conferir se o relatório semanal de {relatorio.rotulo} foi lido:",
            f"  {erro}",
            "",
            "Enquanto isso não for resolvido, a planilha não registra a leitura — e a semana "
            "NÃO é marcada como sem leitura: não conferir é diferente de não ter sido lido.",
            "Confira REVISAO_IMAP_USUARIO e REVISAO_IMAP_SENHA no .env.",
        ],
    )
    if enviado:
        registro.falha_avisada_em = hoje
        registro.gravar()


def _atualizar_planilhas(cfg: Config) -> None:
    historico.atualizar(cfg.historico_path, cfg.historico_dir, revisoes=cfg.revisoes_path)


def linhas_da_aba(arquivo: Path) -> list[list[Any]]:
    """As linhas da aba Revisoes, da semana mais recente para a mais antiga."""
    linhas = []
    for r in sorted(Registro(arquivo).relatorios, key=lambda r: r.fim, reverse=True):
        enviado = datetime.fromisoformat(r.enviado_em)
        lido = f"{datetime.fromisoformat(r.lido_ate):%d/%m/%Y %H:%M}" if r.lido_ate else "—"
        linhas.append([r.rotulo, f"{enviado:%d/%m/%Y %H:%M}", lido, r.situacao])
    return linhas


def ao_fim_da_rodada(cfg: Config, erro_da_rodada: str = "") -> None:
    """Chamado pela rodada agendada: confere a leitura e manda o relatorio, se for a hora.

    Confere antes de enviar: na segunda, o relatorio novo substitui o anterior como o que
    e acompanhado, entao a ultima palavra sobre o anterior precisa vir primeiro.
    Nunca levanta — a revisao nao pode mudar o desfecho de uma rodada.
    """
    if not cfg.revisao_ligada:
        return
    try:
        conferir(cfg)
        enviar_relatorio(cfg, erro_da_rodada=erro_da_rodada)
    except Exception as erro:
        log.warning("Revisao: falhou sem derrubar a rodada: %s", erro)
        log.debug("Detalhe", exc_info=True)


def _imprimir_status(cfg: Config) -> None:
    registro = Registro(cfg.revisoes_path)
    if not registro.relatorios:
        log.info("Nenhum relatorio semanal enviado ainda (%s).", cfg.revisoes_path)
    for semana, enviado, lido, situacao in linhas_da_aba(cfg.revisoes_path):
        log.info("  %-24s enviado %s   lido ate %-16s %s", semana, enviado, lido, situacao)


def main(argv: list[str] | None = None) -> int:
    from src.log import configurar as configurar_log

    parser = argparse.ArgumentParser(prog="revisao", description="Confere a leitura do relatorio semanal.")
    parser.add_argument("--status", action="store_true", help="Mostra o registro, sem conectar a nada.")
    parser.add_argument("--debug", action="store_true", help="Log detalhado.")
    args = parser.parse_args(argv)
    configurar_log("revisao.log", logging.DEBUG if args.debug else logging.INFO)

    try:
        cfg = carregar_config()
    except ConfiguracaoInvalida as erro:
        log.error("%s", erro)
        return 2

    if args.status:
        _imprimir_status(cfg)
        return 0
    if not cfg.revisao_ligada:
        log.debug("Revisao desligada: REVISAO_PARA vazio no .env.")
        return 0

    trava = Trava(cfg.trava_path)
    if not trava.adquirir():
        log.info("Revisao: a rodada esta rodando agora; a conferencia fica para a proxima hora.")
        return 0
    try:
        conferir(cfg)
    finally:
        trava.liberar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
