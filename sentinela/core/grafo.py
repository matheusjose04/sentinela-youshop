"""Grafo de ligações como lista de adjacência (dict de listas), não-direcionado."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sentinela.core.modelos import Vertice

if TYPE_CHECKING:
    from sentinela.core.dados import Base

# Peso de cada tipo de ligação para o Dijkstra: quanto MENOR, mais forte a ligação.
# Dividir celular ou chave Pix é quase "ser a mesma pessoa" (1); comprar/divulgar é mais fraco (2).
PESOS: dict[str, int] = {
    "usou celular": 1,
    "saca para": 1,
    "comprou": 2,
    "divulga": 2,
    "abriu chamado": 2,
}

# O "grupo de segurança" não atravessa produto: comprar ou divulgar o mesmo produto não
# liga duas contas. Contas se ligam por celular, chave Pix ("saca para") e chamados.
NAO_ATRAVESSA: frozenset[str] = frozenset({"produto"})

Vizinho = tuple[str, str, int]  # (id do vizinho, rótulo da aresta, peso)


class Grafo:
    """adj[v] = lista de (vizinho, rótulo, peso). Cada aresta é guardada nos dois sentidos."""

    def __init__(self) -> None:
        self.vertices: dict[str, Vertice] = {}
        self.adj: dict[str, list[Vizinho]] = {}

    def adicionar_vertice(self, v: Vertice) -> None:
        self.vertices[v.id] = v
        self.adj.setdefault(v.id, [])

    def adicionar_aresta(self, a: str, b: str, rotulo: str) -> None:
        if a not in self.adj or b not in self.adj:
            raise KeyError(f"aresta {a!r}-{b!r} referencia vértice inexistente")
        peso = PESOS[rotulo]
        # Não-direcionado: a ligação vale para os dois lados.
        self.adj[a].append((b, rotulo, peso))
        self.adj[b].append((a, rotulo, peso))

    def vizinhos(self, v: str) -> list[Vizinho]:
        return self.adj[v]

    @classmethod
    def de_base(cls, base: Base) -> Grafo:
        """Monta o grafo a partir da base (vértices, arestas e chamados já validados)."""
        g = cls()
        for v in base.vertices.values():
            g.adicionar_vertice(v)
        for a in base.arestas:
            g.adicionar_aresta(a.origem, a.destino, a.rotulo)
        return g
