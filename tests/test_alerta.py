"""Testes do aviso de falha da rodada.

O alerta e a unica coisa que transforma uma falha silenciosa as 07:00 em algo que alguem
fica sabendo. Duas propriedades importam mais que o formato: ele NAO dispara quando a
rodada foi limpa (senao vira ruido e para de ser lido), e ele NUNCA derruba a rodada.
"""

from __future__ import annotations

import pytest

from src.alerta import MAX_LINHAS, _montar_corpo
from src.main import Resultado, _linhas_do_alerta


def ok(nome: str, aviso: str | None = None) -> Resultado:
    return Resultado(nome, "mensal", "01/07 a 31/07", rotulo="2026-07", aviso=aviso)


def falhou(nome: str, erro: str = "timeout no Geweb") -> Resultado:
    return Resultado(nome, "mensal", "01/07 a 31/07", rotulo="2026-07", erro=erro)


class TestQuandoNaoAlerta:
    def test_rodada_limpa_nao_gera_alerta(self):
        """Um e-mail diario de "tudo certo" treina as pessoas a ignorar o alerta."""
        assert _linhas_do_alerta([ok("ACHE"), ok("MARJAN")], []) == []

    def test_sem_nada_a_relatar(self):
        assert _linhas_do_alerta([], []) == []

    def test_envio_com_codigo_zero_nao_e_falha(self):
        assert _linhas_do_alerta([ok("ACHE")], [], codigo_envio=0) == []


class TestConteudo:
    def test_nomeia_o_fabricante_que_falhou(self):
        linhas = _linhas_do_alerta([ok("ACHE"), falhou("MARJAN")], [])
        texto = "\n".join(linhas)
        assert "MARJAN" in texto
        assert "1 de 2" in texto
        assert "timeout no Geweb" in texto

    def test_relata_o_que_saiu_so_no_formato_bruto(self):
        """Nao e falha de extracao, mas alguem precisa formatar a mao antes de enviar."""
        linhas = _linhas_do_alerta([ok("ACHE", aviso="formatacao falhou: xyz")], [])
        assert any("formato bruto" in linha for linha in linhas)

    def test_relata_o_fabricante_que_ficou_de_fora_por_cadastro(self):
        """O caso novo: o cadastro invalido nao derruba mais a rodada, entao o alerta e a
        unica coisa que conta que aquele laboratorio nao recebeu nada."""
        linhas = _linhas_do_alerta([ok("ACHE")], ["Fabricante 'MARJAN': e-mail invalido"])
        texto = "\n".join(linhas)
        assert "MARJAN" in texto and "DE FORA" in texto

    def test_relata_falha_de_envio(self):
        linhas = _linhas_do_alerta([ok("ACHE")], [], codigo_envio=3)
        texto = "\n".join(linhas)
        assert "codigo 3" in texto and "disparo" in texto

    def test_rodada_interrompida_antes_de_gerar_qualquer_coisa(self):
        linhas = _linhas_do_alerta([], [], erro_geral="login recusado pelo Geweb")
        texto = "\n".join(linhas)
        assert "NENHUM relatorio" in texto and "login recusado" in texto

    def test_acumula_varios_problemas_na_mesma_mensagem(self):
        linhas = _linhas_do_alerta(
            [ok("ACHE"), falhou("MARJAN"), ok("EMS", aviso="formatacao falhou")],
            ["Fabricante 'ASPEN': e-mail invalido"],
            codigo_envio=3,
        )
        texto = "\n".join(linhas)
        for esperado in ("MARJAN", "EMS", "ASPEN", "codigo 3"):
            assert esperado in texto


class TestCorpo:
    def test_traz_rodape_com_onde_olhar(self):
        corpo = _montar_corpo(["algo falhou"])
        assert "logs/execucao.log" in corpo

    def test_trunca_para_caber_numa_tela(self):
        """Se a rodada quebrou em 24 laboratorios, o e-mail precisa dizer o essencial;
        o resto esta no log."""
        corpo = _montar_corpo([f"linha {i}" for i in range(MAX_LINHAS + 20)])
        assert "e mais 20 linha(s)" in corpo
        assert f"linha {MAX_LINHAS + 10}" not in corpo


class TestNuncaDerrubaARodada:
    def test_sem_destinatario_devolve_false_em_vez_de_levantar(self, monkeypatch):
        from src import alerta

        class CfgFalso:
            alerta_destinatarios = ()
            email_configurado = True

        assert alerta.enviar(CfgFalso(), "assunto", ["linha"]) is False

    def test_smtp_nao_configurado_devolve_false(self):
        from src import alerta

        class CfgFalso:
            alerta_destinatarios = ("a@b.com",)
            email_configurado = False

        assert alerta.enviar(CfgFalso(), "assunto", ["linha"]) is False

    def test_falha_no_envio_devolve_false_em_vez_de_propagar(self, monkeypatch):
        from src import alerta
        from src.disparo.canais.base import FalhaNoEnvio

        class CanalQuebrado:
            def __init__(self, cfg):
                pass

            def __enter__(self):
                raise FalhaNoEnvio("servidor fora do ar")

            def __exit__(self, *_):
                return False

        class CfgFalso:
            alerta_destinatarios = ("a@b.com",)
            email_configurado = True

        monkeypatch.setattr(alerta, "CanalEmail", CanalQuebrado)
        assert alerta.enviar(CfgFalso(), "assunto", ["linha"]) is False


@pytest.mark.parametrize("codigo", [None, 0])
def test_codigo_de_envio_ausente_ou_zero_e_tratado_igual(codigo):
    assert _linhas_do_alerta([ok("ACHE")], [], codigo_envio=codigo) == []
