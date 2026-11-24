"""Desenho do grafo (pyvis): destaques e rótulos seguros."""
import pytest

from sentinela.core.caso import grafo_do_chamado
from sentinela.core.modelos import TIPOS_VERTICE
from sentinela.ui.grafo_html import COR_FRAUDE, TIPO_VISUAL, html_do_grafo, montar_rede, rotulo_para_grafo

XSS = "</script><img src=x onerror=alert(1)>"
PERIGOSOS = "<>&\"'"


def _grafo_minimo(rotulo: str) -> dict:
    return {
        "chamado_id": "ch-1",
        "vertices": [
            {"id": "ch-1", "tipo": "chamado", "rotulo": "ch-1", "fraude_confirmada": False,
             "no_caminho_fraude": False, "fora_do_grupo": False},
            {"id": "cr-1", "tipo": "creator", "rotulo": rotulo, "fraude_confirmada": False,
             "no_caminho_fraude": False, "fora_do_grupo": False},
        ],
        "arestas": [{"origem": "cr-1", "destino": "ch-1", "rotulo": rotulo, "peso": 1, "no_caminho_fraude": False}],
        "caminho_fraude": [],
        "ligacoes_ate_fraude": None,
        "distancia_texto": "nenhuma fraude confirmada ligada a este chamado",
    }


# ---------------------------------------------------------------- visual por tipo
def test_tipo_visual_cobre_os_6_tipos():
    assert set(TIPO_VISUAL) == set(TIPOS_VERTICE)
    for tipo, vis in TIPO_VISUAL.items():
        assert {"cor", "forma", "icone", "nome"} <= set(vis), tipo
    assert len({v["cor"] for v in TIPO_VISUAL.values()}) == 6
    assert len({v["forma"] for v in TIPO_VISUAL.values()}) == 6


# ---------------------------------------------------------------- rotulo_para_grafo
def test_rotulo_para_grafo_escapa_e_trunca():
    r = rotulo_para_grafo(XSS + " " + "x" * 100)
    assert not any(c in r for c in PERIGOSOS)
    assert len(r) <= 40


def test_rotulo_para_grafo_mantem_rotulo_normal():
    assert rotulo_para_grafo("@promo.top") == "@promo.top"
    assert rotulo_para_grafo("Celular •7731 (Android)") == "Celular •7731 (Android)"


# ---------------------------------------------------------------- html
def test_rotulo_malicioso_nao_aparece_cru_no_html():
    html = html_do_grafo(_grafo_minimo(XSS))
    assert XSS not in html
    assert "<img" not in html
    assert "onerror=alert(1)>" not in html


def test_rede_usa_rotulo_seguro_em_label_e_title():
    rede = montar_rede(_grafo_minimo(XSS))
    for item in rede.nodes + rede.edges:
        for campo in ("label", "title"):
            assert not any(c in item[campo] for c in PERIGOSOS), (campo, item[campo])


def test_html_autocontido_e_physics_desliga():
    html = html_do_grafo(_grafo_minimo("@x"))
    assert "lib/bindings/utils.js" not in html
    assert "vis.Network" in html  # vis-network embutido (in_line)
    assert "stabilizationIterationsDone" in html
    assert "physics: false" in html


# ---------------------------------------------------------------- cenário 3 real
@pytest.fixture
def rede_301(base, agora):
    return montar_rede(grafo_do_chamado("ch-301", base, agora))


def _nos(rede):
    return {n["id"]: n for n in rede.nodes}


def test_cenario_3_fraude_com_borda_vermelha_grossa(rede_301):
    fraude = _nos(rede_301)["cr-cupom.fake"]
    assert fraude["color"]["border"] == COR_FRAUDE
    assert fraude["borderWidth"] >= 4
    assert "fraude confirmada" in fraude["title"]


def test_cenario_3_chamado_selecionado_maior(rede_301):
    nos = _nos(rede_301)
    assert all(nos["ch-301"]["size"] > n["size"] for i, n in nos.items() if i != "ch-301")


def test_cenario_3_componente_em_cor_cheia_e_produto_em_cinza(rede_301):
    nos = _nos(rede_301)
    assert nos["cr-promo.top"]["color"]["background"] == TIPO_VISUAL["creator"]["cor"]
    assert nos["cel-r1"]["color"]["background"] == TIPO_VISUAL["celular"]["cor"]
    assert nos["pd-fone"]["color"]["background"] != TIPO_VISUAL["produto"]["cor"]
    assert "fora do grupo" in nos["pd-fone"]["title"]


def test_cenario_3_caminho_ate_fraude_em_vermelho(base, agora, rede_301):
    caminho = grafo_do_chamado("ch-301", base, agora)["caminho_fraude"]
    pares = {frozenset(p) for p in zip(caminho, caminho[1:])}
    no_caminho = [e for e in rede_301.edges if frozenset((e["from"], e["to"])) in pares]
    fora = [e for e in rede_301.edges if frozenset((e["from"], e["to"])) not in pares]
    assert len(no_caminho) == len(caminho) - 1 == 3
    assert all(e["width"] == 4 and e["color"] == COR_FRAUDE for e in no_caminho)
    assert all(e["width"] < 4 and e["color"] != COR_FRAUDE for e in fora)


def test_cenario_3_arestas_rotuladas(rede_301):
    rotulos = {e["label"] for e in rede_301.edges}
    assert {"usou celular", "abriu chamado"} <= rotulos
    assert all(e["label"] for e in rede_301.edges)


def test_cenario_3_html_so_com_chave_pix_mascarada(base, agora):
    html = html_do_grafo(grafo_do_chamado("ch-301", base, agora))
    assert "r***@example.com" in html


# ---------------------------------------------------------------- endurecimento do HTML (revisão 1)
import re  # noqa: E402

CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:"


def test_html_sem_recurso_externo(base, agora):
    html = html_do_grafo(grafo_do_chamado("ch-301", base, agora))
    assert not re.search(r"""(src|href)\s*=\s*["']?\s*https?://""", html, re.IGNORECASE)
    assert "bootstrap" not in html.lower()
    assert "cdn.jsdelivr" not in html


def test_html_tem_csp_no_head(base, agora):
    html = html_do_grafo(grafo_do_chamado("ch-301", base, agora))
    cabeca = html.split("</head>")[0]
    assert f'<meta http-equiv="Content-Security-Policy" content="{CSP}">' in cabeca


def test_id_malicioso_nao_sai_do_script():
    """O tojson do Jinja escapa '<' como \u003c: um id com </script> não fecha o bloco de dados."""
    g = _grafo_minimo("@x")
    ruim = "</script><img src=x onerror=alert(1)>"
    g["vertices"][1]["id"] = ruim
    g["arestas"][0]["origem"] = ruim
    html = html_do_grafo(g)
    assert ruim not in html
    assert "<img" not in html
    normal = html_do_grafo(_grafo_minimo("@x"))  # o bundle do vis já tem um "<script" literal
    assert html.count("</script>") == normal.count("</script>")
    assert html.count("<script") == normal.count("<script")


def test_falha_alto_se_o_template_mudar(monkeypatch):
    from pyvis.network import Network

    monkeypatch.setattr(Network, "generate_html", lambda self, *a, **k: "<html><head></head><body></body></html>")
    with pytest.raises(RuntimeError):
        html_do_grafo(_grafo_minimo("@x"))


# ---------------------------------------------------------------- legibilidade (revisão de UX)
from sentinela.ui.grafo_html import LIMITE_LABEL, _OPCOES  # noqa: E402

LONGO = "Curso Completo de Fotografia Mobile Avançada"


def test_label_curto_e_title_com_rotulo_completo_e_seguro():
    rede = montar_rede(_grafo_minimo(LONGO + " <b>"))
    no = next(n for n in rede.nodes if n["id"] == "cr-1")
    assert LIMITE_LABEL == 18
    assert len(no["label"]) <= LIMITE_LABEL and no["label"].endswith("…")
    assert LONGO[:30] in no["title"]  # tooltip guarda o rótulo inteiro (até o limite seguro)
    assert not any(c in no["title"] + no["label"] for c in PERIGOSOS)


def test_label_curto_nao_corta_rotulo_que_cabe():
    rede = montar_rede(_grafo_minimo("@promo.top"))
    assert next(n for n in rede.nodes if n["id"] == "cr-1")["label"] == "@promo.top"


def test_fisica_espalha_para_os_rotulos_nao_se_sobreporem():
    fisica = _OPCOES["physics"]
    assert fisica["solver"] == "barnesHut"
    bh = fisica["barnesHut"]
    assert bh["gravitationalConstant"] <= -8000
    assert bh["springLength"] >= 150
    assert bh["avoidOverlap"] > 0
    assert _OPCOES["edges"]["font"]["size"] <= 10


def test_redesenha_e_ajusta_ao_abrir_o_expander():
    """Dentro de um expander fechado o iframe nasce com largura 0: no 1º resize com tamanho real, fit()."""
    html = html_do_grafo(_grafo_minimo("@x"))
    assert 'network.on("resize"' in html
    assert "network.getPositions()" in html and "network.moveTo(" in html  # enquadra pelas posições (o bbox do vis fica velho enquanto escondido)
    assert _OPCOES.get("autoResize", True) is True
    # o iframe escondido pode ter um tamanho provisório: reajusta a cada resize até a pessoa mexer no grafo
    assert "ajustadoComTamanho" not in html
    assert 'network.on("dragStart"' in html and 'network.on("zoom"' in html


def test_cenario_3_hubs_empurram_mais_e_produto_fica_longe(rede_301):
    """Vértices com muitas ligações (celular, chave Pix) repelem mais; o produto (só contexto) fica afastado."""
    nos = _nos(rede_301)
    assert nos["cel-r1"]["mass"] > nos["ch-302"]["mass"] >= 1
    mola = _OPCOES["physics"]["barnesHut"]["springLength"]
    ao_produto = [e for e in rede_301.edges if "pd-fone" in (e["from"], e["to"])]
    assert ao_produto and all(e["length"] > mola for e in ao_produto)
    assert all("length" not in e for e in rede_301.edges if "pd-fone" not in (e["from"], e["to"]))
