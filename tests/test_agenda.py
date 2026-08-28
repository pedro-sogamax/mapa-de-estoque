"""Testes de src/agenda.py — quem roda hoje, e por que.

A agenda decide o que a rodada das 07:00 vai gerar. Errar aqui significa um laboratorio
nao receber o mapa (silencioso) ou receber duas vezes. Nada aqui toca rede ou navegador.

Datas de referencia em agosto/2026 (o mes comeca num sabado):
    01/08 sabado · 02/08 domingo · 03/08 SEGUNDA = 1o dia util · 05/08 quarta
"""

from __future__ import annotations

from datetime import date

import pytest

from src.agenda import tarefas_com_periodo_fixo, tarefas_do_dia
from src.config import Fabricante
from src.estado import EstadoDaAgenda
from src.periodo import mes_cheio

PRIMEIRO_DIA_UTIL = date(2026, 8, 3)  # segunda
QUARTA = date(2026, 8, 5)
SABADO = date(2026, 8, 8)
JULHO = "2026-07"


def fab(nome: str, *, mensal: bool = True, dias: tuple[str, ...] = (), janela: str = "acumulado_mes"):
    return Fabricante(
        nome=nome,
        codigos=("1234",),
        mensal=mensal,
        dias_semana=dias,
        janela_semanal=janela,
    )


@pytest.fixture
def estado(tmp_path):
    """Estado limpo, num arquivo temporario — nunca toca o estado.json de producao."""
    return EstadoDaAgenda(tmp_path / "estado.json")


class TestMensal:
    def test_dispara_no_primeiro_dia_util(self, estado):
        tarefas, _ = tarefas_do_dia([fab("ACHE")], PRIMEIRO_DIA_UTIL, estado)
        assert [(t.fabricante.nome, t.motivo, t.periodo.rotulo) for t in tarefas] == [
            ("ACHE", "mensal", JULHO)
        ]

    def test_nao_dispara_antes_do_primeiro_dia_util(self, estado):
        """01/08 e sabado: nao ha expediente, o mensal espera."""
        tarefas, _ = tarefas_do_dia([fab("ACHE")], date(2026, 8, 1), estado)
        assert tarefas == []

    def test_nao_repete_o_mes_ja_entregue(self, estado):
        estado.registrar_mensal("ACHE", JULHO)
        tarefas, _ = tarefas_do_dia([fab("ACHE")], PRIMEIRO_DIA_UTIL, estado)
        assert tarefas == []

    def test_recupera_o_mes_perdido_num_dia_posterior(self, estado):
        """A maquina desligada no dia 3 nao pode fazer o mapa do mes desaparecer."""
        tarefas, avisos = tarefas_do_dia([fab("ACHE")], QUARTA, estado)
        assert [t.motivo for t in tarefas] == ["mensal"]
        assert tarefas[0].periodo.rotulo == JULHO
        assert any("RECUPERANDO" in a for a in avisos)

    def test_recuperacao_avisa_quem_ficou_para_tras(self, estado):
        estado.registrar_mensal("ACHE", JULHO)
        tarefas, avisos = tarefas_do_dia([fab("ACHE"), fab("MARJAN")], QUARTA, estado)
        assert [t.fabricante.nome for t in tarefas] == ["MARJAN"]
        recuperando = [a for a in avisos if "RECUPERANDO" in a]
        assert len(recuperando) == 1
        assert "MARJAN" in recuperando[0] and "ACHE" not in recuperando[0]

    def test_fabricante_sem_mensal_nao_gera_mensal(self, estado):
        tarefas, _ = tarefas_do_dia(
            [fab("SO_SEMANAL", mensal=False, dias=("segunda",))], PRIMEIRO_DIA_UTIL, estado
        )
        assert [t.motivo for t in tarefas] == []  # segunda, mas o acumulado ainda esta vazio

    def test_sem_estado_so_dispara_no_proprio_primeiro_dia_util(self):
        """Modo --planejar sem consultar o entregue: util para simular uma data."""
        assert len(tarefas_do_dia([fab("ACHE")], PRIMEIRO_DIA_UTIL, None)[0]) == 1
        assert tarefas_do_dia([fab("ACHE")], QUARTA, None)[0] == []


class TestSemanal:
    def test_dispara_no_dia_cadastrado(self, estado):
        tarefas, _ = tarefas_do_dia([fab("MARJAN", dias=("quarta",))], QUARTA, estado)
        semanais = [t for t in tarefas if t.motivo.startswith("semanal")]
        assert [t.motivo for t in semanais] == ["semanal/quarta"]
        assert semanais[0].periodo.rotulo == "2026-08-01_a_2026-08-04"

    def test_nao_dispara_em_dia_nao_cadastrado(self, estado):
        estado.registrar_mensal("MARJAN", JULHO)
        tarefas, _ = tarefas_do_dia([fab("MARJAN", dias=("segunda",))], QUARTA, estado)
        assert tarefas == []

    def test_fim_de_semana_nao_gera_semanal(self, estado):
        estado.registrar_mensal("MARJAN", JULHO)
        tarefas, avisos = tarefas_do_dia([fab("MARJAN", dias=("segunda",))], SABADO, estado)
        assert tarefas == []
        assert any("fim de semana" in a for a in avisos)

    def test_janela_semana_fechada(self, estado):
        estado.registrar_mensal("X", JULHO)
        tarefas, _ = tarefas_do_dia(
            [fab("X", dias=("quarta",), janela="semana_fechada")], QUARTA, estado
        )
        assert tarefas[0].periodo.rotulo == "2026-07-27_a_2026-07-31"

    def test_no_primeiro_dia_util_o_mensal_cobre_o_semanal(self, estado):
        """Unico dia do mes em que o acumulado esta vazio: o mes fechado sai no lugar,
        e o fabricante NAO fica sem receber."""
        tarefas, avisos = tarefas_do_dia(
            [fab("MARJAN", dias=("segunda",))], PRIMEIRO_DIA_UTIL, estado
        )
        assert [t.motivo for t in tarefas] == ["mensal"]
        assert any("coberto pelo mensal" in a for a in avisos)


class TestOsDoisNoMesmoDia:
    def test_mensal_e_semanal_geram_dois_relatorios_de_periodos_diferentes(self, estado):
        """Quem tem os dois envios gera DOIS arquivos — periodos e rotulos diferentes,
        senao um sobrescreveria o outro na pasta do fabricante."""
        tarefas, _ = tarefas_do_dia([fab("MARJAN", dias=("quarta",))], QUARTA, estado)
        assert sorted(t.motivo for t in tarefas) == ["mensal", "semanal/quarta"]
        rotulos = {t.periodo.rotulo for t in tarefas}
        assert len(rotulos) == 2


class TestPeriodoFixo:
    def test_rodada_manual_ignora_a_agenda(self):
        """--mes 2026-07: o mesmo periodo para todos, sem olhar o dia nem o estado."""
        fabricantes = [fab("ACHE"), fab("MARJAN", mensal=False, dias=("segunda",))]
        tarefas = tarefas_com_periodo_fixo(fabricantes, mes_cheio(2026, 7))
        assert len(tarefas) == 2
        assert {t.motivo for t in tarefas} == {"manual"}
        assert {t.periodo.rotulo for t in tarefas} == {JULHO}
