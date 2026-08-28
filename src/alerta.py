"""Aviso por e-mail quando a rodada nao sai como devia.

Ate aqui, uma rodada que falhasse as 07:00 aparecia so no log e no codigo de saida — e a
tarefa agendada roda sem ninguem olhando. O mapa de um laboratorio podia simplesmente nao
sair por dias sem que ninguem soubesse. Era a pendencia registrada em docs/disparo.md §10.

O canal de e-mail ja existe, ja esta configurado e ja sabe reconectar e repetir
(src/disparo/canais/email_smtp.py). Este modulo so monta o resumo e o entrega por ele.

NAO passa pelo roteador do disparo, de proposito: cota horaria, disjuntor e envios.json
existem para proteger as INDUSTRIAS de receber demais. O alerta e uma mensagem interna, e
ficar preso numa cota seria perder justamente o aviso do dia em que tudo deu errado.

Falhar ao avisar nunca derruba a rodada: o alerta e a ultima coisa a acontecer e o que ele
relata ja esta no log.
"""

from __future__ import annotations

import logging
from datetime import datetime

from src.config import Config
from src.disparo.canais.base import Destino, FalhaNoEnvio, Mensagem
from src.disparo.canais.email_smtp import CanalEmail

log = logging.getLogger(__name__)

# Um alerta nao pode virar o problema. Se a rodada quebrou em 24 laboratorios, o e-mail
# precisa caber numa tela e dizer o essencial; o resto esta no log.
MAX_LINHAS = 40


def enviar(cfg: Config, assunto: str, linhas: list[str]) -> bool:
    """Manda o resumo para cfg.alerta_destinatarios. Devolve True se saiu.

    Nunca levanta: qualquer falha vira aviso no log. Quem chama esta terminando a rodada e
    ja tem o desfecho para reportar pelo codigo de saida.
    """
    destinatarios = cfg.alerta_destinatarios
    if not destinatarios:
        log.warning("Sem destinatario para o alerta: preencha ALERTA_PARA no .env.")
        return False
    if not cfg.email_configurado:
        log.warning("Alerta nao enviado: SMTP nao configurado no .env.")
        return False

    corpo = _montar_corpo(linhas)
    destino = Destino(fabricante="alerta", emails=tuple(destinatarios))

    try:
        with CanalEmail(cfg) as canal:
            canal.enviar(destino, Mensagem(assunto=assunto, corpo=corpo), anexo=None)
    except (FalhaNoEnvio, OSError) as erro:
        # Se o proprio e-mail e o que esta quebrado, insistir aqui nao ajuda em nada.
        log.error("Nao consegui enviar o alerta para %s: %s", ", ".join(destinatarios), erro)
        return False

    log.info("Alerta enviado para %s.", ", ".join(destinatarios))
    return True


def _montar_corpo(linhas: list[str]) -> str:
    """Texto puro, sem assinatura: e uma mensagem de servico, nao um mapa."""
    mostradas = linhas[:MAX_LINHAS]
    if len(linhas) > MAX_LINHAS:
        mostradas.append(f"... e mais {len(linhas) - MAX_LINHAS} linha(s) — veja logs/execucao.log.")
    rodape = [
        "",
        "-" * 62,
        f"Mapa de Estoque — automacao, {datetime.now():%d/%m/%Y %H:%M}.",
        "Detalhes em logs/execucao.log e logs/disparo.log.",
    ]
    return "\n".join(mostradas + rodape)
