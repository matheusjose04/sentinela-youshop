"""Score de prioridade decomponível e fila de prioridade com heapq."""
from __future__ import annotations

import heapq
from dataclasses import dataclass
from datetime import datetime, timedelta

from sentinela.core.modelos import AlertaSaque, Chamado, Parcela, Score

# Tetos de cada parcela (somam 100).
MAX_SEGURANCA = 40
MAX_DINHEIRO = 25
MAX_GRUPO = 20
MAX_ESPERA = 15

# Pontos de segurança por sinal (somados e depois limitados a 40).
PTS_SAQUE_EM_ESPERA = 40
PTS_FRAUDE_NO_GRUPO = 20
PTS_COMPARTILHAMENTO = 10

VALOR_TETO = 5000.0  # R$ 5.000 ou mais em risco = parcela de dinheiro cheia
HORAS_ESPERA_TETO = 48  # a espera enche em 48 h: ninguém fica esquecido
PTS_POR_CONTA = 5  # cada conta a mais no grupo vale 5 pontos

FAIXA_ALTA = 50
FAIXA_MEDIA = 20


@dataclass(frozen=True)
class ContextoScore:
    """O que o grafo e os eventos dizem sobre o chamado (montado em caso.py)."""

    alerta_saque: AlertaSaque | None = None
    fraude_no_grupo: bool = False
    compartilhamento: bool = False  # celular ou chave Pix usado por 2+ contas
    contas_no_grupo: int = 1  # contas no grupo de segurança (BFS sem atravessar produto)
    contas_da_causa: int = 0  # compradores distintos afetados pela mesma causa/alvo (30 dias)
    alvo_causa: str | None = None  # rótulo do creator/produto alvo, para o motivo


def _tamanho_grupo(ctx: ContextoScore) -> tuple[int, bool]:
    """(tamanho usado na parcela, veio da causa?). Vale o maior dos dois grupos."""
    if ctx.contas_da_causa > ctx.contas_no_grupo:
        return ctx.contas_da_causa, True
    return ctx.contas_no_grupo, False


def _limitar(valor: float, maximo: float) -> float:
    """Clamp: nenhuma parcela fica abaixo de 0 nem acima do teto."""
    return round(max(0.0, min(float(maximo), valor)), 2)


def formatar_brl(valor: float) -> str:
    """4200 -> 'R$ 4.200'; 159.9 -> 'R$ 159,90'."""
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return "R$ " + texto.removesuffix(",00")


def formatar_espera(delta: timedelta) -> str:
    minutos = max(0, int(delta.total_seconds() // 60))
    if minutos < 60:
        return f"{minutos} min"
    horas = minutos // 60
    if horas < 24:
        return f"{horas} h"
    return f"{horas // 24} d {horas % 24} h"


def faixa(total: float) -> str:
    """Badge de prioridade para a UI."""
    if total >= FAIXA_ALTA:
        return "alta"
    if total >= FAIXA_MEDIA:
        return "média"
    return "baixa"


def calcular_score(chamado: Chamado, ctx: ContextoScore, agora: datetime) -> Score:
    """Score = segurança (0–40) + dinheiro (0–25) + grupo (0–20) + espera (0–15).

    O texto livre do chamado NÃO entra no cálculo: ninguém sobe ou desce na fila
    escrevendo algo (defesa contra prompt injection).
    """
    alerta = ctx.alerta_saque

    seg_bruto = (
        (PTS_SAQUE_EM_ESPERA if alerta else 0)
        + (PTS_FRAUDE_NO_GRUPO if ctx.fraude_no_grupo else 0)
        + (PTS_COMPARTILHAMENTO if ctx.compartilhamento else 0)
    )
    seguranca = _limitar(seg_bruto, MAX_SEGURANCA)

    em_risco = max(chamado.valor, alerta.valor if alerta else 0.0)
    dinheiro = _limitar(MAX_DINHEIRO * em_risco / VALOR_TETO, MAX_DINHEIRO)

    tamanho, da_causa = _tamanho_grupo(ctx)
    grupo = _limitar(PTS_POR_CONTA * (tamanho - 1), MAX_GRUPO)
    grupo_txt = (
        f"{tamanho} compradores com a mesma causa ligados a {ctx.alvo_causa}"
        if da_causa
        else f"{ctx.contas_no_grupo} conta(s) ligada(s) no grafo"
    )

    # Envelhecimento: a espera cresce linearmente com o tempo até o teto.
    esperando = agora - chamado.aberto_em
    horas = esperando.total_seconds() / 3600
    espera = _limitar(MAX_ESPERA * horas / HORAS_ESPERA_TETO, MAX_ESPERA)
    espera_txt = formatar_espera(esperando)

    sinais_seg = [
        nome
        for nome, ativo in [
            ("saque em espera", alerta is not None),
            ("ligado a fraude confirmada", ctx.fraude_no_grupo),
            ("celular ou chave Pix em comum", ctx.compartilhamento),
        ]
        if ativo
    ]
    parcelas = (
        Parcela("segurança", seguranca, MAX_SEGURANCA, " + ".join(sinais_seg) or "nenhum sinal de segurança"),
        Parcela("dinheiro", dinheiro, MAX_DINHEIRO, f"{formatar_brl(em_risco)} em risco (teto em {formatar_brl(VALOR_TETO)})"),
        Parcela("grupo", grupo, MAX_GRUPO, grupo_txt),
        Parcela("espera", espera, MAX_ESPERA, f"esperando há {espera_txt} (enche em {HORAS_ESPERA_TETO} h)"),
    )
    total = round(sum(p.pontos for p in parcelas), 2)
    return Score(parcelas=parcelas, total=total, motivo=motivo_texto(chamado, ctx, em_risco, dinheiro, espera, espera_txt))


def motivo_texto(
    chamado: Chamado, ctx: ContextoScore, em_risco: float, dinheiro: float, espera: float, espera_txt: str
) -> str:
    """UMA linha "Sobe: ..." com os fatores que pesaram (nunca vazia)."""
    partes: list[str] = []
    if ctx.alerta_saque:
        partes.append(f"saque de {formatar_brl(ctx.alerta_saque.valor)} em {ctx.alerta_saque.minutos} min")
    if ctx.fraude_no_grupo:
        partes.append("ligado a fraude confirmada")
    if ctx.compartilhamento and not ctx.alerta_saque:
        partes.append("celular ou chave Pix em comum entre contas")
    if not ctx.alerta_saque and dinheiro >= 5:
        partes.append(f"{formatar_brl(em_risco)} em risco")
    tamanho, da_causa = _tamanho_grupo(ctx)
    if da_causa and tamanho >= 2:
        partes.append(f"{tamanho} compradores com a mesma causa ligados a {ctx.alvo_causa}")
    elif tamanho >= 2:
        partes.append(f"grupo de {tamanho} contas no grafo")
    if espera >= 5:
        partes.append(f"esperando há {espera_txt}")
    if not partes:
        partes.append(f"só o tempo de espera ({espera_txt})")
    return "Sobe: " + " + ".join(partes)


class FilaPrioridade:
    """Fila com heapq. Entradas (-total, aberto_em, contador, ...).

    heapq é um min-heap, então uso o score NEGATIVO para o maior sair primeiro.
    Desempate estável: quem abriu antes, depois a ordem de chegada (contador).
    Envelhecimento: o score depende de `agora`, então o heap é reconstruído a cada
    ordenar(agora); um score calculado na entrada ficaria congelado e velho.
    """

    def __init__(self) -> None:
        self._itens: list[tuple[Chamado, ContextoScore]] = []

    def __len__(self) -> int:
        return len(self._itens)

    def adicionar(self, chamado: Chamado, ctx: ContextoScore) -> None:
        self._itens.append((chamado, ctx))

    def ordenar(self, agora: datetime) -> list[tuple[Chamado, Score]]:
        heap: list[tuple[float, float, int, Chamado, Score]] = []
        for contador, (chamado, ctx) in enumerate(self._itens):
            score = calcular_score(chamado, ctx, agora)
            heapq.heappush(heap, (-score.total, chamado.aberto_em.timestamp(), contador, chamado, score))
        # Esvaziar o heap devolve do maior para o menor score: O(n log n).
        saida: list[tuple[Chamado, Score]] = []
        while heap:
            _, _, _, chamado, score = heapq.heappop(heap)
            saida.append((chamado, score))
        return saida
