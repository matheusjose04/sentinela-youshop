"""Cenário 5: comprador com padrão de abuso (7 reembolsos/30 dias, 95% assistido)."""
from sentinela.core.caso import montar_caso
from sentinela.core.injecao import normalizar
from tests.conftest import textos_das_provas


def test_causa_padrao_de_abuso_com_confianca_media(base, agora):
    causa = montar_caso("ch-501", base, agora)["causa"]
    assert causa["tipo"] == "ma_fe_comprador"
    assert causa["confianca"] == "média"  # intenção não se prova só com dados
    assert causa["descricao"].startswith("Causa provável")


def test_provas_contam_so_janela_de_30_dias(base, agora):
    textos = textos_das_provas(montar_caso("ch-501", base, agora)["causa"]["provas"])
    assert "7 reembolsos nos últimos 30 dias" in textos  # o de setembro fica de fora
    assert "7 produtores diferentes" in textos
    assert "95%" in textos


def test_alerta_com_lembrete_do_direito_de_arrependimento(base, agora):
    alerta = montar_caso("ch-501", base, agora)["alerta_seguranca"]
    assert alerta["tipo"] == "padrao_de_abuso"
    lembrete = normalizar(alerta["lembrete"])
    assert "7 dias" in lembrete and "arrependimento" in lembrete
    assert "humano decide" in lembrete


def test_centro_comprador(base, agora):
    assert montar_caso("ch-501", base, agora)["rota"]["centro"] == "Comprador"


def test_nao_afirma_culpa(base, agora):
    caso = montar_caso("ch-501", base, agora)
    texto = normalizar(caso["causa"]["descricao"] + caso["alerta_seguranca"]["mensagem"])
    for palavra in ("culpado", "fraudador", "comprovad", "golpista"):
        assert palavra not in texto
