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


# ---------------------------------------------------------------- resumo_do_caso (cartão do topo do caso)
from sentinela.core.caso import grupos_dos_chamados, resumo_do_caso  # noqa: E402

CAMPOS_RESUMO = {"aviso", "chamado_id", "causa", "confianca", "contas", "chamados", "grupo_ids",
                 "afeta_texto", "valor", "valor_origem", "valor_texto", "em_risco", "centro", "alertas_grupo"}


def test_resumo_tem_os_campos_e_aviso(base, agora):
    for cid in base.chamados:
        r = resumo_do_caso(cid, base, agora)
        assert set(r) == CAMPOS_RESUMO, cid
        assert r["aviso"] == AVISO and r["chamado_id"] == cid
        assert r["confianca"] in ("alta", "média", "baixa")


def test_resumo_igual_ao_caso(base, agora):
    for cid in base.chamados:
        r, caso = resumo_do_caso(cid, base, agora), montar_caso(cid, base, agora)
        assert r["centro"] == caso["rota"]["centro"]
        assert r["grupo_ids"] == caso["rota"]["grupo_ids"]
        assert r["chamados"] == len(caso["rota"]["grupo_ids"])
        assert r["confianca"] == caso["causa"]["confianca"]


def test_resumo_causa_sem_rotulo_repetido(base, agora):
    for cid in base.chamados:
        texto = resumo_do_caso(cid, base, agora)["causa"]
        assert texto and "causa provável" not in texto.lower(), (cid, texto)


def test_resumo_cenario_3_grupo_de_comissao(base, agora):
    r = resumo_do_caso("ch-301", base, agora)
    assert r["grupo_ids"] == ["ch-301", "ch-302", "ch-601"]
    assert (r["contas"], r["chamados"]) == (7, 3)
    assert r["afeta_texto"] == "afeta 7 contas · 3 chamados"
    assert r["valor"] == 2400 + 1350 + 980 and r["valor_origem"] == "soma dos 3 chamados do grupo"
    assert r["valor_texto"] == "R$ 4.730 em risco (soma dos 3 chamados do grupo)" and r["em_risco"] is True
    assert r["centro"] == "Operações"
    # qualquer chamado do grupo mostra o mesmo grupo
    assert {k: v for k, v in resumo_do_caso("ch-302", base, agora).items() if k != "chamado_id"} == {
        k: v for k, v in r.items() if k != "chamado_id"
    }


def test_resumo_cenario_4_usa_o_valor_do_saque(base, agora):
    r = resumo_do_caso("ch-401", base, agora)
    assert r["valor"] == 4200 and r["valor_origem"] == "saque em espera"
    assert r["valor_texto"] == "R$ 4.200 em risco (saque em espera)" and r["em_risco"] is True
    assert r["chamados"] == 1 and r["afeta_texto"].endswith("· 1 chamado")


def test_resumo_cenarios_1_e_2_contam_compradores_da_causa(base, agora):
    assert resumo_do_caso("ch-101", base, agora)["afeta_texto"] == "afeta 5 contas · 3 chamados"
    assert resumo_do_caso("ch-201", base, agora)["afeta_texto"] == "afeta 6 contas · 2 chamados"


def test_resumo_chamado_comum_singular_e_sem_valor(base, agora):
    r = resumo_do_caso("ch-701", base, agora)
    assert r["afeta_texto"] == "afeta 1 conta · 1 chamado"
    assert r["valor"] == 0 and r["valor_texto"] == "nenhum valor envolvido"


def test_resumo_nao_sugere_decisao(base, agora):
    from sentinela.core.injecao import normalizar

    proibidas = ("aprov", "negar", "negue", "sugerimos", "recomend", "bloque", "liberar", "culpad")
    for cid in base.chamados:
        texto = normalizar(" ".join(str(v) for v in resumo_do_caso(cid, base, agora).values()))
        assert not any(p in texto for p in proibidas), cid


def test_resumo_id_inexistente(base, agora):
    with pytest.raises(KeyError):
        resumo_do_caso("ch-999", base, agora)


def test_resumo_aceita_analise_pronta(base, agora):
    from sentinela.core.caso import analisar

    assert resumo_do_caso("ch-301", base, agora, analise=analisar(base, agora)) == resumo_do_caso("ch-301", base, agora)


# ---------------------------------------------------------------- grupos_dos_chamados (fila agrupada na UI)
def test_grupos_dos_chamados_bate_com_a_rota(base, agora):
    g = grupos_dos_chamados(base, agora)
    assert g["aviso"] == AVISO
    assert set(g["grupos"]) == set(base.chamados)
    for cid, info in g["grupos"].items():
        caso = montar_caso(cid, base, agora)
        assert info["grupo_ids"] == caso["rota"]["grupo_ids"]
        assert info["aberto_em"] == caso["chamado"]["aberto_em"]


# ---------------------------------------------------------------- revisão: "em risco" só com sinal de segurança
@pytest.mark.parametrize("cid,texto", [
    ("ch-303", "R$ 249 envolvidos (valor do chamado)"),
    ("ch-501", "R$ 197 envolvidos (valor do chamado)"),
    ("ch-101", "R$ 891 envolvidos (soma dos 3 chamados do grupo)"),
])
def test_resumo_sem_sinal_de_seguranca_diz_envolvidos(base, agora, cid, texto):
    r = resumo_do_caso(cid, base, agora)
    assert r["valor_texto"] == texto and r["em_risco"] is False
    assert "em risco" not in r["valor_texto"]


@pytest.mark.parametrize("cid", ["ch-301", "ch-401"])
def test_resumo_com_sinal_de_seguranca_diz_em_risco(base, agora, cid):
    r = resumo_do_caso(cid, base, agora)
    assert r["em_risco"] is True and " em risco (" in r["valor_texto"]


# ---------------------------------------------------------------- revisão: alertas do grupo
def test_grupos_dos_chamados_trazem_flags_de_alerta(base, agora):
    g = grupos_dos_chamados(base, agora)["grupos"]
    for cid, info in g.items():
        caso = montar_caso(cid, base, agora)
        assert info["tem_alerta_injecao"] is bool(caso["alertas_injecao"]), cid
        assert info["tem_alerta_saque"] is (
            isinstance(caso["alerta_seguranca"], dict) and caso["alerta_seguranca"]["tipo"] == "saque_em_espera"
        ), cid
    assert g["ch-601"]["tem_alerta_injecao"] and not g["ch-301"]["tem_alerta_injecao"]
    assert g["ch-401"]["tem_alerta_saque"]


def test_resumo_do_lider_mostra_alerta_de_injecao_de_outro_membro(base, agora):
    alertas = resumo_do_caso("ch-301", base, agora)["alertas_grupo"]
    assert alertas == [{"tipo": "injecao", "ids": ["ch-601"],
                        "texto": "1 chamado deste grupo tem texto tentando instruir a IA: ch-601"}]


def test_resumo_com_saque_em_espera(base, agora):
    alertas = resumo_do_caso("ch-401", base, agora)["alertas_grupo"]
    assert alertas == [{"tipo": "saque", "ids": ["ch-401"],
                        "texto": "Este chamado tem saque em espera para revisão humana"}]


def test_resumo_sem_alerta_no_grupo(base, agora):
    assert resumo_do_caso("ch-101", base, agora)["alertas_grupo"] == []


def test_frase_alerta_grupo():
    from sentinela.core.caso import frase_alerta_grupo

    assert frase_alerta_grupo("injecao", ["ch-601"], 3) == "1 chamado deste grupo tem texto tentando instruir a IA: ch-601"
    assert frase_alerta_grupo("injecao", ["ch-1", "ch-2"], 3) == (
        "2 chamados deste grupo têm texto tentando instruir a IA: ch-1, ch-2")
    assert frase_alerta_grupo("saque", ["ch-9"], 2) == "1 chamado deste grupo tem saque em espera para revisão humana: ch-9"
    assert frase_alerta_grupo("injecao", ["ch-9"], 1) == "Este chamado tem texto tentando instruir a IA"
