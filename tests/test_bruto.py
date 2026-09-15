"""Testes do descarte do arquivo bruto do Geweb.

So o .xlsx formatado e guardado. Tres coisas nao podem quebrar com isso: o numero sequencial
nunca se repete (ele se recompunha pela pasta do bruto, que agora fica vazia), a pasta raiz
do DOWNLOAD_DIR nunca some, e o manifesto da rodada continua achando o anexo.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.main import _descartar_bruto
from src.rodada import ItemDaRodada, gravar, ler
from src.sequencia import Sequencia


def _criar(caminho: Path) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("x", encoding="utf-8")
    return caminho


class TestDescartarBruto:
    def test_apaga_o_arquivo_e_as_pastas_vazias(self, tmp_path):
        raiz = tmp_path / "downloads"
        bruto = _criar(raiz / "ACHE" / "2026-08" / "0089_ACHE_2026-08.xls")

        assert _descartar_bruto(bruto, raiz) is True
        assert not bruto.exists()
        assert not (raiz / "ACHE").exists()
        assert raiz.exists(), "a raiz do DOWNLOAD_DIR nunca e removida"

    def test_mantem_pasta_que_ainda_tem_conteudo(self, tmp_path):
        """Um bruto antigo, de antes do descarte, nao pode levar a pasta embora."""
        raiz = tmp_path / "downloads"
        bruto = _criar(raiz / "ACHE" / "2026-09" / "0120_ACHE_2026-09.xls")
        antigo = _criar(raiz / "ACHE" / "2026-08" / "0089_ACHE_2026-08.xls")

        assert _descartar_bruto(bruto, raiz) is True
        assert not (raiz / "ACHE" / "2026-09").exists()
        assert antigo.exists()

    def test_arquivo_que_nao_existe_nao_derruba(self, tmp_path):
        raiz = tmp_path / "downloads"
        raiz.mkdir()
        assert _descartar_bruto(raiz / "ACHE" / "0001_ACHE.xls", raiz) is False


class TestSequenciaSemBruto:
    def test_recompoe_pela_pasta_do_formatado(self, tmp_path):
        """Sem sequencia.json e com o bruto descartado, o maior numero so existe no formatado."""
        downloads, formatado = tmp_path / "downloads", tmp_path / "formatado"
        downloads.mkdir()
        _criar(formatado / "ACHE" / "2026-08" / "0111_ACHE_2026-08.xlsx")

        sequencia = Sequencia(tmp_path / "sequencia.json", downloads, formatado)
        assert sequencia.proximo() == 112

    def test_pasta_inexistente_e_ignorada(self, tmp_path):
        sequencia = Sequencia(tmp_path / "sequencia.json", tmp_path / "nao-existe")
        assert sequencia.proximo() == 1


class TestManifestoSemBruto:
    def test_ida_e_volta_so_com_o_formatado(self, tmp_path):
        formatado = tmp_path / "0089_ACHE_2026-08.xlsx"
        item = ItemDaRodada("ACHE", "mensal", "01/08/2026 a 31/08/2026", "2026-08", None, formatado)
        caminho = tmp_path / "ultima-rodada.json"

        gravar(caminho, [item])
        lidos = ler(caminho)

        assert lidos == [item]
        assert lidos[0].anexo == formatado

    def test_bruto_e_o_anexo_quando_a_formatacao_falhou(self, tmp_path):
        bruto = tmp_path / "0089_ACHE_2026-08.xls"
        item = ItemDaRodada("ACHE", "mensal", "01/08/2026 a 31/08/2026", "2026-08", bruto)
        assert item.anexo == bruto

    def test_item_sem_arquivo_nenhum_e_recusado(self):
        with pytest.raises(ValueError):
            ItemDaRodada("ACHE", "mensal", "", "2026-08", None, None)
