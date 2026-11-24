"""Cenário 2: produto com problema (Kit Sérum X, 4 creators, 'chegou vazando')."""
from sentinela.core.caso import montar_caso
from tests.conftest import textos_das_provas


def test_causa_produto_alta(base, agora):
    causa = montar_caso("ch-201", base, agora)["causa"]
    assert causa["tipo"] == "produto"
    assert causa["confianca"] == "alta"
    assert "Kit Sérum X" in causa["descricao"]


def test_provas_mostram_quatro_creators_mesmo_motivo(base, agora):
    textos = textos_das_provas(montar_caso("ch-201", base, agora)["causa"]["provas"])
    assert "4 creators diferentes" in textos
    assert "produto defeituoso" in textos  # motivo estruturado
    assert "chegou vazando" in textos.lower()  # citação do que o comprador escreveu
    # O reembolso com outro motivo ("textura") não entra na conta do mesmo motivo.
    assert "6 reembolsos" in textos


def test_centro_produtor_sem_alerta(base, agora):
    caso = montar_caso("ch-201", base, agora)
    assert caso["rota"]["centro"] == "Produtor"
    assert caso["alerta_seguranca"] == "nenhum"


def test_agrupamento(base, agora):
    rota = montar_caso("ch-202", base, agora)["rota"]
    assert rota["grupo_ids"] == ["ch-201", "ch-202"]
    assert rota["grupo_texto"] == "2 chamados com a mesma causa"
