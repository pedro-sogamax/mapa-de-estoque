"""Testes de src/periodo.py — o calendario que decide QUAL periodo cada mapa cobre.

E a parte mais perigosa do projeto por ser silenciosa: um erro aqui nao quebra a rodada,
apenas manda o mes errado para a industria. Nada aqui toca rede ou navegador.

As datas usadas sao reais e conferidas contra holidays.Brazil():
    2026-01-01 quinta, feriado (Confraternizacao) -> 1o dia util e 02/01 (sexta)
    2026-02-01 domingo                            -> 1o dia util e 02/02 (segunda)
    2026-08-01 sabado                             -> 1o dia util e 03/08 (segunda)
    2026-11-02 segunda, feriado (Finados)         -> 1o dia util e 03/11 (terca)
    2026-09-01 terca, dia comum                   -> 1o dia util e o proprio 01/09
"""

from __future__ import annotations

from datetime import date

import pytest

from src.periodo import (
    JANELAS_SEMANAIS,
    Periodo,
    PeriodoInvalido,
    acumulado_do_mes,
    eh_dia_util,
    eh_primeiro_dia_util_do_mes,
    intervalo,
    janela_semanal,
    mes_anterior,
    mes_cheio,
    normalizar_dia,
    primeiro_dia_util,
    resolver_periodo,
    semana_anterior,
)


class TestMesCheio:
    def test_mes_comum(self):
        p = mes_cheio(2026, 7)
        assert (p.inicio, p.fim) == (date(2026, 7, 1), date(2026, 7, 31))

    def test_fevereiro_bissexto(self):
        assert mes_cheio(2028, 2).fim == date(2028, 2, 29)

    def test_fevereiro_comum(self):
        assert mes_cheio(2026, 2).fim == date(2026, 2, 28)

    @pytest.mark.parametrize("mes", [0, 13, -1])
    def test_mes_fora_do_intervalo(self, mes):
        with pytest.raises(PeriodoInvalido):
            mes_cheio(2026, mes)


class TestMesAnterior:
    def test_no_meio_do_ano(self):
        assert mes_anterior(date(2026, 8, 3)).rotulo == "2026-07"

    def test_em_janeiro_volta_para_dezembro_do_ano_anterior(self):
        """A virada de ano e o unico caso em que o ano muda — e o mais facil de errar."""
        p = mes_anterior(date(2026, 1, 2))
        assert (p.inicio, p.fim) == (date(2025, 12, 1), date(2025, 12, 31))


class TestRotulo:
    def test_mes_cheio_vira_aaaa_mm(self):
        assert mes_cheio(2026, 7).rotulo == "2026-07"

    def test_intervalo_livre_nunca_colide_com_o_mensal(self):
        """O semanal e o mensal do mesmo mes gravam na MESMA pasta do fabricante:
        se os rotulos coincidissem, um sobrescreveria o outro."""
        semanal = Periodo(date(2026, 7, 1), date(2026, 7, 7))
        assert semanal.rotulo == "2026-07-01_a_2026-07-07"
        assert semanal.rotulo != mes_cheio(2026, 7).rotulo

    def test_mes_cheio_reconhece_o_ultimo_dia_real(self):
        assert Periodo(date(2026, 2, 1), date(2026, 2, 28)).mes_cheio is True
        assert Periodo(date(2026, 2, 1), date(2026, 2, 27)).mes_cheio is False

    def test_formato_brasileiro(self):
        p = Periodo(date(2026, 7, 1), date(2026, 7, 31))
        assert str(p) == "01/07/2026 a 31/07/2026"


class TestDiaUtil:
    def test_dia_comum(self):
        assert eh_dia_util(date(2026, 8, 28)) is True  # sexta

    @pytest.mark.parametrize("dia", [date(2026, 8, 1), date(2026, 8, 2)])  # sabado, domingo
    def test_fim_de_semana(self, dia):
        assert eh_dia_util(dia) is False

    @pytest.mark.parametrize(
        "feriado",
        [date(2026, 1, 1), date(2026, 4, 3), date(2026, 11, 2), date(2026, 12, 25)],
    )
    def test_feriado_nacional(self, feriado):
        """Sem o feriado, os 24 mensais disparariam com a empresa fechada."""
        assert eh_dia_util(feriado) is False


class TestPrimeiroDiaUtil:
    def test_pula_feriado_de_ano_novo(self):
        assert primeiro_dia_util(2026, 1) == date(2026, 1, 2)

    def test_pula_domingo(self):
        assert primeiro_dia_util(2026, 2) == date(2026, 2, 2)

    def test_pula_fim_de_semana_inteiro(self):
        assert primeiro_dia_util(2026, 8) == date(2026, 8, 3)

    def test_pula_feriado_em_dia_de_semana(self):
        """01/11 domingo + 02/11 Finados: o mensal so sai na terca."""
        assert primeiro_dia_util(2026, 11) == date(2026, 11, 3)

    def test_dia_primeiro_util_e_ele_mesmo(self):
        assert primeiro_dia_util(2026, 9) == date(2026, 9, 1)

    def test_eh_primeiro_dia_util_do_mes(self):
        assert eh_primeiro_dia_util_do_mes(date(2026, 8, 3)) is True
        assert eh_primeiro_dia_util_do_mes(date(2026, 8, 4)) is False
        assert eh_primeiro_dia_util_do_mes(date(2026, 8, 1)) is False  # sabado


class TestSemanaAnterior:
    def test_segunda_devolve_a_semana_fechada_anterior(self):
        p = semana_anterior(date(2026, 8, 3))  # segunda
        assert (p.inicio, p.fim) == (date(2026, 7, 27), date(2026, 7, 31))

    def test_nunca_inclui_a_semana_corrente(self):
        """Rodar na quarta nao pode devolver a semana que ainda nao fechou."""
        p = semana_anterior(date(2026, 8, 5))  # quarta
        assert p.fim == date(2026, 7, 31)
        assert p.fim < date(2026, 8, 5)

    def test_a_propria_sexta_nao_conta_como_semana_fechada(self):
        """Na sexta o dia ainda nao acabou: a ancora e a sexta ANTERIOR."""
        p = semana_anterior(date(2026, 8, 7))  # sexta
        assert p.fim == date(2026, 7, 31)

    def test_sabado_e_a_segunda_seguinte_devolvem_a_mesma_semana(self):
        """A janela nao pode mudar conforme o dia em que a rodada atrasou."""
        assert semana_anterior(date(2026, 8, 8)) == semana_anterior(date(2026, 8, 10))

    def test_sempre_segunda_a_sexta(self):
        p = semana_anterior(date(2026, 8, 3))
        assert p.inicio.weekday() == 0 and p.fim.weekday() == 4
        assert (p.fim - p.inicio).days == 4


class TestAcumuladoDoMes:
    def test_vai_do_dia_primeiro_ate_ontem(self):
        p = acumulado_do_mes(date(2026, 8, 10))
        assert (p.inicio, p.fim) == (date(2026, 8, 1), date(2026, 8, 9))

    def test_dia_primeiro_nao_tem_ontem_dentro_do_mes(self):
        assert acumulado_do_mes(date(2026, 8, 1)) is None

    def test_none_enquanto_o_mes_nao_teve_expediente(self):
        """Agosto/2026 comeca sabado: na segunda (1o dia util) o acumulado seria so
        sabado+domingo. Nesse dia o mensal do mes fechado sai no lugar."""
        assert acumulado_do_mes(date(2026, 8, 3)) is None

    def test_ja_ha_acumulado_no_dia_seguinte_ao_primeiro_util(self):
        p = acumulado_do_mes(date(2026, 8, 4))
        assert p is not None and p.fim == date(2026, 8, 3)

    def test_none_ocorre_so_ate_o_primeiro_dia_util(self):
        """Depois do 1o dia util o acumulado sempre existe — o resto do mes sempre gera."""
        vazios = [d for d in range(1, 32) if acumulado_do_mes(date(2026, 8, d)) is None]
        assert vazios == [1, 2, 3]  # sabado, domingo e o proprio 1o dia util


class TestJanelaSemanal:
    def test_acumulado_mes(self):
        assert janela_semanal("acumulado_mes", date(2026, 8, 10)) == acumulado_do_mes(
            date(2026, 8, 10)
        )

    def test_semana_fechada(self):
        assert janela_semanal("semana_fechada", date(2026, 8, 10)) == semana_anterior(
            date(2026, 8, 10)
        )

    def test_tipo_desconhecido(self):
        with pytest.raises(PeriodoInvalido):
            janela_semanal("quinzenal", date(2026, 8, 10))

    def test_todas_as_janelas_cadastraveis_funcionam(self):
        """Garante que JANELAS_SEMANAIS (usada na validacao do cadastro) e janela_semanal
        nao saiam de sincronia — aceitar no cadastro e falhar na rodada seria pior."""
        for tipo in JANELAS_SEMANAIS:
            janela_semanal(tipo, date(2026, 8, 10))


class TestNormalizarDia:
    @pytest.mark.parametrize(
        "bruto",
        ["TERÇA-FEIRA", "terça", "Terca", " TERCA ", "terça-feira", "TERCA-FEIRA"],
    )
    def test_variacoes_da_planilha_chegam_ao_mesmo_dia(self, bruto):
        assert normalizar_dia(bruto) == "terca"

    def test_segunda_e_sexta(self):
        assert normalizar_dia("SEGUNDA-FEIRA") == "segunda"
        assert normalizar_dia("Sexta-Feira") == "sexta"


class TestIntervalo:
    def test_periodo_livre(self):
        p = intervalo("2026-07-01", "2026-07-07")
        assert (p.inicio, p.fim) == (date(2026, 7, 1), date(2026, 7, 7))

    def test_fim_antes_do_inicio(self):
        with pytest.raises(PeriodoInvalido):
            intervalo("2026-07-07", "2026-07-01")

    def test_formato_invalido(self):
        with pytest.raises(PeriodoInvalido):
            intervalo("01/07/2026", "07/07/2026")

    def test_data_inexistente(self):
        with pytest.raises(PeriodoInvalido):
            intervalo("2026-02-30", "2026-03-01")


class TestResolverPeriodo:
    def test_sem_argumento_devolve_none_e_a_agenda_decide(self):
        assert resolver_periodo() is None

    def test_mes(self):
        assert resolver_periodo(mes="2026-07").rotulo == "2026-07"

    def test_inicio_e_fim(self):
        p = resolver_periodo(inicio="2026-07-01", fim="2026-07-07")
        assert p.rotulo == "2026-07-01_a_2026-07-07"

    def test_mes_junto_com_intervalo(self):
        with pytest.raises(PeriodoInvalido):
            resolver_periodo(mes="2026-07", inicio="2026-07-01", fim="2026-07-07")

    @pytest.mark.parametrize("kwargs", [{"inicio": "2026-07-01"}, {"fim": "2026-07-07"}])
    def test_inicio_ou_fim_sozinho(self, kwargs):
        with pytest.raises(PeriodoInvalido):
            resolver_periodo(**kwargs)

    def test_mes_em_formato_errado(self):
        with pytest.raises(PeriodoInvalido):
            resolver_periodo(mes="07/2026")
