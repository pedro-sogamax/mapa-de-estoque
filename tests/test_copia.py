"""Testes da copia temporaria: quem fica em copia no primeiro envio real e depois dele.

O que importa: a copia temporaria vale ate a data, inclusive, e no dia seguinte volta
sozinha a do cadastro; e a trava de teste continua mandando em tudo.
"""

from __future__ import annotations

from datetime import date

from src.config import Contatos
from src.disparo.__main__ import _destino
from tests.test_revisao import _cfg

SEGUNDA = date(2026, 10, 26)
CADASTRO = ("comprador@x.com",)
CONTATOS = Contatos(emails=("industria@y.com",), copia=CADASTRO, canais=("email",))


def test_sem_copia_temporaria_vale_o_cadastro(tmp_path):
    assert _cfg(tmp_path).copia_do_dia(CADASTRO, SEGUNDA) == CADASTRO


def test_copia_temporaria_vale_ate_a_data_inclusive(tmp_path):
    cfg = _cfg(tmp_path, copia_temporaria=("pedro@x.com",), copia_temporaria_ate=SEGUNDA)
    assert cfg.copia_do_dia(CADASTRO, date(2026, 10, 23)) == ("pedro@x.com",)
    assert cfg.copia_do_dia(CADASTRO, SEGUNDA) == ("pedro@x.com",)


def test_no_dia_seguinte_volta_o_cadastro(tmp_path):
    cfg = _cfg(tmp_path, copia_temporaria=("pedro@x.com",), copia_temporaria_ate=SEGUNDA)
    assert cfg.copia_do_dia(CADASTRO, date(2026, 10, 27)) == CADASTRO


def test_destino_usa_a_copia_do_dia(tmp_path):
    cfg = _cfg(tmp_path, copia_temporaria=("pedro@x.com",), copia_temporaria_ate=date.today())
    destino = _destino("ACHE", CONTATOS, cfg)
    assert destino.emails == ("industria@y.com",)
    assert destino.copia == ("pedro@x.com",)


def test_trava_de_teste_suprime_inclusive_a_copia_temporaria(tmp_path):
    cfg = _cfg(
        tmp_path,
        destinatario_teste=("teste@x.com",),
        copia_temporaria=("pedro@x.com",),
        copia_temporaria_ate=date.today(),
    )
    destino = _destino("ACHE", CONTATOS, cfg)
    assert destino.emails == ("teste@x.com",)
    assert destino.copia == ()
