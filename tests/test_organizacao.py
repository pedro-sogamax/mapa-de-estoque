"""Testes da organizacao das pastas: FABRICANTE\\2026-09\\ com todos os periodos do mes.

A pasta e o mes dos dados; o periodo exato vive no nome do arquivo. Dois lados precisam
concordar: a extracao que grava e o `--periodo` do disparo, que acha a leva antiga lendo o
nome — se divergirem, um envio de recuperacao sai sem anexo nenhum.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from src.disparo.selecao import _rotulo_do_arquivo, do_periodo, periodos_disponiveis
from src.periodo import acumulado_do_mes, intervalo, mes_cheio


def _criar(caminho: Path) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("x", encoding="utf-8")
    return caminho


class TestPastaDoMes:
    def test_mensal_vai_para_o_mes_dos_dados(self):
        """O mensal de agosto sai em setembro, mas e sobre agosto."""
        assert mes_cheio(2026, 8).pasta_do_mes == "2026-08"

    def test_acumulado_vai_para_o_proprio_mes(self):
        assert acumulado_do_mes(date(2026, 9, 14)).pasta_do_mes == "2026-09"

    def test_intervalo_que_vira_o_mes_fica_no_mes_do_inicio(self):
        assert intervalo("2026-09-28", "2026-10-02").pasta_do_mes == "2026-09"


class TestRotuloDoArquivo:
    def test_acumulado(self, tmp_path):
        arquivo = tmp_path / "MARJAN" / "2026-09" / "0112_MARJAN_2026-09-01_a_2026-09-13.xlsx"
        assert _rotulo_do_arquivo(arquivo) == "2026-09-01_a_2026-09-13"

    def test_mensal(self, tmp_path):
        arquivo = tmp_path / "MARJAN" / "2026-08" / "0105_MARJAN_2026-08.xlsx"
        assert _rotulo_do_arquivo(arquivo) == "2026-08"

    def test_fabricante_com_sublinhado_no_nome(self, tmp_path):
        arquivo = tmp_path / "EMS_RX" / "2026-08" / "0097_EMS_RX_2026-08.xlsx"
        assert _rotulo_do_arquivo(arquivo) == "2026-08"

    def test_arquivo_fora_do_padrao_e_ignorado(self, tmp_path):
        assert _rotulo_do_arquivo(tmp_path / "MARJAN" / "2026-08" / "copia do mapa.xlsx") is None


class TestDoPeriodo:
    def test_acha_o_periodo_dentro_da_pasta_do_mes(self, tmp_path):
        mes = tmp_path / "MARJAN" / "2026-08"
        _criar(mes / "0078_MARJAN_2026-08-01_a_2026-08-24.xlsx")
        mensal = _criar(mes / "0105_MARJAN_2026-08.xlsx")
        cfg = SimpleNamespace(formatado_dir=tmp_path)

        itens = do_periodo(cfg, "2026-08")

        assert [i.formatado for i in itens] == [mensal]
        assert itens[0].periodo == "agosto/2026"

    def test_reextracao_vence_o_numero_maior(self, tmp_path):
        mes = tmp_path / "ACHE" / "2026-07"
        _criar(mes / "0005_ACHE_2026-07.xlsx")
        recente = _criar(mes / "0030_ACHE_2026-07.xlsx")
        cfg = SimpleNamespace(formatado_dir=tmp_path)

        assert [i.formatado for i in do_periodo(cfg, "2026-07")] == [recente]

    def test_periodos_disponiveis_vem_dos_nomes(self, tmp_path):
        _criar(tmp_path / "MARJAN" / "2026-08" / "0078_MARJAN_2026-08-01_a_2026-08-24.xlsx")
        _criar(tmp_path / "MARJAN" / "2026-08" / "0105_MARJAN_2026-08.xlsx")
        cfg = SimpleNamespace(formatado_dir=tmp_path)

        assert periodos_disponiveis(cfg) == ["2026-08-01_a_2026-08-24", "2026-08"]
