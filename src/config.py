"""Carga e validacao da configuracao: variaveis de ambiente (.env) e fabricantes.yaml."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src.periodo import DIAS_SEMANA, JANELAS_SEMANAIS, normalizar_dia

RAIZ_PROJETO = Path(__file__).resolve().parent.parent

CANAIS = ("email", "whatsapp")

# E.164: "+" seguido do pais e do numero, sem espaco nem pontuacao. O link do WhatsApp so
# funciona nesse formato, e o erro so apareceria na hora de clicar.
_E164 = re.compile(r"^\+\d{10,15}$")


class ConfiguracaoInvalida(Exception):
    """Configuracao ausente ou malformada — erro do operador, nao do Geweb."""


@dataclass(frozen=True)
class Config:
    """Parametros de execucao lidos do .env."""

    url_base: str
    usuario: str
    senha: str
    download_dir: Path
    formatado_dir: Path
    envios_dir: Path
    templates_dir: Path
    auth_state_path: Path
    sequencia_path: Path
    estado_path: Path
    rodada_path: Path
    envios_path: Path
    envios_historico_path: Path
    headless: bool
    timeout_ms: int
    timeout_relatorio_ms: int
    slow_mo_ms: int
    comprador: str
    comprador_cargo: str
    comprador_telefones: str
    remetente: str
    responder_para: str
    destinatario_teste: tuple[str, ...]
    telefone_teste: str
    smtp_host: str
    smtp_porta: int
    smtp_usuario: str
    smtp_senha: str
    smtp_seguranca: str
    whatsapp_provedor: str
    whatsapp_url_base: str
    whatsapp_instancia: str
    whatsapp_token: str
    whatsapp_client_token: str
    intervalo_envio_s: float
    max_envios_por_rodada: int
    max_envios_por_hora: int
    max_falhas_seguidas: int
    max_tentativas: int
    max_anexo_mb: int

    def mascarar(self) -> str:
        """Representacao segura para log — sem senha."""
        return (
            f"url={self.url_base} usuario={self.usuario} headless={self.headless} "
            f"download_dir={self.download_dir} formatado_dir={self.formatado_dir}"
        )

    @property
    def email_configurado(self) -> bool:
        """Ha credenciais de SMTP para enviar de verdade."""
        return bool(self.smtp_host and self.smtp_usuario and self.smtp_senha)

    @property
    def whatsapp_configurado(self) -> bool:
        return bool(self.whatsapp_url_base and self.whatsapp_instancia and self.whatsapp_token)

    @property
    def em_teste(self) -> bool:
        """Alguma trava de teste esta ligada — nenhuma industria sera tocada nesse canal."""
        return bool(self.destinatario_teste or self.telefone_teste)


@dataclass(frozen=True)
class Contatos:
    """Para quem o mapa de um laboratorio vai, e por qual canal.

    Fica vazio por padrao: um laboratorio sem contato continua sendo extraido normalmente,
    e o disparo apenas o pula com aviso nominal. Nao ter destinatario e uma pendencia de
    cadastro, nao um erro de configuracao que deva travar a rodada.
    """

    emails: tuple[str, ...] = ()
    copia: tuple[str, ...] = ()
    whatsapp: tuple[str, ...] = ()
    canais: tuple[str, ...] = ("email",)
    # Algumas industrias querem a planilha no WhatsApp; a maioria so quer o aviso de que o
    # mapa foi por e-mail. Por isso a escolha e por laboratorio, e o padrao e nao anexar.
    whatsapp_anexo: bool = False

    @property
    def vazio(self) -> bool:
        return not self.emails and not self.whatsapp

    def recebe_por(self, canal: str) -> bool:
        """True se este laboratorio deve receber por `canal` e ha para onde mandar."""
        if canal not in self.canais:
            return False
        return bool(self.emails) if canal == "email" else bool(self.whatsapp)


@dataclass(frozen=True)
class Comprador:
    """Quem compra deste laboratorio: assina a mensagem e recebe a resposta da industria.

    Opcional por fabricante. Ausente, valem o COMPRADOR e o RESPONDER_PARA do .env — que e
    o caso enquanto houver um comprador so. A planilha do comprador ja tem uma coluna
    COMPRADOR, entao mais de um e questao de tempo, e o nome errado assinando um mapa e um
    erro que a industria ve.
    """

    nome: str = ""
    responder_para: str = ""
    # Campos da assinatura (templates/email.html e email.txt). Vazios caem no .env.
    cargo: str = ""
    telefones: str = ""


@dataclass(frozen=True)
class Fabricante:
    """Um laboratorio/fabricante a processar.

    `codigos` sao os codigos do Geweb — a lista do campo Fabricante mostra
    "(13963) EUROFARMA LABORATORIOS (RX)". Buscar por codigo evita erro de acentuacao.

    Um mesmo laboratorio costuma ter varios codigos (um por divisao/CD: RX, OTC, generico,
    cada centro de distribuicao). Como o campo aceita multipla escolha, todos entram no
    mesmo relatorio. Rode `python -m src.descobrir --fabricantes` para ver a lista completa.

    `mensal` e `dias_semana` vem da planilha "FABRICANTES ENVIO MAPA.xlsx": a coluna MENSAL
    esta marcada para todos, e algumas linhas tem X tambem num dia da semana. Um fabricante
    pode, portanto, gerar DOIS relatorios diferentes — o mensal e o semanal.
    """

    nome: str
    codigos: tuple[str, ...]
    mensal: bool = True
    dias_semana: tuple[str, ...] = ()
    janela_semanal: str = "acumulado_mes"
    ativo: bool = True
    contatos: Contatos = field(default_factory=Contatos)
    # None (e nao um Comprador vazio) para distinguir "nao cadastrado" de "cadastrado em
    # branco": so o primeiro cai no padrao do .env.
    comprador: Comprador | None = None

    @property
    def resumo_codigos(self) -> str:
        return ", ".join(self.codigos)

    @property
    def resumo_envio(self) -> str:
        partes = ["mensal"] if self.mensal else []
        partes += [f"semanal({'+'.join(self.dias_semana)})"] if self.dias_semana else []
        return " ".join(partes) or "nenhum envio"


def _lista_de_textos(bruto: object) -> list[str]:
    """Aceita tanto `emails: um@x.com` quanto `emails: [um@x.com, dois@x.com]`."""
    if bruto is None or bruto == "":
        return []
    if not isinstance(bruto, list):
        bruto = [bruto]
    return [str(item).strip() for item in bruto if str(item).strip()]


def _ler_contatos(item: dict, nome: str) -> Contatos:
    """Le o bloco `contatos` de um fabricante e valida o que iria falhar so no envio."""
    bruto = item.get("contatos") or {}
    if not isinstance(bruto, dict):
        raise ConfiguracaoInvalida(
            f"Fabricante {nome!r}: 'contatos' precisa ser um bloco com 'emails', 'copia', "
            "'whatsapp' e 'canais'."
        )

    emails = _lista_de_textos(bruto.get("emails"))
    copia = _lista_de_textos(bruto.get("copia"))
    telefones = _lista_de_textos(bruto.get("whatsapp"))

    for endereco in emails + copia:
        if "@" not in endereco or endereco.startswith("@") or endereco.endswith("@"):
            raise ConfiguracaoInvalida(f"Fabricante {nome!r}: e-mail invalido: {endereco!r}.")

    for telefone in telefones:
        if not _E164.match(telefone):
            raise ConfiguracaoInvalida(
                f"Fabricante {nome!r}: telefone {telefone!r} fora do padrao internacional. "
                'Use +55 seguido de DDD e numero, sem espacos: "+5511999999999".'
            )

    canais = [c.lower() for c in _lista_de_textos(bruto.get("canais"))] or ["email"]
    for canal in canais:
        if canal not in CANAIS:
            raise ConfiguracaoInvalida(
                f"Fabricante {nome!r}: canal {canal!r} desconhecido. Use {' ou '.join(CANAIS)}."
            )

    return Contatos(
        emails=tuple(emails),
        copia=tuple(copia),
        whatsapp=tuple(telefones),
        canais=tuple(dict.fromkeys(canais)),
        whatsapp_anexo=bool(bruto.get("whatsapp_anexo", False)),
    )


def _ler_comprador(item: dict, nome: str) -> Comprador | None:
    """Le o bloco `comprador` de um fabricante. Ausente devolve None (usa o padrao do .env)."""
    bruto = item.get("comprador")
    if bruto is None:
        return None
    if not isinstance(bruto, dict):
        raise ConfiguracaoInvalida(
            f"Fabricante {nome!r}: 'comprador' precisa ser um bloco com 'nome' e "
            "'responder_para'."
        )

    nome_comprador = str(bruto.get("nome", "")).strip()
    responder_para = str(bruto.get("responder_para", "")).strip()
    cargo = str(bruto.get("cargo", "")).strip()
    telefones = str(bruto.get("telefones", "")).strip()
    if not nome_comprador:
        raise ConfiguracaoInvalida(
            f"Fabricante {nome!r}: 'comprador' sem 'nome'. E o nome que assina a mensagem — "
            "sem ele a industria receberia um mapa sem assinatura."
        )
    for endereco in responder_para.replace(";", ",").split(","):
        endereco = endereco.strip()
        if endereco and ("@" not in endereco or endereco.startswith("@") or endereco.endswith("@")):
            raise ConfiguracaoInvalida(
                f"Fabricante {nome!r}: 'responder_para' invalido: {endereco!r}."
            )
    return Comprador(
        nome=nome_comprador,
        responder_para=responder_para,
        cargo=cargo,
        telefones=telefones,
    )


def _ler_bool(chave: str, padrao: bool) -> bool:
    bruto = os.getenv(chave)
    if bruto is None or bruto.strip() == "":
        return padrao
    return bruto.strip().lower() in {"1", "true", "sim", "yes", "y"}


def _ler_int(chave: str, padrao: int) -> int:
    bruto = os.getenv(chave)
    if bruto is None or bruto.strip() == "":
        return padrao
    try:
        return int(bruto)
    except ValueError as erro:
        raise ConfiguracaoInvalida(f"{chave} deve ser um numero inteiro, recebido: {bruto!r}") from erro


def _ler_obrigatorio(chave: str) -> str:
    valor = os.getenv(chave, "").strip()
    if not valor:
        raise ConfiguracaoInvalida(
            f"Variavel {chave} nao definida. Copie .env.example para .env e preencha."
        )
    return valor


def carregar_config(headless_override: bool | None = None) -> Config:
    """Le o .env da raiz do projeto e devolve a Config validada."""
    load_dotenv(RAIZ_PROJETO / ".env")

    download_dir = RAIZ_PROJETO / os.getenv("DOWNLOAD_DIR", "downloads")
    # Onde fica o .xlsx formatado, pronto para enviar. Arvore separada do bruto do Geweb.
    formatado_dir = RAIZ_PROJETO / os.getenv("FORMATADO_DIR", "formatado")
    headless = _ler_bool("HEADLESS", padrao=False) if headless_override is None else headless_override

    # Onde ficam os rascunhos de envio (.eml e a pagina de WhatsApp) quando se roda o
    # comando com --rascunho. No modo normal o disparo envia de verdade.
    envios_dir = RAIZ_PROJETO / os.getenv("ENVIOS_DIR", "envios")

    seguranca = os.getenv("SMTP_SEGURANCA", "starttls").strip().lower()
    if seguranca not in ("starttls", "ssl"):
        raise ConfiguracaoInvalida(
            f"SMTP_SEGURANCA={seguranca!r} invalido. Use 'starttls' (porta 587) ou 'ssl' (porta 465)."
        )

    # Um typo aqui nao daria erro nenhum: as respostas das industrias simplesmente iriam
    # para um endereco que nao existe. Barato conferir, caro descobrir tarde.
    responder_para = os.getenv("RESPONDER_PARA", "").strip()
    for endereco in responder_para.replace(";", ",").split(","):
        endereco = endereco.strip()
        if endereco and ("@" not in endereco or endereco.startswith("@") or endereco.endswith("@")):
            raise ConfiguracaoInvalida(
                f"RESPONDER_PARA tem endereco invalido: {endereco!r}. "
                "Separe varios por virgula."
            )

    # A trava de e-mail aceita mais de um endereco. Homologar quase sempre envolve mais de
    # uma pessoa — o comprador precisa ver o que a industria veria — e a alternativa seria
    # desligar a trava para conseguir isso, que e exatamente o que ela existe para evitar.
    destinatario_teste = tuple(
        endereco
        for bruto in os.getenv("DESTINATARIO_TESTE", "").replace(";", ",").split(",")
        if (endereco := bruto.strip())
    )
    for endereco in destinatario_teste:
        if "@" not in endereco or endereco.startswith("@") or endereco.endswith("@"):
            raise ConfiguracaoInvalida(
                f"DESTINATARIO_TESTE tem endereco invalido: {endereco!r}. "
                "Separe varios por virgula."
            )

    telefone_teste = os.getenv("TELEFONE_TESTE", "").strip()
    if telefone_teste and not _E164.match(telefone_teste):
        raise ConfiguracaoInvalida(
            f"TELEFONE_TESTE={telefone_teste!r} fora do padrao internacional. "
            'Use +55 seguido de DDD e numero, sem espacos: "+5511999999999".'
        )

    return Config(
        url_base=_ler_obrigatorio("GEWEB_URL"),
        usuario=_ler_obrigatorio("GEWEB_USUARIO"),
        senha=_ler_obrigatorio("GEWEB_SENHA"),
        download_dir=download_dir,
        formatado_dir=formatado_dir,
        envios_dir=envios_dir,
        templates_dir=RAIZ_PROJETO / "templates",
        auth_state_path=RAIZ_PROJETO / ".auth" / "state.json",
        sequencia_path=RAIZ_PROJETO / "sequencia.json",
        estado_path=RAIZ_PROJETO / "estado.json",
        rodada_path=RAIZ_PROJETO / "ultima-rodada.json",
        envios_path=RAIZ_PROJETO / "envios.json",
        # Historico append-only: conta a cota horaria e serve de auditoria do que saiu.
        envios_historico_path=RAIZ_PROJETO / "logs" / "envios.jsonl",
        headless=headless,
        timeout_ms=_ler_int("TIMEOUT_MS", 30_000),
        timeout_relatorio_ms=_ler_int("TIMEOUT_RELATORIO_MS", 180_000),
        slow_mo_ms=_ler_int("SLOW_MO_MS", 0),
        comprador=os.getenv("COMPRADOR", "").strip(),
        comprador_cargo=os.getenv("COMPRADOR_CARGO", "").strip(),
        comprador_telefones=os.getenv("COMPRADOR_TELEFONES", "").strip(),
        remetente=os.getenv("REMETENTE", "").strip(),
        responder_para=responder_para,
        destinatario_teste=destinatario_teste,
        telefone_teste=telefone_teste,
        smtp_host=os.getenv("SMTP_HOST", "").strip(),
        smtp_porta=_ler_int("SMTP_PORTA", 587),
        smtp_usuario=os.getenv("SMTP_USUARIO", "").strip(),
        smtp_senha=os.getenv("SMTP_SENHA", ""),  # sem strip: senha pode ter espaco nas pontas
        smtp_seguranca=seguranca,
        whatsapp_provedor=os.getenv("WHATSAPP_PROVEDOR", "zapi").strip().lower(),
        whatsapp_url_base=os.getenv("ZAPI_URL_BASE", "https://api.z-api.io").strip().rstrip("/"),
        whatsapp_instancia=os.getenv("ZAPI_INSTANCIA", "").strip(),
        whatsapp_token=os.getenv("ZAPI_TOKEN", "").strip(),
        whatsapp_client_token=os.getenv("ZAPI_CLIENT_TOKEN", "").strip(),
        intervalo_envio_s=float(_ler_int("INTERVALO_ENVIO_S", 5)),
        # Limites de seguranca. Os padroes ja protegem quem nao mexer no .env: sao 24
        # laboratorios reais, e a Locaweb aceita 100 mensagens/hora por caixa.
        max_envios_por_rodada=_ler_int("MAX_ENVIOS_POR_RODADA", 30),
        max_envios_por_hora=_ler_int("MAX_ENVIOS_POR_HORA", 90),
        max_falhas_seguidas=_ler_int("MAX_FALHAS_SEGUIDAS", 3),
        max_tentativas=_ler_int("MAX_TENTATIVAS", 3),
        max_anexo_mb=_ler_int("MAX_ANEXO_MB", 10),
    )


def carregar_fabricantes(caminho: Path | None = None) -> list[Fabricante]:
    """Le fabricantes.yaml e devolve apenas os marcados como ativos."""
    arquivo = caminho or RAIZ_PROJETO / "fabricantes.yaml"
    if not arquivo.exists():
        raise ConfiguracaoInvalida(f"Arquivo de fabricantes nao encontrado: {arquivo}")

    dados = yaml.safe_load(arquivo.read_text(encoding="utf-8")) or {}
    itens = dados.get("fabricantes")
    if not isinstance(itens, list) or not itens:
        raise ConfiguracaoInvalida(f"{arquivo.name} precisa conter uma lista nao vazia em 'fabricantes'.")

    fabricantes: list[Fabricante] = []
    for indice, item in enumerate(itens, start=1):
        if not isinstance(item, dict) or not item.get("nome"):
            raise ConfiguracaoInvalida(f"Item {indice} de {arquivo.name} precisa ter o campo 'nome'.")
        nome = str(item["nome"]).strip()
        bruto = item.get("codigos", item.get("codigo"))
        if not bruto:
            raise ConfiguracaoInvalida(
                f"Fabricante {nome!r} em {arquivo.name} precisa de 'codigo' ou 'codigos' "
                "(os codigos do Geweb, ex.: 13963). Veja logs/fabricantes-geweb.txt."
            )
        # str() porque o YAML le 13963 como numero, e a busca no Geweb e textual.
        codigos = [str(bruto).strip()] if not isinstance(bruto, list) else [str(c).strip() for c in bruto]

        if "periodicidade" in item:
            raise ConfiguracaoInvalida(
                f"Fabricante {nome!r}: o campo 'periodicidade' foi substituido. "
                "Use 'mensal: true/false' e 'dias_semana: [segunda, quarta]' — um fabricante "
                "pode receber os dois envios. Veja os comentarios no topo do fabricantes.yaml."
            )

        dias_brutos = item.get("dias_semana") or []
        if not isinstance(dias_brutos, list):
            dias_brutos = [dias_brutos]
        dias: list[str] = []
        for bruto_dia in dias_brutos:
            dia = normalizar_dia(bruto_dia)
            if dia not in DIAS_SEMANA:
                raise ConfiguracaoInvalida(
                    f"Fabricante {nome!r}: dia {bruto_dia!r} invalido. "
                    f"Use um de: {', '.join(DIAS_SEMANA)}."
                )
            if dia not in dias:  # o mesmo dia duas vezes geraria o relatorio em duplicata
                dias.append(dia)
        # Ordena pelo dia da semana, nao pela ordem digitada — o plano do dia fica legivel.
        dias.sort(key=lambda d: DIAS_SEMANA[d])

        janela = str(item.get("janela_semanal", "acumulado_mes")).strip().lower()
        if janela not in JANELAS_SEMANAIS:
            raise ConfiguracaoInvalida(
                f"Fabricante {nome!r}: janela_semanal {janela!r} invalida. "
                f"Use uma de: {', '.join(JANELAS_SEMANAIS)}."
            )

        mensal = bool(item.get("mensal", True))
        if not mensal and not dias:
            raise ConfiguracaoInvalida(
                f"Fabricante {nome!r} nao tem nenhum envio: defina 'mensal: true' "
                "ou informe 'dias_semana'. Para desligar o fabricante use 'ativo: false'."
            )

        fabricantes.append(
            Fabricante(
                nome=nome,
                codigos=tuple(c for c in codigos if c),
                mensal=mensal,
                dias_semana=tuple(dias),
                janela_semanal=janela,
                ativo=bool(item.get("ativo", True)),
                contatos=_ler_contatos(item, nome),
                comprador=_ler_comprador(item, nome),
            )
        )

    ativos = [f for f in fabricantes if f.ativo]
    if not ativos:
        raise ConfiguracaoInvalida(f"Nenhum fabricante ativo em {arquivo.name}.")
    return ativos
