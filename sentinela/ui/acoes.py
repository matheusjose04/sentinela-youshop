"""Ações do atendente durante a sessão (resolvido, encaminhado, devolvido).

Puro e imutável: cada registro devolve uma lista NOVA. Quem guarda é o app
(st.session_state["acoes"]). Nada aqui decide pelo atendente: só anota o que ele fez.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sentinela.core.modelos import CENTROS

__all__ = ["CENTROS", "centros_para_devolver", "registrar_acao", "status_do_chamado"]

TIPOS_ACAO: frozenset[str] = frozenset({"resolvido", "encaminhado", "devolvido"})
LIMITE_OBSERVACAO = 500
LIMITE_ACOES = 200  # a sessão guarda só as últimas 200 ações


def centros_para_devolver(atual: str) -> tuple[str, ...]:
    """Centros para onde o chamado pode ser devolvido (todos menos o atual)."""
    return tuple(c for c in CENTROS if c != atual)


def registrar_acao(
    acoes: Sequence[dict[str, Any]],
    *,
    tipo: str,
    chamado_id: str,
    centro: str,
    em: datetime,
    destino: str | None = None,
    observacao: str = "",
) -> list[dict[str, Any]]:
    """Devolve uma lista nova com a ação no fim (só as últimas 200).

    "devolvido" exige destino diferente do centro.
    """
    if tipo not in TIPOS_ACAO:
        raise ValueError(f"tipo de ação desconhecido: {tipo!r}")
    if tipo == "devolvido" and destino not in centros_para_devolver(centro):
        raise ValueError(f"destino inválido para devolver: {destino!r}")
    registro = {
        "tipo": tipo,
        "chamado_id": chamado_id,
        "centro": centro,
        "destino": destino if tipo == "devolvido" else None,
        "observacao": observacao.strip()[:LIMITE_OBSERVACAO],
        "em": em.isoformat(),
    }
    return [*acoes, registro][-LIMITE_ACOES:]


def status_do_chamado(acoes: Sequence[dict[str, Any]], chamado_id: str) -> str:
    """Status pela ÚLTIMA ação do chamado; "aberto" se não houver nenhuma."""
    ultima = next((a for a in reversed(acoes) if a["chamado_id"] == chamado_id), None)
    if ultima is None:
        return "aberto"
    if ultima["tipo"] == "devolvido":
        return f"devolvido para {ultima['destino']}"
    return ultima["tipo"]
