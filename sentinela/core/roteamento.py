"""Roteamento pelo GRAFO (não pelo texto) para os centros de atendimento.

A precedência (Operações > Produtor > Creator > Comprador) é a ordem de causa.REGRAS:
a causa já vem das regras sobre grafo e dados estruturados; aqui só traduzimos
causa -> centro, explicamos "por que este centro" e agrupamos chamados.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

from sentinela.core.modelos import Causa, Centro, Rota

CENTRO_POR_CAUSA: dict[str, Centro] = {
    "conta_invadida": "Operações",
    "fraude": "Operações",
    "produto": "Produtor",
    "creator": "Creator",
    "ma_fe_comprador": "Comprador",
    "comum": "Comprador",
}

MOTIVO_POR_CAUSA: dict[str, str] = {
    "conta_invadida": "Os eventos da conta e o grafo mostram sinais de conta invadida (celular novo, chave Pix trocada, saque quase total): segurança é com Operações.",
    "fraude": "O grupo deste chamado no grafo tem fraude confirmada ou contas dividindo celular/chave Pix: segurança é com Operações.",
    "produto": "Creators diferentes geram o mesmo motivo de reembolso no mesmo produto: a origem está no produto, então vai para o Produtor.",
    "creator": "Os reembolsos se concentram em um creator cuja divulgação promete algo que o produto não tem: vai para o centro de Creators.",
    "ma_fe_comprador": "O padrão está no histórico do próprio comprador, não no produto nem no creator: vai para o centro de Compradores.",
    "comum": "Nenhum sinal no grafo aponta fraude, produto ou creator: atendimento normal no centro de Compradores.",
}


def rotear(causa: Causa, grupo_ids: Iterable[str] = ()) -> Rota:
    """Centro de destino + "por que este centro" + chamados do mesmo grupo."""
    return Rota(
        centro=CENTRO_POR_CAUSA[causa.tipo],
        motivo=MOTIVO_POR_CAUSA[causa.tipo],
        grupo_ids=tuple(sorted(grupo_ids)),
    )


def agrupar_chamados(
    causas: Mapping[str, Causa], componentes: Mapping[str, frozenset[str]]
) -> dict[str, tuple[str, ...]]:
    """Para cada chamado, os chamados com a MESMA causa e o MESMO alvo.

    - causa produto/creator: alvo = o produto ou o creator apontado (os compradores não se
      ligam entre si no grupo de segurança, então o alvo é quem os une);
    - demais causas: alvo = o grupo de segurança no grafo (BFS sem atravessar produto).
    Chamados do mesmo grupo vão para o mesmo atendente.
    """
    def chave(cid: str) -> tuple[str, str]:
        causa = causas[cid]
        return causa.tipo, causa.alvo if causa.tipo in ("produto", "creator") and causa.alvo else min(componentes[cid])

    grupos: dict[tuple[str, str], list[str]] = {}
    for cid in causas:
        grupos.setdefault(chave(cid), []).append(cid)
    return {cid: tuple(sorted(grupos[chave(cid)])) for cid in causas}


def texto_grupo(n: int) -> str:
    if n <= 1:
        return "chamado isolado (nenhum outro com a mesma causa)"
    return f"{n} chamados com a mesma causa"
