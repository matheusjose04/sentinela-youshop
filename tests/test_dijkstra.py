"""Dijkstra: menor caminho ponderado e distância até fraude confirmada."""
from sentinela.core.algoritmos import caminho_ate_fraude, dijkstra, reconstruir_caminho
from sentinela.core.grafo import Grafo
from sentinela.core.modelos import Vertice


def _g() -> Grafo:
    # ch --abriu(2)-- a --usou celular(1)-- cel --usou celular(1)-- f (fraude)
    #                 a --comprou(2)-- p --comprou(2)-- f
    g = Grafo()
    g.adicionar_vertice(Vertice(id="ch", tipo="chamado", rotulo="ch"))
    g.adicionar_vertice(Vertice(id="a", tipo="creator", rotulo="a"))
    g.adicionar_vertice(Vertice(id="cel", tipo="celular", rotulo="cel"))
    g.adicionar_vertice(Vertice(id="p", tipo="produto", rotulo="p"))
    g.adicionar_vertice(Vertice(id="f", tipo="creator", rotulo="f", fraude_confirmada=True))
    g.adicionar_vertice(Vertice(id="longe", tipo="creator", rotulo="longe"))
    g.adicionar_aresta("a", "ch", "abriu chamado")
    g.adicionar_aresta("a", "cel", "usou celular")
    g.adicionar_aresta("f", "cel", "usou celular")
    g.adicionar_aresta("a", "p", "comprou")
    g.adicionar_aresta("f", "p", "comprou")
    return g


def test_dijkstra_distancias():
    dist, _ = dijkstra(_g(), "ch")
    assert dist["ch"] == 0
    assert dist["a"] == 2
    assert dist["cel"] == 3
    assert dist["f"] == 4  # pelo celular (1+1), não pelo produto (2+2)
    assert "longe" not in dist  # inalcançável


def test_reconstruir_caminho_mais_leve():
    _, anterior = dijkstra(_g(), "ch")
    assert reconstruir_caminho(anterior, "ch", "f") == ["ch", "a", "cel", "f"]


def test_caminho_ate_fraude_conta_ligacoes():
    caminho, ligacoes = caminho_ate_fraude(_g(), "ch")
    assert caminho == ["ch", "a", "cel", "f"]
    assert ligacoes == 3


def test_sem_fraude_alcancavel_retorna_none():
    assert caminho_ate_fraude(_g(), "longe") is None


def test_origem_ja_e_fraude():
    assert caminho_ate_fraude(_g(), "f") == (["f"], 0)


def test_cenario_3_distancia_ate_fraude(base):
    caminho, ligacoes = caminho_ate_fraude(Grafo.de_base(base), "ch-301")
    assert caminho[0] == "ch-301" and caminho[-1] == "cr-cupom.fake"
    assert ligacoes == 3


# ---------------------------------------------------------------- regressões (revisão 1)
import sentinela.core.algoritmos as algoritmos  # noqa: E402


def _dois_caminhos() -> Grafo:
    # Caminho A: o --comprou(2)-- p --comprou(2)-- f        -> 2 ligações, peso 4
    # Caminho B: o --usou(1)-- cel --usou(1)-- m --saca(1)-- f -> 3 ligações, peso 3
    g = Grafo()
    for vid, tipo in [("o", "creator"), ("p", "creator"), ("cel", "celular"), ("m", "creator")]:
        g.adicionar_vertice(Vertice(id=vid, tipo=tipo, rotulo=vid))
    g.adicionar_vertice(Vertice(id="f", tipo="creator", rotulo="f", fraude_confirmada=True))
    g.adicionar_aresta("o", "p", "comprou")
    g.adicionar_aresta("p", "f", "comprou")
    g.adicionar_aresta("o", "cel", "usou celular")
    g.adicionar_aresta("cel", "m", "usou celular")
    g.adicionar_aresta("m", "f", "saca para")
    return g


def test_distancia_exibida_e_do_caminho_de_menor_peso_nao_de_menos_arestas():
    """"N ligações" = arestas do caminho MAIS LEVE (ligações mais fortes), não o caminho mais curto em arestas."""
    caminho, ligacoes = caminho_ate_fraude(_dois_caminhos(), "o")
    assert caminho == ["o", "cel", "m", "f"]
    assert ligacoes == 3


def test_lazy_deletion_ignora_entrada_velha(monkeypatch):
    # s --comprou(2)-- x --comprou(2)-- a   (a entra no heap com 4)
    # s --usou(1)-- y --usou(1)-- z --usou(1)-- a   (depois melhora para 3)
    g = Grafo()
    for vid in "sxyza":
        g.adicionar_vertice(Vertice(id=vid, tipo="creator", rotulo=vid))
    g.adicionar_aresta("s", "x", "comprou")
    g.adicionar_aresta("x", "a", "comprou")
    g.adicionar_aresta("s", "y", "usou celular")
    g.adicionar_aresta("y", "z", "usou celular")
    g.adicionar_aresta("z", "a", "usou celular")
    pops = []
    original = algoritmos.heapq.heappop
    monkeypatch.setattr(algoritmos.heapq, "heappop", lambda h: pops.append(1) or original(h))
    dist, anterior = dijkstra(g, "s")
    assert dist["a"] == 3 and anterior["a"] == "z"
    assert len(pops) == len(g.vertices) + 1  # uma entrada velha (a, 4) saiu e foi ignorada


def test_dijkstra_respeita_tipos_ignorados():
    g = _dois_caminhos()
    dist, _ = dijkstra(g, "o", ignorar_tipos=frozenset({"celular"}))
    assert dist["f"] == 4  # sem atravessar o celular, só sobra o caminho pesado
    assert "cel" not in dist and dist["m"] == 5  # m só é alcançado depois de f
