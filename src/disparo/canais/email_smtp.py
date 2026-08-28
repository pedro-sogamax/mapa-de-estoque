"""Canal de e-mail por SMTP autenticado.

O dominio sogamax.com.br e hospedado na Locaweb, que oferece SMTP autenticado padrao
(smtp.locaweb.com.br, 587 com STARTTLS ou 465 com SSL). Nao precisa de aplicacao registrada,
consentimento de administrador nem servico de terceiro — smtplib da biblioteca padrao basta.

Uma conexao serve a leva inteira: abrir e fechar por mensagem e mais lento e da mais chance
de o servidor cortar por excesso de conexoes.
"""

from __future__ import annotations

import logging
import smtplib
import time
from email.message import EmailMessage
from pathlib import Path

from src.config import Config
from src.disparo.canais.base import Destino, Envio, FalhaFatal, FalhaNoEnvio, Mensagem
from src.disparo.eml import montar_mensagem

log = logging.getLogger(__name__)

# Espera antes de cada retentativa. Crescente: se o servidor esta ocupado, insistir no mesmo
# ritmo so piora.
_ESPERAS = (5, 15)


class CanalEmail:
    """Envia por SMTP. Mantem a conexao aberta enquanto estiver em uso como contexto."""

    nome = "email"

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._sessao: smtplib.SMTP | None = None

    def disponivel(self) -> str | None:
        if not self.cfg.smtp_host:
            return "SMTP_HOST nao configurado no .env"
        if not self.cfg.smtp_usuario or not self.cfg.smtp_senha:
            return "SMTP_USUARIO/SMTP_SENHA nao configurados no .env"
        return None

    def __enter__(self) -> CanalEmail:
        self._sessao = self._conectar()
        return self

    def __exit__(self, *_) -> None:
        if self._sessao is not None:
            try:
                self._sessao.quit()
            except smtplib.SMTPException:  # ja caiu; nao ha o que salvar
                pass
            self._sessao = None

    def _conectar(self) -> smtplib.SMTP:
        cfg = self.cfg
        try:
            if cfg.smtp_seguranca == "ssl":
                sessao: smtplib.SMTP = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_porta, timeout=30)
            else:
                sessao = smtplib.SMTP(cfg.smtp_host, cfg.smtp_porta, timeout=30)
                sessao.starttls()
            sessao.login(cfg.smtp_usuario, cfg.smtp_senha)
        except smtplib.SMTPAuthenticationError as erro:
            # Fatal de proposito: insistir com credencial recusada e o caminho mais curto
            # para o provedor bloquear a conta.
            raise FalhaFatal(
                f"O servidor recusou as credenciais de {cfg.smtp_usuario}. Confira SMTP_USUARIO "
                f"e SMTP_SENHA no .env. Resposta do servidor: {erro.smtp_code} {erro.smtp_error!r}"
            ) from erro
        except (OSError, smtplib.SMTPException) as erro:
            raise FalhaNoEnvio(
                f"Nao consegui conectar em {cfg.smtp_host}:{cfg.smtp_porta} "
                f"({cfg.smtp_seguranca}): {erro}"
            ) from erro

        log.debug("Conectado em %s:%s como %s", cfg.smtp_host, cfg.smtp_porta, cfg.smtp_usuario)

        # A Locaweb exige que quem assina a mensagem seja a mesma conta que autenticou; com
        # REMETENTE diferente ela devolve "503 5.0.3 Client host rejected" em cada mensagem.
        if cfg.remetente and cfg.remetente.casefold() != cfg.smtp_usuario.casefold():
            log.warning(
                "REMETENTE (%s) e diferente da conta autenticada (%s). Varios provedores, a "
                "Locaweb entre eles, recusam isso com erro 503. Se as mensagens falharem, "
                "esvazie REMETENTE e use RESPONDER_PARA para direcionar as respostas.",
                cfg.remetente,
                cfg.smtp_usuario,
            )
        return sessao

    def _remetente(self) -> str:
        """Quem assina tecnicamente. Sem REMETENTE, a propria caixa autenticada."""
        return self.cfg.remetente or self.cfg.smtp_usuario

    def _enviar_com_retentativa(self, msg: EmailMessage, fabricante: str) -> dict:
        """Tenta entregar, repetindo so o que vale a pena repetir.

        Erro 4xx do SMTP e temporario por definicao (caixa cheia, servidor ocupado, greylist):
        esperar e tentar de novo resolve a maioria. Erro 5xx e permanente — repetir so gasta
        reputacao. Queda de conexao exige reabrir a sessao antes, senao as tentativas
        seguintes falhariam pelo mesmo motivo.
        """
        ultimo_erro = ""
        for tentativa in range(1, max(1, self.cfg.max_tentativas) + 1):
            # A ordem dos except importa e nao e obvia: smtplib.SMTPException herda de
            # OSError, e SMTPConnectError/SMTPAuthenticationError herdam de
            # SMTPResponseException. Capturar OSError cedo demais faria TODO erro virar
            # "conexao caiu" — inclusive o 5xx permanente, que seria repetido 3 vezes.
            try:
                return self._sessao.send_message(msg)
            except smtplib.SMTPAuthenticationError as erro:
                raise FalhaFatal(f"Credenciais recusadas durante o envio: {erro}") from erro
            except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError) as erro:
                ultimo_erro = f"conexao caiu ({erro})"
                temporario = True
                self._reabrir()
            except smtplib.SMTPResponseException as erro:
                ultimo_erro = f"{erro.smtp_code} {erro.smtp_error!r}"
                # 4xx e transitorio por definicao (caixa cheia, servidor ocupado, greylist);
                # 5xx e definitivo, e repetir so gasta reputacao.
                temporario = 400 <= erro.smtp_code < 500
            except smtplib.SMTPRecipientsRefused as erro:
                ultimo_erro = f"destinatarios recusados: {erro.recipients}"
                temporario = False
            except smtplib.SMTPException as erro:
                ultimo_erro = str(erro)
                temporario = False
            except OSError as erro:  # timeout, conexao resetada: rede, nao protocolo
                ultimo_erro = f"falha de rede ({erro})"
                temporario = True
                self._reabrir()

            if not temporario:
                raise FalhaNoEnvio(f"O servidor recusou a mensagem: {ultimo_erro}")
            if tentativa >= self.cfg.max_tentativas:
                break

            espera = _ESPERAS[min(tentativa - 1, len(_ESPERAS) - 1)]
            log.warning(
                "    %s: %s — tentando de novo em %ds (%d de %d)",
                fabricante,
                ultimo_erro,
                espera,
                tentativa + 1,
                self.cfg.max_tentativas,
            )
            time.sleep(espera)

        raise FalhaNoEnvio(
            f"Falha temporaria persistiu em {self.cfg.max_tentativas} tentativas: {ultimo_erro}"
        )

    def _reabrir(self) -> None:
        """Refaz a conexao depois de uma queda. Silencia falha no fechamento do que ja caiu."""
        if self._sessao is not None:
            try:
                self._sessao.quit()
            except (smtplib.SMTPException, OSError):
                pass
        self._sessao = self._conectar()

    def enviar(self, destino: Destino, mensagem: Mensagem, anexo: Path | None) -> Envio:
        if self._sessao is None:
            raise FalhaNoEnvio("Canal de e-mail usado sem conexao aberta (falta o 'with').")
        if not destino.emails:
            raise FalhaNoEnvio(f"{destino.fabricante} nao tem e-mail de destino.")

        msg: EmailMessage = montar_mensagem(
            para=list(destino.emails),
            copia=list(destino.copia),
            assunto=mensagem.assunto,
            corpo=mensagem.corpo,
            anexo=anexo,
            remetente=self._remetente(),
            responder_para=destino.responder_para or self.cfg.responder_para,
            rascunho=False,  # X-Unsent so faz sentido no arquivo .eml
            corpo_html=mensagem.corpo_html,
            assinatura_dir=self.cfg.templates_dir / "assinatura",
        )

        recusados = self._enviar_com_retentativa(msg, destino.fabricante)
        if recusados:
            raise FalhaNoEnvio(f"Enderecos recusados pelo servidor: {', '.join(recusados)}")

        aceitos = tuple(destino.emails) + tuple(destino.copia)
        return Envio(canal=self.nome, destinatarios=aceitos, identificadores=(msg["Message-ID"],))
