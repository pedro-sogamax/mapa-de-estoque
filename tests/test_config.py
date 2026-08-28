"""Testes de src/config.py — a validacao do cadastro de fabricantes.

Este e o arquivo que o comprador vai passar a editar. Cada regra aqui existe para pegar,
no carregamento, um erro que so apareceria na hora do envio — ou que nao apareceria nunca,
como um relatorio gerado para o fabricante errado.

Todos os testes escrevem um YAML temporario; nenhum toca o fabricantes.yaml de producao.
"""

from __future__ import annotations

import textwrap

import pytest

from src.config import (
    ConfiguracaoInvalida,
    Contatos,
    carregar_fabricantes,
    carregar_fabricantes_com_problemas,
)

MINIMO = """
fabricantes:
  - nome: ACHE
    codigo: 106975
"""


def escrever(tmp_path, conteudo: str):
    arquivo = tmp_path / "fabricantes.yaml"
    arquivo.write_text(textwrap.dedent(conteudo), encoding="utf-8")
    return arquivo


def carregar(tmp_path, conteudo: str):
    return carregar_fabricantes(escrever(tmp_path, conteudo))


class TestLeituraBasica:
    def test_fabricante_minimo(self, tmp_path):
        (f,) = carregar(tmp_path, MINIMO)
        assert f.nome == "ACHE"
        assert f.codigos == ("106975",)
        assert f.mensal is True
        assert f.dias_semana == ()
        assert f.janela_semanal == "acumulado_mes"
        assert f.ativo is True
        assert f.comprador is None

    def test_codigo_numerico_vira_texto(self, tmp_path):
        """O YAML le 13963 como int, mas a busca no Geweb e textual."""
        (f,) = carregar(tmp_path, MINIMO)
        assert f.codigos == ("106975",)
        assert all(isinstance(c, str) for c in f.codigos)

    def test_varios_codigos_viram_um_relatorio_so(self, tmp_path):
        (f,) = carregar(
            tmp_path,
            """
            fabricantes:
              - nome: ACHE
                codigos: [106975, 106976]
            """,
        )
        assert f.codigos == ("106975", "106976")
        assert f.resumo_codigos == "106975, 106976"

    def test_inativo_e_filtrado(self, tmp_path):
        nomes = [
            f.nome
            for f in carregar(
                tmp_path,
                """
                fabricantes:
                  - nome: ATIVO
                    codigo: 1
                  - nome: DESLIGADO
                    codigo: 2
                    ativo: false
                """,
            )
        ]
        assert nomes == ["ATIVO"]

    def test_arquivo_inexistente(self, tmp_path):
        with pytest.raises(ConfiguracaoInvalida, match="nao encontrado"):
            carregar_fabricantes(tmp_path / "nao-existe.yaml")

    def test_lista_vazia(self, tmp_path):
        with pytest.raises(ConfiguracaoInvalida):
            carregar(tmp_path, "fabricantes: []")

    def test_nenhum_ativo(self, tmp_path):
        with pytest.raises(ConfiguracaoInvalida, match="Nenhum fabricante ativo"):
            carregar(
                tmp_path,
                """
                fabricantes:
                  - nome: ACHE
                    codigo: 1
                    ativo: false
                """,
            )


class TestCamposObrigatorios:
    def test_sem_nome(self, tmp_path):
        with pytest.raises(ConfiguracaoInvalida, match="nome"):
            carregar(tmp_path, "fabricantes:\n  - codigo: 1\n")

    def test_sem_codigo(self, tmp_path):
        with pytest.raises(ConfiguracaoInvalida, match="codigo"):
            carregar(tmp_path, "fabricantes:\n  - nome: ACHE\n")

    def test_campo_legado_periodicidade_explica_a_migracao(self, tmp_path):
        with pytest.raises(ConfiguracaoInvalida, match="periodicidade"):
            carregar(
                tmp_path,
                """
                fabricantes:
                  - nome: ACHE
                    codigo: 1
                    periodicidade: mensal
                """,
            )


class TestDiasDaSemana:
    def test_acento_e_sufixo_da_planilha_sao_normalizados(self, tmp_path):
        (f,) = carregar(
            tmp_path,
            """
            fabricantes:
              - nome: MARJAN
                codigo: 1
                dias_semana: [TERÇA-FEIRA, "quarta"]
            """,
        )
        assert f.dias_semana == ("terca", "quarta")

    def test_dia_repetido_nao_gera_relatorio_em_duplicata(self, tmp_path):
        (f,) = carregar(
            tmp_path,
            """
            fabricantes:
              - nome: MARJAN
                codigo: 1
                dias_semana: [segunda, SEGUNDA-FEIRA]
            """,
        )
        assert f.dias_semana == ("segunda",)

    def test_ordena_pelo_dia_da_semana_nao_pela_ordem_digitada(self, tmp_path):
        (f,) = carregar(
            tmp_path,
            """
            fabricantes:
              - nome: MARJAN
                codigo: 1
                dias_semana: [sexta, segunda, quarta]
            """,
        )
        assert f.dias_semana == ("segunda", "quarta", "sexta")

    def test_dia_invalido(self, tmp_path):
        with pytest.raises(ConfiguracaoInvalida, match="sabado"):
            carregar(
                tmp_path,
                """
                fabricantes:
                  - nome: MARJAN
                    codigo: 1
                    dias_semana: [sabado]
                """,
            )

    def test_sem_mensal_e_sem_dias_nao_teria_envio_nenhum(self, tmp_path):
        with pytest.raises(ConfiguracaoInvalida, match="nenhum envio"):
            carregar(
                tmp_path,
                """
                fabricantes:
                  - nome: MARJAN
                    codigo: 1
                    mensal: false
                """,
            )

    def test_janela_semanal_invalida(self, tmp_path):
        with pytest.raises(ConfiguracaoInvalida, match="janela_semanal"):
            carregar(
                tmp_path,
                """
                fabricantes:
                  - nome: MARJAN
                    codigo: 1
                    janela_semanal: quinzenal
                """,
            )


class TestContatos:
    def test_email_escalar_ou_lista(self, tmp_path):
        (f,) = carregar(
            tmp_path,
            """
            fabricantes:
              - nome: ACHE
                codigo: 1
                contatos:
                  emails: um@lab.com.br
                  copia: [a@sogamax.com.br, b@sogamax.com.br]
            """,
        )
        assert f.contatos.emails == ("um@lab.com.br",)
        assert f.contatos.copia == ("a@sogamax.com.br", "b@sogamax.com.br")

    @pytest.mark.parametrize("ruim", ["semarroba.com.br", "@lab.com.br", "fulano@"])
    def test_email_invalido(self, tmp_path, ruim):
        with pytest.raises(ConfiguracaoInvalida, match="e-mail invalido"):
            carregar(
                tmp_path,
                f"""
                fabricantes:
                  - nome: ACHE
                    codigo: 1
                    contatos:
                      emails: ["{ruim}"]
                """,
            )

    def test_email_invalido_na_copia_tambem_e_pego(self, tmp_path):
        with pytest.raises(ConfiguracaoInvalida, match="e-mail invalido"):
            carregar(
                tmp_path,
                """
                fabricantes:
                  - nome: ACHE
                    codigo: 1
                    contatos:
                      emails: [ok@lab.com.br]
                      copia: [quebrado]
                """,
            )

    @pytest.mark.parametrize("ruim", ["11999999999", "+55 11 99999-9999", "5511999999999"])
    def test_telefone_fora_do_padrao_internacional(self, tmp_path, ruim):
        """O link do WhatsApp so funciona em E.164 — o erro so apareceria ao clicar."""
        with pytest.raises(ConfiguracaoInvalida, match="padrao internacional"):
            carregar(
                tmp_path,
                f"""
                fabricantes:
                  - nome: ACHE
                    codigo: 1
                    contatos:
                      whatsapp: ["{ruim}"]
                """,
            )

    def test_telefone_valido(self, tmp_path):
        (f,) = carregar(
            tmp_path,
            """
            fabricantes:
              - nome: ACHE
                codigo: 1
                contatos:
                  whatsapp: ["+5511999999999"]
                  canais: [whatsapp]
            """,
        )
        assert f.contatos.whatsapp == ("+5511999999999",)

    def test_canal_desconhecido(self, tmp_path):
        with pytest.raises(ConfiguracaoInvalida, match="canal"):
            carregar(
                tmp_path,
                """
                fabricantes:
                  - nome: ACHE
                    codigo: 1
                    contatos:
                      canais: [telegram]
                """,
            )

    def test_canal_padrao_e_email(self, tmp_path):
        (f,) = carregar(tmp_path, MINIMO)
        assert f.contatos.canais == ("email",)

    def test_sem_contato_o_fabricante_continua_valido(self, tmp_path):
        """Falta de destinatario e pendencia de cadastro, nao erro que trave a rodada:
        o mapa e extraido normalmente e o disparo apenas pula com aviso."""
        (f,) = carregar(tmp_path, MINIMO)
        assert f.contatos.vazio is True


class TestRecebePor:
    def test_precisa_do_canal_e_do_destino(self):
        c = Contatos(emails=("a@lab.com",), canais=("email",))
        assert c.recebe_por("email") is True
        assert c.recebe_por("whatsapp") is False

    def test_canal_marcado_sem_destino_nao_recebe(self):
        c = Contatos(emails=(), canais=("email",))
        assert c.recebe_por("email") is False

    def test_destino_sem_o_canal_marcado_nao_recebe(self):
        c = Contatos(whatsapp=("+5511999999999",), canais=("email",))
        assert c.recebe_por("whatsapp") is False


class TestComprador:
    def test_ausente_vira_none_para_cair_no_padrao_do_env(self, tmp_path):
        (f,) = carregar(tmp_path, MINIMO)
        assert f.comprador is None

    def test_bloco_completo(self, tmp_path):
        (f,) = carregar(
            tmp_path,
            """
            fabricantes:
              - nome: ACHE
                codigo: 1
                comprador:
                  nome: YURI TOSO
                  responder_para: yuritoso@sogamax.com.br
                  cargo: Compras
            """,
        )
        assert f.comprador.nome == "YURI TOSO"
        assert f.comprador.cargo == "Compras"

    def test_sem_nome_e_erro_porque_e_quem_assina(self, tmp_path):
        with pytest.raises(ConfiguracaoInvalida, match="sem 'nome'"):
            carregar(
                tmp_path,
                """
                fabricantes:
                  - nome: ACHE
                    codigo: 1
                    comprador:
                      responder_para: a@sogamax.com.br
                """,
            )

    def test_responder_para_aceita_varios_enderecos(self, tmp_path):
        (f,) = carregar(
            tmp_path,
            """
            fabricantes:
              - nome: ACHE
                codigo: 1
                comprador:
                  nome: YURI e MARIA
                  responder_para: yuri@sogamax.com.br, maria@sogamax.com.br
            """,
        )
        assert "maria@sogamax.com.br" in f.comprador.responder_para

    def test_responder_para_invalido(self, tmp_path):
        with pytest.raises(ConfiguracaoInvalida, match="responder_para"):
            carregar(
                tmp_path,
                """
                fabricantes:
                  - nome: ACHE
                    codigo: 1
                    comprador:
                      nome: YURI
                      responder_para: quebrado
                """,
            )


class TestResumoEnvio:
    def test_mensal(self, tmp_path):
        (f,) = carregar(tmp_path, MINIMO)
        assert f.resumo_envio == "mensal"

    def test_mensal_e_semanal(self, tmp_path):
        (f,) = carregar(
            tmp_path,
            """
            fabricantes:
              - nome: MARJAN
                codigo: 1
                dias_semana: [segunda, quarta]
            """,
        )
        assert f.resumo_envio == "mensal semanal(segunda+quarta)"


class TestUmErroNaoDerrubaARodada:
    """O comprador vai editar este arquivo. Um erro dele nao pode custar os 23 laboratorios.

    Antes, `carregar_fabricantes` abortava no primeiro erro e a rodada das 07:00 nao gerava
    nada — em silencio, porque nao ha alerta ativo. Agora o fabricante com problema fica de
    fora e os demais seguem.
    """

    DOIS = """
    fabricantes:
      - nome: BOM
        codigo: 1
        contatos:
          emails: [contato@lab.com.br]
      - nome: RUIM
        codigo: 2
        contatos:
          emails: [sem-arroba]
    """

    def test_o_valido_sobrevive_ao_invalido(self, tmp_path):
        assert [f.nome for f in carregar(tmp_path, self.DOIS)] == ["BOM"]

    def test_o_problema_e_reportado_e_nomeia_o_fabricante(self, tmp_path):
        fabricantes, problemas = carregar_fabricantes_com_problemas(
            escrever(tmp_path, self.DOIS)
        )
        assert [f.nome for f in fabricantes] == ["BOM"]
        assert len(problemas) == 1
        assert "RUIM" in problemas[0]

    def test_cadastro_sem_erro_nao_reporta_problema(self, tmp_path):
        _, problemas = carregar_fabricantes_com_problemas(escrever(tmp_path, MINIMO))
        assert problemas == []

    def test_erro_e_registrado_no_log_como_error(self, tmp_path, caplog):
        """Ficar de fora em silencio seria pior que abortar: precisa gritar no log."""
        with caplog.at_level("ERROR"):
            carregar(tmp_path, self.DOIS)
        assert any("RUIM" in r.getMessage() for r in caplog.records)

    def test_varios_invalidos_sao_todos_reportados(self, tmp_path):
        _, problemas = carregar_fabricantes_com_problemas(
            escrever(
                tmp_path,
                """
                fabricantes:
                  - nome: BOM
                    codigo: 1
                  - nome: SEM_CODIGO
                  - nome: DIA_RUIM
                    codigo: 3
                    dias_semana: [sabado]
                """,
            )
        )
        assert len(problemas) == 2

    def test_ainda_aborta_quando_nao_sobra_ninguem(self, tmp_path):
        """Sem nenhum fabricante nao ha rodada: a falha total e o desfecho correto,
        e a mensagem precisa carregar os problemas para nao se perderem."""
        with pytest.raises(ConfiguracaoInvalida) as erro:
            carregar(
                tmp_path,
                """
                fabricantes:
                  - nome: RUIM
                    codigo: 1
                    contatos:
                      emails: [sem-arroba]
                """,
            )
        assert "sem-arroba" in str(erro.value)

    def test_yaml_malformado_aborta_com_mensagem_util(self, tmp_path):
        """Um YAML quebrado nao tem entrada aproveitavel — nao da para isolar o estrago.
        TAB no lugar de espacos e o erro mais comum de quem edita YAML a mao."""
        arquivo = tmp_path / "fabricantes.yaml"
        arquivo.write_text("fabricantes:\n\t- nome: ACHE\n", encoding="utf-8")
        with pytest.raises(ConfiguracaoInvalida, match="indentacao"):
            carregar_fabricantes(arquivo)


class TestCadastroReal:
    def test_o_fabricantes_yaml_de_producao_carrega(self):
        """Guarda-corpo: qualquer edicao no cadastro real precisa continuar valida."""
        fabricantes = carregar_fabricantes()
        assert fabricantes, "nenhum fabricante ativo no cadastro de producao"
        for f in fabricantes:
            assert f.codigos, f"{f.nome} sem codigo do Geweb"
            assert f.mensal or f.dias_semana, f"{f.nome} nao tem envio nenhum"
