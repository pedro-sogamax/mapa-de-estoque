"""Envia o mapa de estoque as industrias, por e-mail e/ou WhatsApp.

Uso:
    python -m src.disparo --dry-run             # mostra o que enviaria, e sai
    python -m src.disparo                       # mostra, pergunta e envia
    python -m src.disparo --sim                 # envia sem perguntar
    python -m src.disparo --periodo 2026-07     # uma leva antiga
    python -m src.disparo --fabricante MARJAN   # so um laboratorio
    python -m src.disparo --canal email         # so um canal
    python -m src.disparo --refazer             # reenvia o que ja foi enviado
    python -m src.disparo --rascunho            # nao envia: grava .eml e a pagina wa.me

Este comando ENVIA de verdade. Rodado assim, quem dispara e uma pessoa, depois da extracao,
e duas travas seguram o dedo pesado: a confirmacao (digitar SIM) e o par
DESTINATARIO_TESTE/TELEFONE_TESTE, que redireciona tudo para voce.

A tarefa agendada chama a versao automatica: `src.main --enviar` executa este mesmo comando
com --canal email --sim ao fim da extracao. So o e-mail — o WhatsApp continua exclusivo daqui.

Codigos de saida: 0 tudo entregue, 2 erro de configuracao, 3 algum envio falhou.
"""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src import historico
from src.config import (
    Comprador,
    Config,
    ConfiguracaoInvalida,
    Contatos,
    Fabricante,
    carregar_config,
    carregar_fabricantes,
    nome_do_comprador,
)
from src.disparo.canais.base import Canal, Destino, Envio, FalhaFatal, FalhaNoEnvio, Mensagem
from src.disparo.canais.email_smtp import CanalEmail
from src.disparo.canais.rascunho import CanalRascunhoEmail, CanalRascunhoWhatsApp
from src.disparo.canais.whatsapp_api import CanalWhatsApp
from src.disparo.limites import CotaDeEnvio, Disjuntor, LimiteAtingido, conferir_teto
from src.disparo.mensagem import TemplateInvalido, para_email, para_whatsapp
from src.disparo.registro import RegistroDeEnvios, RegistroIlegivel
from src.disparo.selecao import da_ultima_rodada, do_periodo, periodos_disponiveis
from src.log import configurar as configurar_log
from src.rodada import ItemDaRodada

log = logging.getLogger("disparo")

CODIGO_FALHA_DE_ENVIO = 3


@dataclass
class Passo:
    """Uma entrega a fazer: um laboratorio, por um canal."""

    item: ItemDaRodada
    canal: str
    destino: Destino
    mensagem: Mensagem
    anexo: Path | None
    com_anexo: bool
    ja_enviado_em: str | None = None

    @property
    def alvo(self) -> str:
        endereços = self.destino.emails if self.canal == "email" else self.destino.telefones
        return ", ".join(endereços)


def _configurar_log(nivel: int = logging.INFO) -> None:
    configurar_log("disparo.log", nivel)


def _destino(
    fabricante: str, contatos: Contatos, cfg: Config, comprador: Comprador | None = None
) -> Destino:
    """Para quem vai — respeitando as travas de teste, canal a canal.

    As duas travas sao independentes de proposito: quem preenche so DESTINATARIO_TESTE
    protege o e-mail e mandaria WhatsApp de verdade. Por isso o resumo avisa qual esta ligada.

    O `responder_para` sai do comprador deste laboratorio; sem ele, do .env. A trava de teste
    NAO o sobrepoe: ela protege quem RECEBE o mapa, e mandar a resposta para o comprador certo
    e o comportamento correto mesmo em homologacao — e o que se quer conferir.
    """
    emails = cfg.destinatario_teste or contatos.emails
    copia = () if cfg.destinatario_teste else contatos.copia
    telefones = (cfg.telefone_teste,) if cfg.telefone_teste else contatos.whatsapp
    responder_para = comprador.responder_para if comprador else ""
    return Destino(
        fabricante=fabricante,
        emails=emails,
        copia=copia,
        telefones=telefones,
        responder_para=responder_para or cfg.responder_para,
    )


def montar_plano(
    cfg: Config,
    itens: list[ItemDaRodada],
    fabricantes_por_nome: dict[str, Fabricante],
    canais: tuple[str, ...],
    registro: RegistroDeEnvios,
    refazer: bool,
) -> tuple[list[Passo], list[str]]:
    """Decide o que sera enviado. Nao envia nada — so monta a lista."""
    passos: list[Passo] = []
    pendencias: list[str] = []

    for item in itens:
        fabricante = fabricantes_por_nome.get(item.fabricante)
        if fabricante is None:
            pendencias.append(f"{item.fabricante}: nao esta no fabricantes.yaml (ou esta inativo)")
            continue
        contatos = fabricante.contatos
        # Sem bloco proprio, quem assina e recebe a resposta e o comprador do .env.
        comprador = fabricante.comprador
        quem_compra = comprador.nome if comprador else cfg.comprador
        # Dados da assinatura: o do laboratorio primeiro, o do .env como padrao. Cada campo
        # cai sozinho, para um bloco `comprador` que so preencha o nome nao apagar o resto.
        cargo = (comprador.cargo if comprador else "") or cfg.comprador_cargo
        telefones = (comprador.telefones if comprador else "") or cfg.comprador_telefones
        email_comprador = (comprador.responder_para if comprador else "") or cfg.responder_para
        if contatos.vazio:
            pendencias.append(f"{item.fabricante}: sem e-mail nem WhatsApp cadastrado")
            continue

        destino = _destino(item.fabricante, contatos, cfg, fabricante.comprador)
        anexo = item.anexo if item.anexo.exists() else None
        if anexo is None:
            pendencias.append(f"{item.fabricante}: arquivo nao encontrado em {item.anexo}")
            continue

        # Um mapa formatado tem menos de 100 KB. Perto do limite indica arquivo errado —
        # e servidor recusa anexo grande depois de ja ter recebido a mensagem inteira.
        tamanho_mb = anexo.stat().st_size / (1024 * 1024)
        if tamanho_mb > cfg.max_anexo_mb:
            pendencias.append(
                f"{item.fabricante}: anexo de {tamanho_mb:.1f} MB acima do limite de "
                f"{cfg.max_anexo_mb} MB ({anexo.name})"
            )
            continue

        for canal in canais:
            if not contatos.recebe_por(canal):
                continue
            ja = registro.enviado_em(item.fabricante, item.rotulo, canal)
            if ja and not refazer:
                passos.append(
                    Passo(item, canal, destino, Mensagem("", ""), anexo, False, ja_enviado_em=ja)
                )
                continue

            if canal == "email":
                msg = para_email(
                    cfg.templates_dir,
                    item,
                    quem_compra,
                    cargo=cargo,
                    telefones=telefones,
                    email_comprador=email_comprador,
                )
                mensagem = Mensagem(
                    assunto=msg.assunto, corpo=msg.corpo, corpo_html=msg.corpo_html
                )
                com_anexo = True
            else:
                texto = para_whatsapp(
                    cfg.templates_dir, item, quem_compra, ", ".join(destino.emails)
                )
                mensagem = Mensagem(assunto="", corpo=texto)
                com_anexo = contatos.whatsapp_anexo

            passos.append(Passo(item, canal, destino, mensagem, anexo, com_anexo))

    return passos, pendencias


def _destinatarios_repetidos(passos: list[Passo]) -> dict[str, list[str]]:
    """Endereco de e-mail -> laboratorios que mandam para ele nesta leva, quando ha mais de um.

    Nao e erro: EUROFARMA e EUROFARMA_RX sao relatorios diferentes, de codigos diferentes do
    Geweb, e podem legitimamente ir separados para a mesma caixa. Mas quem confirma precisa
    ver que aquela pessoa vai receber duas mensagens.
    """
    por_endereco: dict[str, list[str]] = {}
    for passo in passos:
        if passo.canal != "email":
            continue
        for endereco in passo.destino.emails:
            por_endereco.setdefault(endereco, []).append(passo.item.fabricante)
    return {e: labs for e, labs in por_endereco.items() if len(labs) > 1}


def _imprimir_plano(
    cfg: Config,
    passos: list[Passo],
    pendencias: list[str],
    rotulo: str,
    cota: CotaDeEnvio | None = None,
) -> None:
    a_enviar = [p for p in passos if p.ja_enviado_em is None]
    ja_enviados = [p for p in passos if p.ja_enviado_em is not None]

    log.info("-" * 72)
    log.info("%d mensagem(ns) a enviar — periodo %s", len(a_enviar), rotulo)

    # Cada canal tem a sua trava. Dizer canal a canal quem esta protegido evita a leitura
    # perigosa de "vi MODO TESTE no topo, entao nada sai daqui" — quando so metade estava.
    usados = {p.canal for p in a_enviar}
    travas = {"email": cfg.destinatario_teste, "whatsapp": (cfg.telefone_teste,) if cfg.telefone_teste else ()}
    for canal in sorted(usados):
        if travas[canal]:
            log.info("TESTE   %-9s tudo vai para %s", canal, ", ".join(travas[canal]))
        else:
            log.info("REAL    %-9s vai para as INDUSTRIAS", canal)
    log.info("")

    for passo in a_enviar:
        extra = "  (com anexo)" if passo.canal == "whatsapp" and passo.com_anexo else ""
        log.info("  %-28s %-9s %s%s", passo.item.fabricante, passo.canal, passo.alvo, extra)

    repetidos = _destinatarios_repetidos(a_enviar)
    if repetidos:
        log.info("")
        for endereco, laboratorios in sorted(repetidos.items()):
            log.info(
                "  ATENCAO: %s recebe %d e-mails nesta leva (%s)",
                endereco,
                len(laboratorios),
                ", ".join(laboratorios),
            )

    if cota is not None and a_enviar:
        log.info("")
        for canal in sorted({p.canal for p in a_enviar}):
            pedidos = sum(1 for p in a_enviar if p.canal == canal)
            restantes = cota.restantes(canal)
            aviso = "  <- NAO CABE, a leva vai parar no meio" if pedidos > restantes else ""
            log.info(
                "  cota %-9s %d de %d usados na ultima hora; cabem mais %d, a leva pede %d%s",
                canal,
                cota.usados(canal),
                cfg.max_envios_por_hora,
                restantes,
                pedidos,
                aviso,
            )
        log.info("  teto por rodada: %d mensagens", cfg.max_envios_por_rodada)

    if ja_enviados:
        log.info("")
        log.info("Ja enviados (use --refazer para mandar de novo):")
        for passo in ja_enviados:
            log.info("  %-28s %-9s em %s", passo.item.fabricante, passo.canal, passo.ja_enviado_em[:10])

    if pendencias:
        log.info("")
        log.info("Sem cadastro de contato — %d laboratorio(s):", len(pendencias))
        for pendencia in pendencias:
            log.info("  - %s", pendencia)
        log.info("Preencha o bloco 'contatos' no fabricantes.yaml.")
    log.info("-" * 72)


def _confirmar(quantidade: int, canais_reais: set[str]) -> bool:
    """Pergunta antes de enviar, deixando claro se alguem de fora sera atingido."""
    if canais_reais:
        destino = f"— {', '.join(sorted(canais_reais))} vai para as INDUSTRIAS"
    else:
        destino = "(todos os canais em modo teste)"
    print(f"\nEnviar {quantidade} mensagem(ns) {destino}?")
    try:
        resposta = input("Digite SIM para confirmar: ").strip()
    except EOFError:  # rodando sem terminal interativo
        log.error("Sem terminal para confirmar. Use --sim se a intencao e enviar mesmo.")
        return False
    return resposta.casefold() == "sim"


def _canais_reais(cfg: Config) -> dict[str, Canal]:
    return {"email": CanalEmail(cfg), "whatsapp": CanalWhatsApp(cfg)}


def executar(
    cfg: Config,
    passos: list[Passo],
    canais: dict[str, Canal],
    registro: RegistroDeEnvios,
    registrar: bool = True,
    cota: CotaDeEnvio | None = None,
) -> tuple[list[Passo], list[tuple[Passo, str]], list[tuple[Passo, str]]]:
    """Envia, um passo por vez. Devolve (enviados, falhas, barrados por limite).

    Falha de um laboratorio nao interrompe os demais, mas falha SISTEMATICA interrompe: tres
    seguidas no mesmo canal o desligam, porque insistir com um servidor que ja recusou e o
    que faz um provedor suspender a conta.

    `registrar=False` no modo rascunho: montar um .eml nao e entregar. Registrar ali faria a
    idempotencia bloquear o envio de verdade depois — o mapa nunca chegaria a industria.
    """
    enviados: list[Passo] = []
    falhas: list[tuple[Passo, str]] = []
    barrados: list[tuple[Passo, str]] = []
    disjuntor = Disjuntor(maximo=cfg.max_falhas_seguidas)
    total = len(passos)

    for indice, passo in enumerate(passos, start=1):
        canal = canais[passo.canal]

        if disjuntor.desligado(passo.canal):
            barrados.append((passo, f"canal {passo.canal} desligado: {disjuntor.motivo(passo.canal)}"))
            continue

        if cota is not None:
            try:
                cota.conferir(passo.canal)
            except LimiteAtingido as erro:
                log.error("    COTA ATINGIDA: %s", erro)
                barrados.append((passo, str(erro)))
                # Nao adianta seguir para os proximos DESTE canal; os outros continuam.
                disjuntor.desligar(passo.canal, "cota horaria atingida")
                continue

        log.info("[%d/%d] %s por %s", indice, total, passo.item.fabricante, passo.canal)

        if isinstance(canal, CanalWhatsApp):
            canal.com_anexo = passo.com_anexo

        try:
            envio: Envio = canal.enviar(passo.destino, passo.mensagem, passo.anexo)
        except FalhaFatal:
            raise  # credencial recusada: a leva inteira para, em main()
        except FalhaNoEnvio as erro:
            log.error("    FALHOU: %s", erro)
            falhas.append((passo, str(erro)))
            disjuntor.registrar_falha(passo.canal, str(erro))
            if disjuntor.desligado(passo.canal):
                log.error(
                    "    CANAL %s DESLIGADO apos %d falhas seguidas — o resto deste canal "
                    "nao sera tentado.",
                    passo.canal.upper(),
                    cfg.max_falhas_seguidas,
                )
            continue

        disjuntor.registrar_sucesso(passo.canal)
        if registrar:
            registro.registrar(passo.item.fabricante, passo.item.rotulo, passo.canal, envio.resumo)
            if cota is not None:
                cota.registrar(passo.canal, passo.item.fabricante, envio.resumo)
        log.info("    %s -> %s", "enviado" if registrar else "montado", envio.resumo)
        enviados.append(passo)

        # Rajada de mensagens identicas e o padrao que faz provedor de WhatsApp banir numero.
        if indice < total and cfg.intervalo_envio_s > 0:
            time.sleep(cfg.intervalo_envio_s)

    return enviados, falhas, barrados


def _parsear_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="disparo",
        description="Envia o mapa as industrias por e-mail e WhatsApp.",
    )
    parser.add_argument("--periodo", help="Rotulo do periodo (ex.: 2026-07). Padrao: a ultima rodada.")
    parser.add_argument("--fabricante", help="So este laboratorio.")
    parser.add_argument(
        "--comprador",
        help="So os laboratorios destes compradores. Aceita varios, separados por virgula.",
    )
    parser.add_argument("--canal", choices=("email", "whatsapp"), help="Restringe a um canal.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que enviaria e sai.")
    parser.add_argument("--sim", action="store_true", help="Nao pergunta antes de enviar.")
    parser.add_argument("--refazer", action="store_true", help="Reenvia o que ja foi enviado.")
    parser.add_argument(
        "--rascunho",
        action="store_true",
        help="Nao envia: grava os .eml e a pagina wa.me para envio manual.",
    )
    parser.add_argument(
        "--forcar",
        action="store_true",
        help="Libera o teto de mensagens por rodada. Use so depois de conferir no --dry-run.",
    )
    parser.add_argument("--debug", action="store_true", help="Log detalhado.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parsear_argumentos(argv)
    _configurar_log(logging.DEBUG if args.debug else logging.INFO)

    try:
        cfg = carregar_config()
        fabricantes = carregar_fabricantes()
    except ConfiguracaoInvalida as erro:
        log.error("%s", erro)
        return 2

    itens = do_periodo(cfg, args.periodo) if args.periodo else da_ultima_rodada(cfg)
    if not itens:
        if args.periodo:
            log.error("Nenhum relatorio do periodo %s em %s.", args.periodo, cfg.formatado_dir)
            disponiveis = periodos_disponiveis(cfg)
            if disponiveis:
                log.info("Periodos disponiveis: %s", ", ".join(disponiveis))
            return 2
        log.info(
            "Nenhuma rodada registrada em %s. Rode a extracao primeiro, ou use --periodo.",
            cfg.rodada_path.name,
        )
        return 0

    if args.comprador:
        alvos = {p.strip().casefold() for p in args.comprador.split(",") if p.strip()}
        de_quem = {f.nome: nome_do_comprador(f, cfg) for f in fabricantes}
        conhecidos = sorted(set(de_quem.values()))
        itens = [i for i in itens if de_quem.get(i.fabricante, "").casefold() in alvos]
        if not itens:
            log.error(
                "Nenhum laboratorio de %r nesta leva. Compradores no cadastro: %s",
                args.comprador,
                ", ".join(conhecidos) or "(nenhum)",
            )
            return 2

    if args.fabricante:
        alvo = args.fabricante.strip().casefold()
        itens = [i for i in itens if i.fabricante.casefold() == alvo]
        if not itens:
            log.error("Fabricante %r nao esta nesta leva.", args.fabricante)
            return 2

    canais_pedidos = (args.canal,) if args.canal else ("email", "whatsapp")

    try:
        registro = RegistroDeEnvios(cfg.envios_path)
    except RegistroIlegivel as erro:
        log.error("%s", erro)
        return 2

    try:
        passos, pendencias = montar_plano(
            cfg, itens, {f.nome: f for f in fabricantes}, canais_pedidos, registro, args.refazer
        )
    except TemplateInvalido as erro:
        log.error("%s", erro)
        return 2

    cota = CotaDeEnvio(cfg.envios_historico_path, cfg.max_envios_por_hora)
    _imprimir_plano(cfg, passos, pendencias, itens[0].periodo, cota)
    a_enviar = [p for p in passos if p.ja_enviado_em is None]

    if args.dry_run:
        log.info("--dry-run: nada foi enviado.")
        return 0
    if not a_enviar:
        log.info("Nada a enviar.")
        return 0

    try:
        conferir_teto(len(a_enviar), cfg.max_envios_por_rodada, args.forcar)
    except LimiteAtingido as erro:
        log.error("%s", erro)
        return 2

    if args.rascunho:
        return _executar_rascunho(cfg, a_enviar, registro, itens[0])

    canais = _canais_reais(cfg)
    indisponiveis = {nome: canal.disponivel() for nome, canal in canais.items()}
    usados = {p.canal for p in a_enviar}
    for nome in sorted(usados):
        if indisponiveis[nome]:
            log.error("Canal %s indisponivel: %s", nome, indisponiveis[nome])
    if any(indisponiveis[nome] for nome in usados):
        log.error("Configure o canal, ou restrinja com --canal, ou use --rascunho.")
        return 2

    travas = {"email": cfg.destinatario_teste, "whatsapp": cfg.telefone_teste}
    sem_trava = {canal for canal in usados if not travas[canal]}
    if not args.sim and not _confirmar(len(a_enviar), sem_trava):
        log.info("Cancelado. Nada foi enviado.")
        return 0

    try:
        if "email" in usados:
            with canais["email"]:  # uma conexao SMTP para a leva inteira
                enviados, falhas, barrados = executar(cfg, a_enviar, canais, registro, cota=cota)
        else:
            enviados, falhas, barrados = executar(cfg, a_enviar, canais, registro, cota=cota)
    except FalhaFatal as erro:
        # Credencial recusada. Parar aqui e a protecao: repetir e o que bloqueia a conta.
        log.error("%s", erro)
        log.error("A leva foi interrompida. O que ja saiu esta registrado.")
        return CODIGO_FALHA_DE_ENVIO
    except FalhaNoEnvio as erro:
        # Falha ao ABRIR a conexao: nenhuma mensagem chegou a ser tentada. Sair limpo,
        # sem traceback — o operador precisa da mensagem, nao da pilha.
        log.error("%s", erro)
        log.error("Nada foi enviado.")
        return CODIGO_FALHA_DE_ENVIO

    _registrar_historico(cfg, fabricantes, registro, enviados, falhas, barrados)

    log.info("-" * 72)
    log.info("RESUMO — %d de %d entregues", len(enviados), len(a_enviar))
    for passo, erro in falhas:
        log.info("  FALHA %-28s %-9s %s", passo.item.fabricante, passo.canal, erro)
    if barrados:
        log.info("")
        log.info("%d nao tentado(s) — ficam para a proxima rodada:", len(barrados))
        for passo, motivo in barrados:
            log.info("  %-28s %-9s %s", passo.item.fabricante, passo.canal, motivo)
    log.info("-" * 72)
    return CODIGO_FALHA_DE_ENVIO if (falhas or barrados) else 0


def _registrar_historico(
    cfg: Config,
    fabricantes: list[Fabricante],
    registro: RegistroDeEnvios,
    enviados: list[Passo],
    falhas: list[tuple[Passo, str]],
    barrados: list[tuple[Passo, str]],
) -> None:
    """Anota o envio no historico e reescreve as planilhas do FORMATADO_DIR/logs.

    Registra as tres saidas, nao so a entrega: o que falhou e o que nem chegou a ser
    tentado sao justamente o que alguem precisa achar no dia seguinte. O logs/envios.jsonl
    continua so com o que saiu — e ele que alimenta a cota horaria.
    """
    de_quem = {f.nome: nome_do_comprador(f, cfg) for f in fabricantes}

    def evento(passo: Passo, desfecho: str, motivo: str = "") -> dict:
        return historico.evento_envio(
            comprador=de_quem.get(passo.item.fabricante, cfg.comprador),
            laboratorio=passo.item.fabricante,
            periodo=passo.item.rotulo,
            canal=passo.canal,
            destinatario=passo.alvo,
            resultado=desfecho,
            motivo=motivo,
            identificador=registro.identificador(
                passo.item.fabricante, passo.item.rotulo, passo.canal
            ),
        )

    eventos = [evento(passo, "ok") for passo in enviados]
    eventos += [evento(passo, "falha", erro) for passo, erro in falhas]
    eventos += [evento(passo, "nao tentado", motivo) for passo, motivo in barrados]
    historico.atualizar(cfg.historico_path, cfg.historico_dir, eventos)


def _executar_rascunho(
    cfg: Config, passos: list[Passo], registro: RegistroDeEnvios, primeiro: ItemDaRodada
) -> int:
    """Modo contingencia: grava em disco para o comprador enviar a mao."""
    pasta = cfg.envios_dir / f"{date.today():%Y-%m-%d}_{primeiro.rotulo}"
    canais: dict[str, Canal] = {
        "email": CanalRascunhoEmail(cfg, pasta),
        "whatsapp": CanalRascunhoWhatsApp(cfg, pasta, primeiro.periodo),
    }
    enviados, falhas, _ = executar(cfg, passos, canais, registro, registrar=False)

    pagina = canais["whatsapp"].finalizar()
    sem_anexo = [p.item.fabricante for p in passos if p.canal == "whatsapp" and p.com_anexo]

    log.info("-" * 72)
    log.info("RASCUNHO — %d arquivo(s) montado(s) em %s", len(enviados), pasta)
    if pagina:
        log.info("Pagina de WhatsApp: %s", pagina.name)
    if sem_anexo:
        log.info(
            "Sem o anexo no WhatsApp (o link wa.me nao carrega arquivo): %s", ", ".join(sem_anexo)
        )
    for passo, erro in falhas:
        log.info("  FALHA %-28s %-9s %s", passo.item.fabricante, passo.canal, erro)
    log.info("Nada foi enviado. Abra os .eml, confira e clique em Enviar.")
    log.info("-" * 72)
    return CODIGO_FALHA_DE_ENVIO if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
