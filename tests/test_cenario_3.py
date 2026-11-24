"""Cenário 3: rede de fraude de comissão (@promo.top, @ofertaja, @achadinhos)."""
from sentinela.core.caso import grafo_do_chamado, montar_caso
from tests.conftest import textos_das_provas


def test_causa_fraude_alta(base, agora):
    causa = montar_caso("ch-301", base, agora)["causa"]
    assert causa["tipo"] == "fraude"
    assert causa["confianca"] == "alta"
    textos = textos_das_provas(causa["provas"])
    for perfil in ("@promo.top", "@ofertaja", "@achadinhos"):
        assert perfil in textos
    assert "@cupom.fake" in textos
    assert "próprio link" in textos


def test_centro_operacoes_e_alerta(base, agora):
    caso = montar_caso("ch-301", base, agora)
    assert caso["rota"]["centro"] == "Operações"
    assert caso["alerta_seguranca"] != "nenhum"
    assert caso["alerta_seguranca"]["tipo"] == "rede_suspeita"
    assert caso["alerta_seguranca"]["mensagem"].startswith("Sinais de contas ligadas no grafo")
    assert "pagamento" not in caso["alerta_seguranca"]["mensagem"].lower()


def test_distancia_ate_fraude(base, agora):
    dist = montar_caso("ch-301", base, agora)["distancia_fraude"]
    assert dist["ligacoes"] == 3
    assert dist["texto"] == "a 3 ligações de uma fraude confirmada"
    assert dist["caminho"][-1].startswith("@cupom.fake")


def test_prioridade_alta(base, agora):
    for cid in ("ch-301", "ch-302"):
        assert montar_caso(cid, base, agora)["score"]["faixa"] == "alta"


def test_componente_grande(base, agora):
    g = grafo_do_chamado("ch-301", base, agora)
    contas = [v for v in g["vertices"] if v["tipo"] in ("creator", "comprador")]
    assert len(contas) >= 6
    assert any(v["fraude_confirmada"] for v in g["vertices"])
    assert g["caminho_fraude"][0] == "ch-301"


def test_agrupamento_com_mesma_causa(base, agora):
    rota = montar_caso("ch-301", base, agora)["rota"]
    assert rota["grupo_ids"] == ["ch-301", "ch-302", "ch-601"]
    assert rota["grupo_texto"] == "3 chamados com a mesma causa"


# ---------------------------------------------------------------- regressão (revisão 1): falso positivo
def test_comprador_comum_do_produto_da_rede_nao_vira_suspeito(base, agora):
    """cp-33 só comprou o Fone Bluetooth Z: produto não liga contas no grupo de segurança."""
    caso = montar_caso("ch-303", base, agora)
    assert caso["causa"]["tipo"] == "comum"
    assert caso["rota"]["centro"] == "Comprador"
    assert caso["alerta_seguranca"] == "nenhum"
    assert caso["distancia_fraude"]["ligacoes"] is None
    parcelas = {p["nome"]: p["pontos"] for p in caso["score"]["parcelas"]}
    assert parcelas["segurança"] == 0 and parcelas["grupo"] == 0
    assert caso["rota"]["grupo_ids"] == ["ch-303"]
    assert caso["score"]["faixa"] == "baixa"


def test_cenarios_1_e_2_pontuam_pelo_grupo_da_causa(base, agora):
    """O grupo de segurança do ch-101 é só o comprador, mas a causa afeta 5 compradores."""
    for cid, faixa in [("ch-101", "média"), ("ch-201", "média"), ("ch-303", "baixa")]:
        assert montar_caso(cid, base, agora)["score"]["faixa"] == faixa, cid
    motivo = montar_caso("ch-101", base, agora)["score"]["motivo"]
    assert "5 compradores com a mesma causa ligados a @lu.dicas" in motivo
