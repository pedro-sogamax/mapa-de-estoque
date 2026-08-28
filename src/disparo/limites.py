"""Defesas contra descontrole no envio.

As travas que ja existiam protegem contra engano humano: a confirmacao, o DESTINATARIO_TESTE
e o envios.json. Este modulo cobre o outro lado — o sistema disparando alem do razoavel:

- **CotaDeEnvio**: nao passar do que o provedor aceita por hora;
- **Disjuntor**: parar de insistir com um servidor que ja esta recusando;
- **teto por rodada**: recusar uma leva grande demais antes de conectar.

Todas param a leva com uma explicacao. Nenhuma silencia nada: o que nao saiu aparece no
resumo, e o registro em disco diz o que ja tinha saido.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

JANELA = timedelta(hours=1)


class LimiteAtingido(Exception):
    """A leva precisa parar. A mensagem explica o motivo e o que fazer."""


@dataclass
class CotaDeEnvio:
    """Quantas mensagens sairam por canal na ultima hora.

    O historico fica em logs/envios.jsonl, uma linha por mensagem, so acrescentando. Serve
    para duas coisas: contar a cota e ser o registro de auditoria do que realmente saiu — o
    envios.json guarda apenas o ULTIMO envio de cada chave, entao um reenvio apagaria o
    rastro do anterior.
    """

    arquivo: Path
    maximo_por_hora: int
    _marcas: list[tuple[datetime, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._marcas = self._carregar()

    def _carregar(self) -> list[tuple[datetime, str]]:
        if not self.arquivo.exists():
            return []
        marcas: list[tuple[datetime, str]] = []
        for linha in self.arquivo.read_text(encoding="utf-8").splitlines():
            if not linha.strip():
                continue
            try:
                registro = json.loads(linha)
                marcas.append((datetime.fromisoformat(registro["em"]), str(registro["canal"])))
            except (ValueError, KeyError, TypeError):
                # Linha corrompida conta a menos na cota, o que e conservador na direcao
                # errada — mas descartar o historico inteiro seria pior.
                log.debug("Linha ilegivel em %s, ignorada", self.arquivo.name)
        return marcas

    def usados(self, canal: str, agora: datetime | None = None) -> int:
        limite = (agora or datetime.now()) - JANELA
        return sum(1 for em, c in self._marcas if c == canal and em > limite)

    def restantes(self, canal: str, agora: datetime | None = None) -> int:
        return max(0, self.maximo_por_hora - self.usados(canal, agora))

    def liberacao(self, canal: str, agora: datetime | None = None) -> datetime | None:
        """Quando a janela abre espaco de novo — o instante do envio mais antigo + 1h."""
        agora = agora or datetime.now()
        recentes = sorted(em for em, c in self._marcas if c == canal and em > agora - JANELA)
        return recentes[0] + JANELA if recentes else None

    def conferir(self, canal: str, agora: datetime | None = None) -> None:
        """Levanta LimiteAtingido se nao ha mais espaco para este canal."""
        if self.restantes(canal, agora) > 0:
            return
        quando = self.liberacao(canal, agora)
        horario = quando.strftime("%H:%M") if quando else "daqui a uma hora"
        raise LimiteAtingido(
            f"Cota de {self.maximo_por_hora} mensagem(ns) por hora atingida no canal {canal}. "
            f"Rode de novo a partir das {horario} — o que ja saiu esta registrado e nao "
            "sera reenviado."
        )

    def registrar(self, canal: str, fabricante: str, identificador: str) -> None:
        """Anota a mensagem que acabou de sair. Grava na hora, so acrescentando."""
        agora = datetime.now()
        self._marcas.append((agora, canal))
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        registro = {
            "em": agora.isoformat(timespec="seconds"),
            "canal": canal,
            "fabricante": fabricante,
            "id": identificador,
        }
        with self.arquivo.open("a", encoding="utf-8") as saida:
            saida.write(json.dumps(registro, ensure_ascii=False) + "\n")


@dataclass
class Disjuntor:
    """Desliga um canal depois de N falhas consecutivas.

    O alvo e a falha sistematica — senha revogada, servidor barrando, sessao do WhatsApp
    caida —, nao o erro isolado de um endereco. Por isso o contador zera a cada sucesso:
    tres falhas seguidas dizem que o proximo tambem vai falhar, e insistir 24 vezes num
    servidor que ja recusou e exatamente o que faz um provedor suspender a conta.
    """

    maximo: int
    _seguidas: dict[str, int] = field(default_factory=dict)
    _desligados: dict[str, str] = field(default_factory=dict)

    def registrar_sucesso(self, canal: str) -> None:
        self._seguidas[canal] = 0

    def registrar_falha(self, canal: str, motivo: str) -> None:
        self._seguidas[canal] = self._seguidas.get(canal, 0) + 1
        if self._seguidas[canal] >= self.maximo:
            self._desligados[canal] = motivo

    def desligar(self, canal: str, motivo: str) -> None:
        """Desliga na hora, sem esperar as falhas — para cota atingida, por exemplo."""
        self._desligados[canal] = motivo

    def desligado(self, canal: str) -> bool:
        return canal in self._desligados

    def motivo(self, canal: str) -> str:
        return self._desligados.get(canal, "")

    @property
    def canais_desligados(self) -> dict[str, str]:
        return dict(self._desligados)


def conferir_teto(quantidade: int, maximo: int, forcar: bool) -> None:
    """Recusa uma leva grande demais ANTES de qualquer conexao.

    Sao 24 laboratorios reais. Uma leva muito maior quase sempre significa cadastro
    duplicado ou manifesto errado — e com --sim isso viraria centenas de mensagens antes de
    alguem notar.
    """
    if forcar or quantidade <= maximo:
        return
    raise LimiteAtingido(
        f"A leva tem {quantidade} mensagens, acima do teto de {maximo}. Isso costuma indicar "
        "cadastro duplicado no fabricantes.yaml ou um manifesto errado. Confira com "
        "--dry-run; se estiver certo mesmo, use --forcar ou aumente MAX_ENVIOS_POR_RODADA."
    )
