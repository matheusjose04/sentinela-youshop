"""Ações do atendente na sessão (puro, imutável)."""
from datetime import datetime, timedelta, timezone

import pytest

from sentinela.ui.acoes import CENTROS, centros_para_devolver, registrar_acao, status_do_chamado

EM = datetime(2026, 11, 20, 15, 0, tzinfo=timezone(timedelta(hours=-3)))


def test_centros():
    assert CENTROS == ("Comprador", "Produtor", "Creator", "Operações")


def test_centros_para_devolver_tira_o_atual():
    assert centros_para_devolver("Operações") == ("Comprador", "Produtor", "Creator")
    assert centros_para_devolver("Comprador") == ("Produtor", "Creator", "Operações")
    assert centros_para_devolver("???") == CENTROS


def test_registrar_e_imutavel():
    antes: list = []
    depois = registrar_acao(antes, tipo="resolvido", chamado_id="ch-701", centro="Comprador", em=EM)
    assert antes == []
    assert depois is not antes
    assert depois == [
        {
            "tipo": "resolvido",
            "chamado_id": "ch-701",
            "centro": "Comprador",
            "destino": None,
            "observacao": "",
            "em": EM.isoformat(),
        }
    ]
    mais = registrar_acao(depois, tipo="encaminhado", chamado_id="ch-701", centro="Comprador", em=EM, observacao="x")
    assert len(depois) == 1 and len(mais) == 2


def test_devolver_guarda_destino_e_motivo():
    acoes = registrar_acao(
        [], tipo="devolvido", chamado_id="ch-301", centro="Operações", destino="Produtor",
        observacao="  é do produto  ", em=EM,
    )
    assert acoes[0]["destino"] == "Produtor"
    assert acoes[0]["observacao"] == "é do produto"


def test_devolver_exige_outro_centro():
    with pytest.raises(ValueError):
        registrar_acao([], tipo="devolvido", chamado_id="ch-301", centro="Operações", destino="Operações", em=EM)
    with pytest.raises(ValueError):
        registrar_acao([], tipo="devolvido", chamado_id="ch-301", centro="Operações", destino=None, em=EM)


def test_tipo_desconhecido_recusado():
    with pytest.raises(ValueError):
        registrar_acao([], tipo="aprovado", chamado_id="ch-301", centro="Operações", em=EM)


def test_observacao_truncada():
    acoes = registrar_acao([], tipo="encaminhado", chamado_id="c", centro="Comprador", em=EM, observacao="a" * 5000)
    assert len(acoes[0]["observacao"]) <= 500


def test_status_do_chamado():
    assert status_do_chamado([], "ch-1") == "aberto"
    acoes = registrar_acao([], tipo="encaminhado", chamado_id="ch-1", centro="Comprador", em=EM)
    assert status_do_chamado(acoes, "ch-1") == "encaminhado"
    acoes = registrar_acao(acoes, tipo="devolvido", chamado_id="ch-1", centro="Comprador", destino="Creator", em=EM)
    assert status_do_chamado(acoes, "ch-1") == "devolvido para Creator"
    acoes = registrar_acao(acoes, tipo="resolvido", chamado_id="ch-2", centro="Comprador", em=EM)
    assert status_do_chamado(acoes, "ch-1") == "devolvido para Creator"
    assert status_do_chamado(acoes, "ch-2") == "resolvido"


def test_guarda_so_as_ultimas_200():
    from sentinela.ui.acoes import LIMITE_ACOES

    assert LIMITE_ACOES == 200
    acoes: list = []
    for i in range(205):
        acoes = registrar_acao(acoes, tipo="resolvido", chamado_id=f"ch-{i}", centro="Comprador", em=EM)
    assert len(acoes) == 200
    assert acoes[0]["chamado_id"] == "ch-5" and acoes[-1]["chamado_id"] == "ch-204"
