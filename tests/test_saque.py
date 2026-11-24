"""Proteção do saque: celular novo + chave Pix trocada + saque quase total na janela."""
from datetime import datetime, timedelta, timezone

from sentinela.core.injecao import normalizar
from sentinela.core.modelos import EventoSaque
from sentinela.core.saque import avaliar_saque, listar_alertas_saque

T0 = datetime(2026, 11, 20, 14, 20, tzinfo=timezone(timedelta(hours=-3)))


def _ev(tipo, minutos, valor=None, saldo=None, creator="cr-x"):
    return EventoSaque(
        id=f"{tipo}-{minutos}", creator_id=creator, tipo=tipo, em=T0 + timedelta(minutes=minutos), valor=valor, saldo=saldo
    )


def _padrao(saque_valor=4200, saldo=4200, min_pix=6, min_saque=12):
    return [
        _ev("login_celular_novo", 0),
        _ev("troca_chave_pix", min_pix),
        _ev("pedido_saque", min_saque, valor=saque_valor, saldo=saldo),
    ]


def test_padrao_completo_coloca_saque_em_espera():
    alerta = avaliar_saque("cr-x", _padrao())
    assert alerta is not None
    assert alerta.status == "em_espera"
    assert alerta.minutos == 12
    assert alerta.valor == 4200
    assert alerta.percentual_saldo == 1.0
    assert len(alerta.provas) == 3 and all(p.fonte for p in alerta.provas)


def test_nunca_fala_em_bloqueio():
    alerta = avaliar_saque("cr-x", _padrao())
    textos = [alerta.mensagem, *(p.texto for p in alerta.provas)]
    assert all("bloque" not in normalizar(t) for t in textos)
    assert "revisao humana" in normalizar(alerta.mensagem)


def test_saque_parcial_nao_alerta():
    assert avaliar_saque("cr-x", _padrao(saque_valor=2000, saldo=4200)) is None


def test_limite_de_90_por_cento():
    assert avaliar_saque("cr-x", _padrao(saque_valor=3780, saldo=4200)) is not None  # 90%
    assert avaliar_saque("cr-x", _padrao(saque_valor=3700, saldo=4200)) is None


def test_fora_da_janela_nao_alerta():
    assert avaliar_saque("cr-x", _padrao(min_pix=100, min_saque=200)) is None


def test_falta_um_sinal_nao_alerta():
    eventos = [e for e in _padrao() if e.tipo != "troca_chave_pix"]
    assert avaliar_saque("cr-x", eventos) is None


def test_ignora_eventos_de_outro_creator():
    eventos = _padrao()
    eventos[0] = _ev("login_celular_novo", 0, creator="cr-outro")
    assert avaliar_saque("cr-x", eventos) is None


def test_sinais_depois_do_saque_nao_contam():
    eventos = [
        _ev("pedido_saque", 0, valor=4200, saldo=4200),
        _ev("login_celular_novo", 3),
        _ev("troca_chave_pix", 5),
    ]
    assert avaliar_saque("cr-x", eventos) is None


def test_listar_alertas_da_base_so_rafa(base):
    alertas = listar_alertas_saque(base)
    assert [a.creator_id for a in alertas] == ["cr-rafa.fit"]


# ---------------------------------------------------------------- regressões (revisão 1)
def test_limite_exato_da_janela_de_30_min():
    assert avaliar_saque("cr-x", _padrao(min_pix=10, min_saque=30)) is not None  # 30 min exatos: alerta
    assert avaliar_saque("cr-x", _padrao(min_pix=10, min_saque=31)) is None  # 31 min: login ficou fora


def test_login_dentro_e_pix_fora_da_janela():
    eventos = [
        _ev("troca_chave_pix", 0),
        _ev("login_celular_novo", 20),
        _ev("pedido_saque", 40, valor=4200, saldo=4200),
    ]
    assert avaliar_saque("cr-x", eventos) is None


def test_eventos_fora_de_ordem():
    alerta = avaliar_saque("cr-x", list(reversed(_padrao())))
    assert alerta is not None and alerta.minutos == 12


def test_eventos_depois_de_agora_nao_contam(base):
    from datetime import datetime

    antes_do_saque = datetime(2026, 11, 20, 14, 30, tzinfo=timezone(timedelta(hours=-3)))
    assert listar_alertas_saque(base, antes_do_saque) == []
    assert len(listar_alertas_saque(base, antes_do_saque + timedelta(minutes=5))) == 1
