"""Testes da organizacao das pastas: FABRICANTE\\2026-09\\ com todos os periodos do mes.

A pasta e o mes dos dados; o periodo exato vive no nome do arquivo. Dois lados precisam
concordar: a extracao que grava e o `--periodo` do disparo, que acha a leva antiga lendo o
nome — se divergirem, um envio de recuperacao sai sem anexo nenhum.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from src.config import Comprador, Fabricante
from src.disparo.selecao import _rotulo_do_arquivo, do_periodo, periodos_disponiveis
from src.main import _pasta_do_comprador
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


class TestPastaDoComprador:
    """A arvore ganhou um nivel: COMPRADOR/FABRICANTE/2026-09/arquivo.xlsx.

    O que a industria recebe nao muda — muda so onde o arquivo fica, para cada comprador
    achar a propria carteira na pasta do ownCloud sem filtrar 46 laboratorios.
    """

    def _fabricante(self, nome, comprador=None):
        return Fabricante(
            nome=nome,
            codigos=("123",),
            comprador=Comprador(nome=comprador) if comprador else None,
        )

    def test_usa_o_comprador_do_laboratorio(self):
        cfg = SimpleNamespace(comprador="Yuri Toso")
        fabricante = self._fabricante("BLAU", comprador="Geliana Ferreira")

        assert _pasta_do_comprador(fabricante, cfg) == "Geliana Ferreira"

    def test_sem_bloco_cai_no_comprador_do_env(self):
        """E o que mantem a arvore certa enquanto o cadastro nao tem os blocos."""
        cfg = SimpleNamespace(comprador="Yuri Toso")

        assert _pasta_do_comprador(self._fabricante("MARJAN"), cfg) == "Yuri Toso"

    def test_sem_comprador_nenhum_a_pasta_denuncia(self):
        cfg = SimpleNamespace(comprador="")

        assert _pasta_do_comprador(self._fabricante("MARJAN"), cfg) == "SEM_COMPRADOR"

    def test_disparo_acha_o_relatorio_na_arvore_com_comprador(self, tmp_path):
        arquivo = _criar(
            tmp_path / "Geliana Ferreira" / "BLAU" / "2026-08" / "0120_BLAU_2026-08.xlsx"
        )
        cfg = SimpleNamespace(formatado_dir=tmp_path)

        itens = do_periodo(cfg, "2026-08")

        assert [i.formatado for i in itens] == [arquivo]
        assert itens[0].fabricante == "BLAU"

    def test_as_duas_arvores_convivem(self, tmp_path):
        """O historico gravado antes da mudanca continua sendo encontrado, sem migracao."""
        antigo = _criar(tmp_path / "MARJAN" / "2026-08" / "0105_MARJAN_2026-08.xlsx")
        novo = _criar(
            tmp_path / "Geliana Ferreira" / "BLAU" / "2026-08" / "0120_BLAU_2026-08.xlsx"
        )
        cfg = SimpleNamespace(formatado_dir=tmp_path)

        achados = {i.fabricante: i.formatado for i in do_periodo(cfg, "2026-08")}

        assert achados == {"MARJAN": antigo, "BLAU": novo}
