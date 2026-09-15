"""Resolucao do periodo do relatorio e formatacao para a tela do Geweb.

Cada fabricante recebe o mapa MENSAL (mes anterior fechado, gerado no 1o dia util do mes —
que pula fim de semana E feriado nacional). Alguns recebem TAMBEM um envio semanal, nos
dias marcados na planilha "FABRICANTES ENVIO MAPA.xlsx" — esse envio cobre o mes corrente
ate ontem (acumulado).
"""

from __future__ import annotations

import calendar
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

import holidays

_FORMATO_MES = re.compile(r"^(\d{4})-(\d{2})$")
_FORMATO_DIA = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


class PeriodoInvalido(Exception):
    """Mes informado fora do formato AAAA-MM ou inexistente."""


@dataclass(frozen=True)
class Periodo:
    """Intervalo fechado [inicio, fim] correspondente a um mes cheio."""

    inicio: date
    fim: date

    @property
    def mes_cheio(self) -> bool:
        """True quando o intervalo cobre exatamente um mes inteiro."""
        ultimo = calendar.monthrange(self.inicio.year, self.inicio.month)[1]
        return self.inicio.day == 1 and self.fim.day == ultimo and self.inicio.month == self.fim.month

    @property
    def rotulo(self) -> str:
        """Identificador usado em nome de pasta.

        Mes cheio vira "2026-07"; qualquer outro intervalo vira "2026-07-01_a_2026-07-07",
        para que uma extracao semanal nunca sobrescreva a mensal.
        """
        if self.mes_cheio:
            return self.inicio.strftime("%Y-%m")
        return f"{self.inicio:%Y-%m-%d}_a_{self.fim:%Y-%m-%d}"

    @property
    def pasta_do_mes(self) -> str:
        """Pasta onde o relatorio e guardado: o MES DOS DADOS, "2026-08".

        Dentro dela convivem o mensal e todos os acumulados daquele mes, quantas vezes tenham
        sido tirados — o periodo exato fica no nome do arquivo (veja `rotulo`). O mensal de
        agosto, gerado em setembro, vai para 2026-08. Um intervalo que atravessa a virada do
        mes (semana_fechada de 28/09 a 02/10) fica no mes em que comeca.
        """
        return self.inicio.strftime("%Y-%m")

    @property
    def inicio_br(self) -> str:
        return self.inicio.strftime("%d/%m/%Y")

    @property
    def fim_br(self) -> str:
        return self.fim.strftime("%d/%m/%Y")

    def __str__(self) -> str:
        return f"{self.inicio_br} a {self.fim_br}"


def mes_cheio(ano: int, mes: int) -> Periodo:
    """Primeiro e ultimo dia do mes informado."""
    if not 1 <= mes <= 12:
        raise PeriodoInvalido(f"Mes fora do intervalo 1-12: {mes}")
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    return Periodo(inicio=date(ano, mes, 1), fim=date(ano, mes, ultimo_dia))


def mes_anterior(hoje: date | None = None) -> Periodo:
    """Mes cheio anterior ao mes corrente — padrao da rotina mensal."""
    referencia = hoje or date.today()
    if referencia.month == 1:
        return mes_cheio(referencia.year - 1, 12)
    return mes_cheio(referencia.year, referencia.month - 1)


def _dia(valor: str, rotulo_campo: str) -> date:
    casamento = _FORMATO_DIA.match(valor.strip())
    if not casamento:
        raise PeriodoInvalido(
            f"{rotulo_campo}: formato esperado AAAA-MM-DD (ex.: 2026-07-15), recebido: {valor!r}"
        )
    ano, mes, dia = (int(g) for g in casamento.groups())
    try:
        return date(ano, mes, dia)
    except ValueError as erro:
        raise PeriodoInvalido(f"{rotulo_campo}: data inexistente {valor!r}") from erro


def parsear_data(valor: str, rotulo_campo: str = "data") -> date:
    """Converte um argumento AAAA-MM-DD da linha de comando em date."""
    return _dia(valor, rotulo_campo)


def intervalo(inicio: str, fim: str) -> Periodo:
    """Periodo livre entre duas datas AAAA-MM-DD — usado nos mapas semanais e diarios."""
    data_inicio = _dia(inicio, "--inicio")
    data_fim = _dia(fim, "--fim")
    if data_fim < data_inicio:
        raise PeriodoInvalido(f"--fim ({data_fim}) e anterior a --inicio ({data_inicio}).")
    return Periodo(inicio=data_inicio, fim=data_fim)


SEXTA = 4
SABADO = 5


def semana_anterior(hoje: date | None = None) -> Periodo:
    """Ultima semana util fechada: segunda a sexta.

    Sabado e domingo ficam de fora — nao ha movimento e so sujariam o mapa.

    A ancora e a ultima sexta-feira ANTERIOR a hoje, nao a semana do calendario. Assim a
    rodada devolve a mesma semana quer rode na segunda, no sabado ou na quarta seguinte —
    e nunca inclui a semana corrente, que ainda nao fechou.
    """
    referencia = hoje or date.today()
    dias_desde_sexta = (referencia.weekday() - SEXTA) % 7
    sexta = referencia - timedelta(days=dias_desde_sexta or 7)
    return Periodo(inicio=sexta - timedelta(days=4), fim=sexta)


DIAS_SEMANA: dict[str, int] = {
    "segunda": 0,
    "terca": 1,
    "quarta": 2,
    "quinta": 3,
    "sexta": 4,
}
"""Dias em que um mapa pode ser enviado. As colunas D..H da planilha, nesta ordem."""

NOME_DO_DIA = {numero: nome for nome, numero in DIAS_SEMANA.items()}


def normalizar_dia(bruto: str) -> str:
    """"TERÇA-FEIRA", "terça", "Terca" -> "terca". Sem isso o acento vira erro de cadastro."""
    texto = unicodedata.normalize("NFKD", str(bruto).strip().lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.replace("-feira", "").replace("feira", "").strip()


_FERIADOS = holidays.Brazil()
"""Feriados NACIONAIS brasileiros. A instancia e unica e cacheia cada ano sob demanda.

Feriado municipal ou estadual nao entra aqui — aniversario da cidade, padroeira, etc.
Se algum dia atrapalhar, troque por holidays.Brazil(subdiv="SP") para incluir os de SP.
"""


def eh_dia_util(dia: date) -> bool:
    """Dia de expediente: nem fim de semana, nem feriado nacional.

    Ponto unico de verdade sobre o que conta como dia util. Sem o feriado, uma segunda
    de 1o de janeiro seria tratada como dia de trabalho: os 24 mensais disparariam com a
    empresa fechada, e o acumulado do dia seguinte cobriria so o proprio feriado.
    """
    return dia.weekday() < SABADO and dia not in _FERIADOS


def primeiro_dia_util(ano: int, mes: int) -> date:
    """Primeiro dia do mes com expediente — pula fim de semana e feriado nacional."""
    dia = date(ano, mes, 1)
    while not eh_dia_util(dia):
        dia += timedelta(days=1)
    return dia


def eh_primeiro_dia_util_do_mes(hoje: date | None = None) -> bool:
    """True somente no dia em que a rodada mensal deve gerar o mes anterior."""
    referencia = hoje or date.today()
    return referencia == primeiro_dia_util(referencia.year, referencia.month)


JANELAS_SEMANAIS = ("acumulado_mes", "semana_fechada")


def acumulado_do_mes(hoje: date | None = None) -> Periodo | None:
    """Do dia 1o do mes corrente ate ontem — o mes crescendo, como a industria acompanha.

    Devolve None quando o intervalo ainda nao contem nenhum dia util: no dia 1o nao ha
    "ontem" dentro do mes, e num mes que comeca no fim de semana ou em feriado os
    primeiros dias nao tem movimento. Gerar o relatorio nesses casos so produziria
    arquivo vazio.

    Na pratica isso acontece em UM dia por mes, e sempre o mesmo: o proprio 1o dia util,
    que e justamente quando o mensal do mes anterior fechado sai. Nenhum fabricante fica
    sem receber — ele recebe o mes fechado no lugar do acumulado.
    """
    referencia = hoje or date.today()
    inicio = referencia.replace(day=1)
    fim = referencia - timedelta(days=1)
    if fim < inicio:
        return None
    if not any(eh_dia_util(inicio + timedelta(days=d)) for d in range((fim - inicio).days + 1)):
        return None
    return Periodo(inicio=inicio, fim=fim)


def janela_semanal(tipo: str, hoje: date | None = None) -> Periodo | None:
    """Periodo coberto por um envio semanal, conforme a janela cadastrada no fabricante."""
    if tipo == "acumulado_mes":
        return acumulado_do_mes(hoje)
    if tipo == "semana_fechada":
        return semana_anterior(hoje)
    raise PeriodoInvalido(
        f"Janela semanal invalida: {tipo!r}. Use uma de: {', '.join(JANELAS_SEMANAIS)}."
    )


def resolver_periodo(
    mes: str | None = None,
    inicio: str | None = None,
    fim: str | None = None,
    hoje: date | None = None,
) -> Periodo | None:
    """Decide o periodo a partir dos argumentos da linha de comando.

    --inicio/--fim  -> intervalo livre (semanal, quinzenal, um dia so...)
    --mes           -> mes cheio
    nenhum          -> None: a rodada consulta a agenda do dia (veja src/agenda.py)
    """
    if not (mes or inicio or fim):
        return None

    if inicio or fim:
        if mes:
            raise PeriodoInvalido("Use --mes OU --inicio/--fim, nao os dois ao mesmo tempo.")
        if not (inicio and fim):
            raise PeriodoInvalido("--inicio e --fim devem ser usados juntos.")
        return intervalo(inicio, fim)

    casamento = _FORMATO_MES.match(mes.strip())
    if not casamento:
        raise PeriodoInvalido(f"--mes: formato esperado AAAA-MM (ex.: 2026-07), recebido: {mes!r}")
    return mes_cheio(int(casamento.group(1)), int(casamento.group(2)))
