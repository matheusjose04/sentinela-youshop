"""Grafo não-direcionado com lista de adjacência."""
from sentinela.core.grafo import PESOS, Grafo
from sentinela.core.modelos import Vertice


def _grafo_pequeno() -> Grafo:
    g = Grafo()
    for vid, tipo in [("a", "creator"), ("b", "celular"), ("c", "creator")]:
        g.adicionar_vertice(Vertice(id=vid, tipo=tipo, rotulo=vid))
    g.adicionar_aresta("a", "b", "usou celular")
    g.adicionar_aresta("c", "b", "usou celular")
    return g


def test_aresta_vale_nos_dois_sentidos():
    g = _grafo_pequeno()
    assert [v for v, _, _ in g.vizinhos("a")] == ["b"]
    assert sorted(v for v, _, _ in g.vizinhos("b")) == ["a", "c"]


def test_peso_vem_do_rotulo():
    g = _grafo_pequeno()
    assert g.vizinhos("a")[0] == ("b", "usou celular", 1)
    assert PESOS["comprou"] == 2 and PESOS["saca para"] == 1


def test_vertice_isolado_tem_lista_vazia():
    g = _grafo_pequeno()
    g.adicionar_vertice(Vertice(id="z", tipo="produto", rotulo="z"))
    assert g.vizinhos("z") == []


def test_aresta_com_vertice_inexistente_falha():
    g = _grafo_pequeno()
    try:
        g.adicionar_aresta("a", "nao-existe", "comprou")
    except KeyError:
        return
    raise AssertionError("deveria falhar")


def test_de_base_inclui_chamados(base):
    g = Grafo.de_base(base)
    assert "ch-401" in g.vertices
    assert ("ch-401", "abriu chamado", 2) in g.vizinhos("cr-rafa.fit")
