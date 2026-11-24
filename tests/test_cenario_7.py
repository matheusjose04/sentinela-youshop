"""Cenário 7: chamado comum (acesso perdido): prioridade baixa que sobe com o tempo."""
from datetime import timedelta

from sentinela.core.caso import montar_caso


def test_causa_comum(base, agora):
    caso = montar_caso("ch-701", base, agora)
    assert caso["causa"]["tipo"] == "comum"
    assert caso["causa"]["confianca"] == "média"
    assert "acesso" in caso["causa"]["descricao"]


def test_centro_comprador_sem_alerta(base, agora):
    caso = montar_caso("ch-701", base, agora)
    assert caso["rota"]["centro"] == "Comprador"
    assert caso["alerta_seguranca"] == "nenhum"
    assert caso["distancia_fraude"]["ligacoes"] is None


def test_prioridade_baixa_que_sobe_com_o_tempo(base, agora):
    agora_score = montar_caso("ch-701", base, agora)["score"]
    depois = montar_caso("ch-701", base, agora + timedelta(hours=12))["score"]
    assert agora_score["faixa"] == "baixa"
    assert depois["total"] > agora_score["total"]
    espera = {p["nome"]: p for p in depois["parcelas"]}["espera"]
    assert 0 < espera["pontos"] <= 15


def test_cpf_do_texto_aparece_mascarado(base, agora):
    dado = montar_caso("ch-701", base, agora)["chamado"]["texto"]["citacao"]
    assert "123.456.789-00" not in dado
    assert "***.456.789-**" in dado
    assert "ana.p@" not in dado


def test_saida_inteira_do_caso_sem_cpf_nem_email(base, agora):
    import json

    saida = json.dumps(montar_caso("ch-701", base, agora), ensure_ascii=False)
    assert "123.456.789-00" not in saida
    assert "ana.p@" not in saida
