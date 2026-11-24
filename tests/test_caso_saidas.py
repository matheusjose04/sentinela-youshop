"""Saídas públicas do core usadas pelo MCP: CENTROS e distancia_fraude."""
from typing import get_args

import pytest

from sentinela.core.caso import AVISO, distancia_fraude, montar_caso
from sentinela.core.modelos import CENTROS, Centro


def test_centros_no_core_batem_com_o_literal():
    assert CENTROS == ("Comprador", "Produtor", "Creator", "Operações")
    assert CENTROS == get_args(Centro)


def test_ui_reusa_centros_do_core():
    from sentinela.ui import acoes

    assert acoes.CENTROS is CENTROS


def test_distancia_fraude_igual_ao_caso(base, agora):
    for cid in base.chamados:
        d = distancia_fraude(cid, base, agora)
        assert d["aviso"] == AVISO
        assert d["chamado_id"] == cid
        caso = montar_caso(cid, base, agora)["distancia_fraude"]
        assert {k: d[k] for k in ("ligacoes", "caminho", "texto")} == caso, cid


def test_distancia_fraude_rede_de_comissao(base, agora):
    d = distancia_fraude("ch-301", base, agora)
    assert d["ligacoes"] is not None and d["ligacoes"] >= 1
    assert "fraude confirmada" in d["texto"]


def test_distancia_fraude_id_inexistente(base, agora):
    with pytest.raises(KeyError):
        distancia_fraude("ch-999", base, agora)


def test_montar_fila_aceita_analise_pronta(base, agora):
    from sentinela.core.caso import analisar, montar_fila

    assert montar_fila(base, agora, analise=analisar(base, agora)) == montar_fila(base, agora)
