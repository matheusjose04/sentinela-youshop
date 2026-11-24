"""Cenário 1: promessa falsa do creator (@lu.dicas, Curso Excel Pro, 'certificado reconhecido pelo MEC')."""
from sentinela.core.caso import montar_caso
from tests.conftest import textos_das_provas


def test_causa_creator_com_confianca_alta(base, agora):
    caso = montar_caso("ch-101", base, agora)
    assert caso["causa"]["tipo"] == "creator"
    assert caso["causa"]["confianca"] == "alta"
    assert caso["causa"]["descricao"].startswith("Causa provável")
    assert "@lu.dicas" in caso["causa"]["descricao"]


def test_provas_com_fonte_incluem_post_e_concentracao(base, agora):
    provas = montar_caso("ch-101", base, agora)["causa"]["provas"]
    assert all(p["fonte"] for p in provas)
    textos = textos_das_provas(provas)
    assert "certificado reconhecido pelo MEC" in textos
    assert "5 de 5" in textos and "@lu.dicas" in textos
    assert any("post" in p["fonte"] for p in provas)


def test_centro_creator_sem_alerta(base, agora):
    caso = montar_caso("ch-101", base, agora)
    assert caso["rota"]["centro"] == "Creator"
    assert caso["rota"]["motivo"]
    assert caso["alerta_seguranca"] == "nenhum"


def test_chamados_agrupados(base, agora):
    rota = montar_caso("ch-102", base, agora)["rota"]
    assert rota["grupo_ids"] == ["ch-101", "ch-102", "ch-103"]
    assert rota["grupo_texto"] == "3 chamados com a mesma causa"
