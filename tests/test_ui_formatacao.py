"""Helpers puros de formatação da tela (sem streamlit)."""
import string
from datetime import timedelta

import pytest

from sentinela.core.dados import AGORA_DEMO
from sentinela.core.injecao import FIM_DADO, INICIO_DADO, como_dado
from sentinela.ui.formatacao import agora_simulado, cor_badge, escapar_md, linhas_score, texto_citado


# ---------------------------------------------------------------- texto_citado
def test_texto_citado_tira_os_delimitadores():
    citado = texto_citado(como_dado("Meu saque não caiu.\nSegunda linha."))
    assert citado == "Meu saque não caiu.\nSegunda linha."
    assert INICIO_DADO not in citado and FIM_DADO not in citado


def test_texto_citado_mantem_a_troca_de_sinais_do_core():
    assert texto_citado(como_dado("<b>oi</b>")) == "‹b›oi‹/b›"


def test_texto_citado_sem_delimitador_devolve_igual():
    assert texto_citado("texto solto") == "texto solto"
    assert texto_citado("") == ""


def test_texto_citado_nao_e_enganado_por_fechamento_falso():
    """Um 'fim de dado' escrito pelo usuário fica dentro do texto citado."""
    falso = f"antes\n{FIM_DADO} abc>>>\ndepois"
    citado = texto_citado(como_dado(falso))
    assert citado.startswith("antes") and citado.endswith("depois")


def test_texto_citado_aceita_dict_do_core():
    assert texto_citado({"citacao": como_dado("oi"), "origem": "dado de terceiros"}) == "oi"


# ---------------------------------------------------------------- escapar_md
def test_escapar_md_neutraliza_toda_pontuacao():
    bruto = "R$ 4.200 *negrito* [link](http://x) <i> :red[x] `code` # _a_ ~b~ | $x$"
    saida = escapar_md(bruto)
    i = 0
    while i < len(saida):
        c = saida[i]
        if c == "\\":
            i += 2  # barra + caractere escapado
            continue
        assert c not in string.punctuation, (c, saida)
        i += 1


def test_escapar_md_preserva_letras_e_acentos():
    assert escapar_md("Comprador Otávio L") == "Comprador Otávio L"
    assert escapar_md("R$ 10") == "R\\$ 10"


def test_escapar_md_tira_quebra_de_linha():
    assert "\n" not in escapar_md("a\nb")


# ---------------------------------------------------------------- cor_badge
@pytest.mark.parametrize("valor,cor", [("alta", "red"), ("média", "orange"), ("baixa", "blue")])
def test_cor_badge_prioridade(valor, cor):
    assert cor_badge(valor) == cor


@pytest.mark.parametrize("valor,cor", [("alta", "violet"), ("média", "blue"), ("baixa", "gray")])
def test_cor_badge_confianca(valor, cor):
    assert cor_badge(valor, "confianca") == cor


def test_cor_badge_desconhecido_e_cinza():
    assert cor_badge("???") == "gray"
    assert cor_badge("???", "confianca") == "gray"


# ---------------------------------------------------------------- agora_simulado
def test_agora_simulado():
    assert agora_simulado(0) == AGORA_DEMO
    assert agora_simulado(48) == AGORA_DEMO + timedelta(hours=48)


@pytest.mark.parametrize("horas", [-1, 73])
def test_agora_simulado_fora_da_faixa(horas):
    with pytest.raises(ValueError):
        agora_simulado(horas)


# ---------------------------------------------------------------- linhas_score
def test_linhas_score_mostra_pontos_e_maximo_na_ordem():
    parcelas = [
        {"nome": "segurança", "pontos": 40.0, "maximo": 40, "explicacao": "saque em espera"},
        {"nome": "dinheiro", "pontos": 21.0, "maximo": 25, "explicacao": "R$ 4.200 em risco"},
        {"nome": "grupo", "pontos": 5, "maximo": 20, "explicacao": "2 contas"},
        {"nome": "espera", "pontos": 0.1, "maximo": 15, "explicacao": "20 min"},
    ]
    assert linhas_score(parcelas) == [
        "segurança: 40 de 40 · saque em espera",
        "dinheiro: 21 de 25 · R$ 4.200 em risco",
        "grupo: 5 de 20 · 2 contas",
        "espera: 0,1 de 15 · 20 min",
    ]


def test_linhas_score_real(base, agora):
    from sentinela.core.caso import montar_caso

    linhas = linhas_score(montar_caso("ch-401", base, agora)["score"]["parcelas"])
    assert [linha.split(":")[0] for linha in linhas] == ["segurança", "dinheiro", "grupo", "espera"]


# ---------------------------------------------------------------- limpar_texto (revisão 1)
def test_limpar_texto_tira_controles_e_bidi():
    from sentinela.ui.formatacao import limpar_texto

    sujo = "a\u202eb\u200bc\x07\x1b[31m\nd\te\u2066f\u2069"
    assert limpar_texto(sujo) == "abc[31m\nd\tef"


def test_limpar_texto_mantem_texto_normal():
    from sentinela.ui.formatacao import limpar_texto

    assert limpar_texto("Comprador Otávio L. → @x") == "Comprador Otávio L. → @x"


# ---------------------------------------------------------------- nivel_seguro (revisão 1)
def test_nivel_seguro_so_aceita_lista_fixa():
    from sentinela.ui.formatacao import nivel_seguro

    for v in ("alta", "média", "baixa"):
        assert nivel_seguro(v) == v
    assert nivel_seguro("alta] :red[x") == "desconhecida"
    assert nivel_seguro("") == "desconhecida"


# ---------------------------------------------------------------- tooltip de origem do texto citado
from sentinela.ui.formatacao import (  # noqa: E402
    TOOLTIP_CLIENTE,
    TOOLTIP_CREATOR,
    TOOLTIP_FORA,
    tooltip_origem,
)


def test_tooltips_sao_as_frases_combinadas():
    assert TOOLTIP_CLIENTE == "texto escrito pelo cliente (tratado como dado)"
    assert TOOLTIP_CREATOR == "texto escrito pelo creator (tratado como dado)"
    assert TOOLTIP_FORA == "texto de fora (tratado como dado)"


@pytest.mark.parametrize("fonte,esperado", [
    ("cliente", TOOLTIP_CLIENTE),
    ("assunto do chamado", TOOLTIP_CLIENTE),
    ("texto do chamado", TOOLTIP_CLIENTE),
    ("post do creator (po-01)", TOOLTIP_CREATOR),
    ("histórico de reembolsos", TOOLTIP_FORA),
    ("eventos da conta (eventos_saque)", TOOLTIP_FORA),
    ("", TOOLTIP_FORA),
    ("post do creator <script>", TOOLTIP_CREATOR),  # só escolhe a constante; nada da fonte vai para o tooltip
])
def test_tooltip_por_fonte(fonte, esperado):
    assert tooltip_origem(fonte) == esperado
