"""Fila agrupada (UI): chamados com a mesma causa viram um item só, na ordem do heap."""
from __future__ import annotations

import pytest

from sentinela.core.caso import grupos_dos_chamados, montar_fila
from sentinela.ui.agrupamento import agrupar_fila


def _item(cid: str, total: float, faixa: str = "alta", esperando: str = "1 h") -> dict:
    return {"id": cid, "total": total, "faixa": faixa, "centro": "Operações", "esperando": esperando,
            "motivo": f"Sobe: motivo de {cid}", "assunto": {"citacao": cid}, "parcelas": []}


GRUPOS = {
    "a": {"grupo_ids": ["a", "c"], "aberto_em": "2026-11-20T10:00:00-03:00"},
    "b": {"grupo_ids": ["b"], "aberto_em": "2026-11-20T11:00:00-03:00"},
    "c": {"grupo_ids": ["a", "c"], "aberto_em": "2026-11-20T08:00:00-03:00"},
}


def test_agrupa_mantendo_a_ordem_do_heap():
    itens = [_item("a", 90, esperando="5 h"), _item("b", 50), _item("c", 40, "média", esperando="7 h")]
    grupos = agrupar_fila(itens, GRUPOS)
    assert [g["lider"]["id"] for g in grupos] == ["a", "b"]
    g = grupos[0]
    assert [m["id"] for m in g["membros"]] == ["a", "c"]
    assert g["titulo"] == "2 chamados com a mesma causa"
    assert (g["total"], g["faixa"], g["centro"]) == (90, "alta", "Operações")  # assume o score máximo
    assert g["motivo"] == "Sobe: motivo de a"  # "por quê" do chamado de maior score
    assert g["esperando"] == "7 h"  # maior espera = aberto há mais tempo (c)


def test_chamado_isolado_vira_item_sem_titulo_de_grupo():
    grupos = agrupar_fila([_item("b", 50)], GRUPOS)
    assert len(grupos) == 1 and grupos[0]["titulo"] is None
    assert [m["id"] for m in grupos[0]["membros"]] == ["b"]


def test_so_agrupa_os_itens_visiveis():
    grupos = agrupar_fila([_item("c", 40)], GRUPOS)  # "a" fora do filtro
    assert grupos[0]["titulo"] is None and grupos[0]["lider"]["id"] == "c"


def test_id_sem_grupo_conhecido_fica_sozinho():
    grupos = agrupar_fila([_item("x", 10)], GRUPOS)
    assert [g["lider"]["id"] for g in grupos] == ["x"]


def test_fila_vazia():
    assert agrupar_fila([], GRUPOS) == []


def test_nao_altera_a_entrada():
    itens = [_item("a", 90), _item("c", 40)]
    copia = [dict(i) for i in itens]
    agrupar_fila(itens, GRUPOS)
    assert itens == copia


def test_cenario_3_vira_um_item(base, agora):
    itens = montar_fila(base, agora)["itens"]
    grupos = agrupar_fila(itens, grupos_dos_chamados(base, agora)["grupos"])
    rede = next(g for g in grupos if g["lider"]["id"] == "ch-301")
    assert [m["id"] for m in rede["membros"]] == ["ch-301", "ch-302", "ch-601"]
    assert rede["titulo"] == "3 chamados com a mesma causa"
    assert len(itens) == 12 and len(grupos) == 7
    assert sum(len(g["membros"]) for g in grupos) == 12
    totais = [g["total"] for g in grupos]
    assert totais == sorted(totais, reverse=True)


@pytest.mark.parametrize("centro,n", [("Operações", 2), ("Creator", 1), ("Produtor", 1), ("Comprador", 3)])
def test_filtro_por_centro_mantem_grupos_inteiros(base, agora, centro, n):
    itens = montar_fila(base, agora, centro)["itens"]
    grupos = agrupar_fila(itens, grupos_dos_chamados(base, agora)["grupos"])
    assert len(grupos) == n
    assert sum(len(g["membros"]) for g in grupos) == len(itens)


# ---------------------------------------------------------------- revisão: alertas agregados no grupo
def test_flags_de_alerta_agregadas_com_any():
    grupos = {
        "a": {"grupo_ids": ["a", "c"], "aberto_em": "2026-11-20T10:00:00-03:00",
              "tem_alerta_injecao": False, "tem_alerta_saque": False},
        "c": {"grupo_ids": ["a", "c"], "aberto_em": "2026-11-20T08:00:00-03:00",
              "tem_alerta_injecao": True, "tem_alerta_saque": False},
    }
    g = agrupar_fila([_item("a", 90), _item("c", 40)], grupos)[0]
    assert g["tem_alerta_injecao"] is True and g["tem_alerta_saque"] is False
    assert g["alertas"] == [{"tipo": "injecao", "ids": ["c"],
                             "texto": "1 chamado deste grupo tem texto tentando instruir a IA: c"}]


def test_sem_flags_conhecidas_nao_ha_alerta():
    g = agrupar_fila([_item("a", 90), _item("c", 40)], GRUPOS)[0]
    assert g["tem_alerta_injecao"] is False and g["tem_alerta_saque"] is False and g["alertas"] == []


def test_cenario_6_alerta_do_ch_601_sobe_para_o_grupo(base, agora):
    itens = montar_fila(base, agora)["itens"]
    grupos = agrupar_fila(itens, grupos_dos_chamados(base, agora)["grupos"])
    rede = next(g for g in grupos if g["lider"]["id"] == "ch-301")
    assert rede["tem_alerta_injecao"] is True
    assert rede["alertas"][0]["ids"] == ["ch-601"]
    saque = next(g for g in grupos if g["lider"]["id"] == "ch-401")
    assert saque["tem_alerta_saque"] is True
