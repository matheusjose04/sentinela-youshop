"""Cenário 4: conta invadida (@rafa.fit) com saque total de R$ 4.200 em 12 minutos."""
from datetime import timedelta

from sentinela.core.caso import montar_caso, montar_fila


def test_causa_conta_invadida_alta(base, agora):
    causa = montar_caso("ch-401", base, agora)["causa"]
    assert causa["tipo"] == "conta_invadida"
    assert causa["confianca"] == "alta"
    assert causa["descricao"].startswith("Causa provável")


def test_saque_em_espera(base, agora):
    alerta = montar_caso("ch-401", base, agora)["alerta_seguranca"]
    assert alerta["tipo"] == "saque_em_espera"
    assert alerta["status"] == "em_espera"
    assert "R$ 4.200" in alerta["mensagem"] and "12 min" in alerta["mensagem"]
    assert "revisão humana" in alerta["mensagem"]


def test_centro_operacoes(base, agora):
    assert montar_caso("ch-401", base, agora)["rota"]["centro"] == "Operações"


def test_topo_da_fila(base, agora):
    fila = montar_fila(base, agora)["itens"]
    assert fila[0]["id"] == "ch-401"
    assert fila[0]["faixa"] == "alta"
    assert fila[0]["motivo"].startswith("Sobe: saque de R$ 4.200 em 12 min")


def test_topo_da_fila_mesmo_horas_depois(base, agora):
    assert montar_fila(base, agora + timedelta(hours=6))["itens"][0]["id"] == "ch-401"
