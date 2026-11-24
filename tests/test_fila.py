"""Fila de prioridade (heap): ordem, desempate, envelhecimento, limites e motivo."""
from datetime import datetime, timedelta, timezone

from sentinela.core.fila import ContextoScore, FilaPrioridade, calcular_score, faixa
from sentinela.core.modelos import AlertaSaque, Chamado

T0 = datetime(2026, 11, 20, 8, 0, tzinfo=timezone(timedelta(hours=-3)))
SEM_RISCO = ContextoScore()


def _ch(cid: str, aberto_em: datetime = T0, valor: float = 0.0) -> Chamado:
    return Chamado(id=cid, autor_id="x", tipo="acesso", assunto=cid, texto="", aberto_em=aberto_em, valor=valor)


def _alerta(valor: float = 4200) -> AlertaSaque:
    return AlertaSaque(
        creator_id="cr-x", status="em_espera", valor=valor, percentual_saldo=1.0, minutos=12, mensagem="m"
    )


def test_ordem_por_score():
    fila = FilaPrioridade()
    fila.adicionar(_ch("baixo"), SEM_RISCO)
    fila.adicionar(_ch("saque", valor=4200), ContextoScore(alerta_saque=_alerta()))
    fila.adicionar(_ch("grupo"), ContextoScore(contas_no_grupo=5))
    ordem = [ch.id for ch, _ in fila.ordenar(T0 + timedelta(minutes=10))]
    assert ordem == ["saque", "grupo", "baixo"]


def test_desempate_estavel_mais_antigo_primeiro_depois_ordem_de_chegada():
    agora = T0 + timedelta(hours=1)
    fila = FilaPrioridade()
    # Mesmo score: espera é igual para quem abriu no mesmo instante.
    fila.adicionar(_ch("b"), SEM_RISCO)
    fila.adicionar(_ch("a"), SEM_RISCO)
    fila.adicionar(_ch("velho", aberto_em=T0 - timedelta(seconds=1)), ContextoScore())
    ordem = [ch.id for ch, _ in fila.ordenar(agora)]
    assert ordem[0] == "velho"  # espera um tiquinho maior
    assert ordem[1:] == ["b", "a"]  # empate total: ordem de chegada (contador)


def test_envelhecimento_reordena_a_cada_ordenar():
    fila = FilaPrioridade()
    fila.adicionar(_ch("antigo", aberto_em=T0), SEM_RISCO)
    assert fila.ordenar(T0)[0][1].total == 0  # recém-aberto: score zero
    novo = _ch("novo", aberto_em=T0 + timedelta(hours=30), valor=1000)  # 5 pts de dinheiro
    fila.adicionar(novo, SEM_RISCO)
    ordem = [ch.id for ch, _ in fila.ordenar(T0 + timedelta(hours=30))]
    # Se o score do "antigo" fosse congelado na entrada (0), ele ficaria atrás.
    assert ordem == ["antigo", "novo"]


def test_espera_cresce_com_o_tempo():
    ch = _ch("x")
    s1 = calcular_score(ch, SEM_RISCO, T0 + timedelta(hours=2))
    s2 = calcular_score(ch, SEM_RISCO, T0 + timedelta(hours=20))
    assert s2.parcela("espera").pontos > s1.parcela("espera").pontos
    assert s2.total > s1.total


def test_limites_das_parcelas():
    s = calcular_score(
        _ch("max", valor=10**9),
        ContextoScore(alerta_saque=_alerta(10**9), fraude_no_grupo=True, compartilhamento=True, contas_no_grupo=999),
        T0 + timedelta(days=365),
    )
    assert s.parcela("segurança").pontos == 40
    assert s.parcela("dinheiro").pontos == 25
    assert s.parcela("grupo").pontos == 20
    assert s.parcela("espera").pontos == 15
    assert s.total == 100
    assert [p.maximo for p in s.parcelas] == [40, 25, 20, 15]


def test_limites_inferiores():
    # Chamado "do futuro" (relógio torto) e valor negativo não geram pontos negativos.
    s = calcular_score(_ch("min", aberto_em=T0 + timedelta(days=1), valor=-50), ContextoScore(contas_no_grupo=0), T0)
    assert all(p.pontos == 0 for p in s.parcelas)
    assert s.total == 0


def test_total_e_soma_das_parcelas():
    s = calcular_score(_ch("x", valor=2400), ContextoScore(fraude_no_grupo=True, contas_no_grupo=3), T0 + timedelta(hours=5))
    assert abs(s.total - sum(p.pontos for p in s.parcelas)) < 0.01


def test_motivo_uma_linha_nao_vazia():
    s = calcular_score(
        _ch("x", valor=4200), ContextoScore(alerta_saque=_alerta(), contas_no_grupo=3), T0 + timedelta(minutes=20)
    )
    assert s.motivo == "Sobe: saque de R$ 4.200 em 12 min + grupo de 3 contas no grafo"
    vazio = calcular_score(_ch("y"), SEM_RISCO, T0)
    assert vazio.motivo.startswith("Sobe: ") and len(vazio.motivo) > len("Sobe: ")
    assert "\n" not in vazio.motivo


def test_cada_parcela_tem_explicacao():
    s = calcular_score(_ch("x", valor=300), ContextoScore(contas_no_grupo=2), T0 + timedelta(hours=3))
    assert all(p.explicacao for p in s.parcelas)


def test_faixas():
    assert faixa(70) == "alta"
    assert faixa(30) == "média"
    assert faixa(5) == "baixa"


def test_grupo_usa_o_maior_entre_seguranca_e_causa():
    ctx = ContextoScore(contas_no_grupo=1, contas_da_causa=5, alvo_causa="@lu.dicas")
    s = calcular_score(_ch("x"), ctx, T0)
    assert s.parcela("grupo").pontos == 20
    assert "5 compradores com a mesma causa ligados a @lu.dicas" in s.motivo
    # Se o grupo de segurança for maior, vale ele.
    s2 = calcular_score(_ch("y"), ContextoScore(contas_no_grupo=4, contas_da_causa=2, alvo_causa="X"), T0)
    assert s2.parcela("grupo").pontos == 15 and "grupo de 4 contas no grafo" in s2.motivo
