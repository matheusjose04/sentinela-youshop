"""BFS: componentes conexos."""
from sentinela.core.algoritmos import bfs_componente, componentes_conexos
from sentinela.core.grafo import Grafo
from sentinela.core.modelos import Vertice


def _grafo(arestas, isolados=()):
    g = Grafo()
    nomes = {x for a, b in arestas for x in (a, b)} | set(isolados)
    for n in sorted(nomes):
        g.adicionar_vertice(Vertice(id=n, tipo="creator", rotulo=n))
    for a, b in arestas:
        g.adicionar_aresta(a, b, "usou celular")
    return g


def test_bfs_acha_o_componente_inteiro():
    g = _grafo([("a", "b"), ("b", "c"), ("x", "y")])
    assert bfs_componente(g, "a") == {"a", "b", "c"}
    assert bfs_componente(g, "y") == {"x", "y"}


def test_bfs_com_ciclo_nao_repete():
    g = _grafo([("a", "b"), ("b", "c"), ("c", "a")])
    assert bfs_componente(g, "b") == {"a", "b", "c"}


def test_bfs_vertice_isolado():
    g = _grafo([("a", "b")], isolados=["z"])
    assert bfs_componente(g, "z") == {"z"}


def test_componentes_conexos_particiona():
    g = _grafo([("a", "b"), ("c", "d"), ("d", "e")], isolados=["z"])
    comps = componentes_conexos(g)
    assert sorted(sorted(c) for c in comps) == [["a", "b"], ["c", "d", "e"], ["z"]]
    # Toda aresta fica dentro de um componente só.
    todos = [v for c in comps for v in c]
    assert len(todos) == len(set(todos)) == len(g.vertices)


def test_rede_de_fraude_e_um_componente_so(base):
    g = Grafo.de_base(base)
    comp = bfs_componente(g, "ch-301")
    for v in ["cr-promo.top", "cr-ofertaja", "cr-achadinhos", "cel-r1", "pix-r1", "cr-cupom.fake"]:
        assert v in comp
    # Cenário 1 não está ligado à rede.
    assert "cr-lu.dicas" not in comp


# ---------------------------------------------------------------- regressões (revisão 1)
def _com_produto() -> Grafo:
    g = Grafo()
    g.adicionar_vertice(Vertice(id="a", tipo="comprador", rotulo="a"))
    g.adicionar_vertice(Vertice(id="b", tipo="creator", rotulo="b"))
    g.adicionar_vertice(Vertice(id="p", tipo="produto", rotulo="p"))
    g.adicionar_aresta("a", "p", "comprou")
    g.adicionar_aresta("b", "p", "divulga")
    return g


def test_bfs_nao_atravessa_tipos_ignorados():
    g = _com_produto()
    assert bfs_componente(g, "a") == {"a", "p", "b"}
    # Comprar o mesmo produto não liga ninguém: o grupo de segurança não passa por produto.
    assert bfs_componente(g, "a", ignorar_tipos=frozenset({"produto"})) == {"a"}


def test_grupo_de_seguranca_do_cenario_1_nao_inclui_outros_compradores(base):
    from sentinela.core.grafo import NAO_ATRAVESSA

    g = Grafo.de_base(base)
    assert bfs_componente(g, "ch-101", NAO_ATRAVESSA) == {"ch-101", "cp-11"}
    # A rede do cenário 3 continua ligada por celular e chave Pix, sem precisar do produto.
    rede = bfs_componente(g, "ch-301", NAO_ATRAVESSA)
    assert {"cr-promo.top", "cr-ofertaja", "cr-achadinhos", "cr-cupom.fake", "cr-vitrine.express"} <= rede
    assert "pd-fone" not in rede
