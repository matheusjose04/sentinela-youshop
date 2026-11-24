"""Algoritmos de grafo escritos à mão: BFS (componentes) e Dijkstra (distância até fraude)."""
from __future__ import annotations

import heapq
from collections import deque

from sentinela.core.grafo import Grafo


def bfs_componente(grafo: Grafo, origem: str, ignorar_tipos: frozenset[str] = frozenset()) -> set[str]:
    """Todos os vértices alcançáveis a partir de `origem` (o "grupo" no grafo).

    `ignorar_tipos`: tipos de vértice onde a busca NÃO entra (ex.: "produto", para que
    comprar ou divulgar o mesmo produto não ligue contas sem relação).

    Ideia: uma fila (deque) com a fronteira. Tiro o primeiro da fila, olho os vizinhos
    e enfileiro os que ainda não visitei. Cada vértice entra uma vez só: O(V + E).
    """
    visitados = {origem}
    fila: deque[str] = deque([origem])
    while fila:
        atual = fila.popleft()  # popleft = FIFO, por isso é "em largura"
        for vizinho, _, _ in grafo.vizinhos(atual):
            if vizinho not in visitados and grafo.vertices[vizinho].tipo not in ignorar_tipos:
                visitados.add(vizinho)  # marca ao enfileirar para não enfileirar duas vezes
                fila.append(vizinho)
    return visitados


def componentes_conexos(grafo: Grafo) -> list[set[str]]:
    """Particiona o grafo em grupos conectados: um BFS a partir de cada vértice ainda não visto."""
    vistos: set[str] = set()
    componentes: list[set[str]] = []
    for v in grafo.vertices:
        if v not in vistos:
            comp = bfs_componente(grafo, v)
            vistos |= comp
            componentes.append(comp)
    return componentes


def dijkstra(
    grafo: Grafo, origem: str, ignorar_tipos: frozenset[str] = frozenset()
) -> tuple[dict[str, float], dict[str, str]]:
    """Menor distância ponderada de `origem` até cada vértice alcançável.

    Ideia: um heap guarda (distância, vértice) e sempre devolve o mais perto ainda não
    fechado. Ao fechar um vértice, tento "relaxar" os vizinhos: se passar por ele deixa
    o vizinho mais perto, atualizo e empurro a nova distância no heap.
    Lazy deletion: não removo a entrada velha do heap; quando ela sair, vejo que já é
    maior que a distância conhecida e ignoro. Funciona porque os pesos são positivos.
    Retorna (dist, anterior); `anterior` permite reconstruir o caminho.
    """
    dist: dict[str, float] = {origem: 0}
    anterior: dict[str, str] = {}
    heap: list[tuple[float, str]] = [(0, origem)]
    while heap:
        d, atual = heapq.heappop(heap)
        if d > dist[atual]:
            continue  # entrada velha (lazy deletion)
        for vizinho, _, peso in grafo.vizinhos(atual):
            if grafo.vertices[vizinho].tipo in ignorar_tipos:
                continue
            nova = d + peso
            if nova < dist.get(vizinho, float("inf")):
                dist[vizinho] = nova
                anterior[vizinho] = atual
                heapq.heappush(heap, (nova, vizinho))
    return dist, anterior


def reconstruir_caminho(anterior: dict[str, str], origem: str, destino: str) -> list[str]:
    """Volta de `destino` até `origem` seguindo `anterior` e inverte."""
    caminho = [destino]
    while caminho[-1] != origem:
        caminho.append(anterior[caminho[-1]])
    caminho.reverse()
    return caminho


def caminho_ate_fraude(
    grafo: Grafo, origem: str, ignorar_tipos: frozenset[str] = frozenset()
) -> tuple[list[str], int] | None:
    """Caminho mais leve até o vértice de fraude confirmada mais próximo.

    Retorna (caminho, nº de ligações) ou None se nenhuma fraude é alcançável.
    Atenção: "N ligações" é o número de arestas do caminho de MENOR PESO (ligações mais
    fortes, ex. celular/Pix), não o caminho com menos arestas. Um caminho de 2 ligações
    fracas (comprou + comprou = 4) perde para 3 ligações fortes (1 + 1 + 1 = 3).
    """
    dist, anterior = dijkstra(grafo, origem, ignorar_tipos)
    fraudes = [v for v in dist if grafo.vertices[v].fraude_confirmada]
    if not fraudes:
        return None
    # Mais próxima pelo peso; empate desfeito pelo id para ser determinístico.
    alvo = min(fraudes, key=lambda v: (dist[v], v))
    caminho = reconstruir_caminho(anterior, origem, alvo)
    return caminho, len(caminho) - 1
