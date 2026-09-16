"""Decide QUAIS relatorios a rodada de hoje deve gerar.

A planilha "docs/ENVIO MAPA.xlsx" define dois envios independentes:

* mensal  — todos os fabricantes, a partir do 1o dia util do mes, cobrindo o mes anterior;
* semanal — so quem tem X num dia da semana, cobrindo o mes corrente ate ontem.

Quem tem os dois pode gerar DOIS relatorios no mesmo dia — sao periodos diferentes,
arquivos diferentes. A excecao e o proprio 1o dia util do mes: ali o acumulado ainda nao
tem nenhum dia util (veja acumulado_do_mes), e o envio semanal fica coberto pelo mensal
do mes fechado, que sai no mesmo dia. E o unico dia do mes em que isso ocorre.

O mensal e RECUPERAVEL: em vez de "hoje e o 1o dia util", a condicao e "o mes anterior
ainda nao foi entregue a este fabricante" (veja src/estado.py). Assim uma maquina desligada
no dia certo nao faz o mapa do mes desaparecer em silencio — a proxima rodada o pega. No
caso normal nada muda, porque no 1o dia util nada esta registrado ainda.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.config import Fabricante
from src.estado import EstadoDaAgenda
from src.periodo import (
    NOME_DO_DIA,
    Periodo,
    janela_semanal,
    mes_anterior,
    primeiro_dia_util,
)


@dataclass(frozen=True)
class Tarefa:
    """Uma extracao a executar: um fabricante num periodo, com o motivo do disparo."""

    fabricante: Fabricante
    periodo: Periodo
    motivo: str

    def __str__(self) -> str:
        return f"{self.fabricante.nome} [{self.motivo}] {self.periodo}"


def tarefas_do_dia(
    fabricantes: list[Fabricante],
    hoje: date | None = None,
    estado: EstadoDaAgenda | None = None,
) -> tuple[list[Tarefa], list[str]]:
    """Monta o plano do dia. Devolve (tarefas, avisos do que foi dispensado e por que).

    Sem `estado`, o mensal so dispara no proprio 1o dia util — util para simular o plano
    de uma data sem consultar o que ja foi entregue de verdade.
    """
    referencia = hoje or date.today()
    dia_de_hoje = NOME_DO_DIA.get(referencia.weekday())
    primeiro_util = primeiro_dia_util(referencia.year, referencia.month)
    mes_a_entregar = mes_anterior(referencia)

    tarefas: list[Tarefa] = []
    avisos: list[str] = []
    atrasados: list[str] = []

    for fabricante in fabricantes:
        if fabricante.mensal and referencia >= primeiro_util:
            if estado is None:
                pendente = referencia == primeiro_util
            else:
                pendente = not estado.ja_gerou_mensal(fabricante.nome, mes_a_entregar.rotulo)
            if pendente:
                tarefas.append(Tarefa(fabricante, mes_a_entregar, "mensal"))
                if referencia > primeiro_util:
                    atrasados.append(fabricante.nome)

        if dia_de_hoje and dia_de_hoje in fabricante.dias_semana:
            periodo = janela_semanal(fabricante.janela_semanal, referencia)
            if periodo is None:
                # Sem acumulado ha dois motivos, e o log precisa dizer qual. No 1o dia util
                # o mensal do mes fechado sai no lugar; antes dele (dia 1o em feriado, por
                # exemplo) nao ha expediente nenhum e o envio so espera.
                avisos.append(
                    f"{fabricante.nome}: envio de {dia_de_hoje} coberto pelo mensal de "
                    f"{mes_a_entregar.rotulo} — hoje e o 1o dia util do mes e o mes fechado "
                    "sai no lugar do acumulado."
                    if referencia == primeiro_util
                    else f"{fabricante.nome}: envio de {dia_de_hoje} adiado — "
                    f"{referencia:%d/%m/%Y} nao e dia de expediente e o mes ainda nao tem "
                    f"nada acumulado; o 1o dia util e {primeiro_util:%d/%m/%Y}."
                )
            else:
                tarefas.append(Tarefa(fabricante, periodo, f"semanal/{dia_de_hoje}"))

    if atrasados:
        avisos.append(
            f"RECUPERANDO o mensal de {mes_a_entregar.rotulo}, que devia ter saido em "
            f"{primeiro_util:%d/%m/%Y}: {', '.join(atrasados)}."
        )
    elif not any(t.motivo == "mensal" for t in tarefas):
        avisos.append(
            f"Mensal de {mes_a_entregar.rotulo} nao roda hoje ({referencia:%d/%m/%Y}): "
            "ja foi entregue a todos os fabricantes."
            if estado is not None and referencia >= primeiro_util
            else f"Mensal nao roda hoje ({referencia:%d/%m/%Y}): so a partir do 1o dia util."
        )
    if dia_de_hoje is None:
        avisos.append(f"{referencia:%d/%m/%Y} e fim de semana — nenhum envio semanal.")

    return tarefas, avisos


def tarefas_com_periodo_fixo(fabricantes: list[Fabricante], periodo: Periodo) -> list[Tarefa]:
    """Rodada manual (--mes / --inicio+--fim): o mesmo periodo para todos, sem olhar o dia."""
    return [Tarefa(f, periodo, "manual") for f in fabricantes]
