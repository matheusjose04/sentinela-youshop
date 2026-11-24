"""Fila agrupada para a tela. Puro: não importa streamlit (testável com pytest).

Chamados com a mesma causa (o mesmo `grupo_ids` da rota) viram UM item na fila.
A ordem continua a do heap: o grupo aparece onde está o seu chamado de maior score
(o primeiro dele na lista ordenada) e assume esse score.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from sentinela.core.caso import frase_alerta_grupo
from sentinela.core.roteamento import texto_grupo

_FLAGS = (("injecao", "tem_alerta_injecao"), ("saque", "tem_alerta_saque"))


def agrupar_fila(itens: Sequence[Mapping[str, Any]], grupos: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Agrupa `montar_fila(...)["itens"]` (já em ordem de heap) usando `grupos_dos_chamados(...)["grupos"]`.

    Cada item devolvido: lider (chamado de maior score), membros (na ordem do heap), titulo
    ("N chamados com a mesma causa" ou None se isolado), total, faixa, centro e motivo do líder,
    e esperando = a maior espera do grupo (chamado aberto há mais tempo).
    Só agrupa o que está visível (filtro de centro já aplicado).
    """
    saida: list[dict[str, Any]] = []
    por_chave: dict[tuple[str, ...], dict[str, Any]] = {}
    for item in itens:
        info = grupos.get(item["id"])
        chave = tuple(info["grupo_ids"]) if info else (item["id"],)
        if chave not in por_chave:
            # primeiro do grupo na ordem do heap = maior score: vira o líder
            por_chave[chave] = {"lider": item, "membros": []}
            saida.append(por_chave[chave])
        por_chave[chave]["membros"].append(item)
    return [_resumir(g["lider"], g["membros"], grupos) for g in saida]


def _aberto_em(grupos: Mapping[str, Mapping[str, Any]], chamado_id: str) -> datetime:
    """Data de abertura (com fuso); sem data conhecida conta como a mais nova."""
    try:
        return datetime.fromisoformat(str(grupos[chamado_id]["aberto_em"]))
    except (KeyError, ValueError):
        return datetime.max.replace(tzinfo=timezone.utc)


def _resumir(lider: Mapping[str, Any], membros: list[Mapping[str, Any]], grupos: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    # Todos foram medidos no mesmo "agora": o aberto mais cedo é o que espera há mais tempo.
    mais_antigo = min(membros, key=lambda m: _aberto_em(grupos, m["id"]))
    # Alertas de QUALQUER membro visível sobem para o item do grupo (o líder não os esconde).
    # Os ids vêm dos próprios itens da fila (da base), nunca de texto livre.
    flags, alertas = {}, []
    for tipo, chave in _FLAGS:
        ids = [m["id"] for m in membros if grupos.get(m["id"], {}).get(chave) is True]
        flags[chave] = any(ids)
        if ids:
            alertas.append({"tipo": tipo, "ids": ids, "texto": frase_alerta_grupo(tipo, ids, len(membros))})
    return {
        **flags,
        "alertas": alertas,
        "lider": lider,
        "membros": membros,
        "titulo": texto_grupo(len(membros)) if len(membros) > 1 else None,
        "total": lider["total"],
        "faixa": lider["faixa"],
        "centro": lider["centro"],
        "motivo": lider["motivo"],
        "esperando": mais_antigo["esperando"],
    }
