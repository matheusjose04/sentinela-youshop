"""Desenho do grafo do chamado com pyvis (vis-network embutido no HTML).

Só DESENHA o que `grafo_do_chamado` (core) já calculou: componente, caminho até a fraude
(Dijkstra) e produtos de contexto. Nenhum algoritmo de grafo roda aqui.

Segurança: todo rótulo passa por `rotulo_para_grafo` antes de ir para label/title,
porque o HTML vai para dentro de um iframe com JavaScript. O HTML final é autocontido
(sem CDN) e leva uma CSP que proíbe qualquer acesso à rede.
"""
from __future__ import annotations

import re
from typing import Any

from pyvis.network import Network

LIMITE_ROTULO = 40
COR_FRAUDE = "#d62728"
COR_ARESTA = "#9ca3af"
COR_FORA_DO_GRUPO = {"background": "#e5e7eb", "border": "#9ca3af"}
ALTURA_PX = 520

# Constantes do código (nenhum dado de fora): cor (hex, no grafo) · cor_st (cor do markdown do
# Streamlit, na legenda) · forma (vis-network) · icone (Material Symbols) · nome (para a pessoa).
TIPO_VISUAL: dict[str, dict[str, str]] = {
    "comprador": {"cor": "#1f77b4", "cor_st": "blue", "forma": "dot", "icone": "person", "nome": "comprador"},
    "creator": {"cor": "#9467bd", "cor_st": "violet", "forma": "diamond", "icone": "campaign", "nome": "creator"},
    "produto": {"cor": "#ff7f0e", "cor_st": "orange", "forma": "box", "icone": "inventory_2", "nome": "produto"},
    "celular": {"cor": "#2ca02c", "cor_st": "green", "forma": "triangle", "icone": "smartphone", "nome": "celular"},
    "chave_pix": {"cor": "#d4a017", "cor_st": "yellow", "forma": "hexagon", "icone": "key", "nome": "chave Pix"},
    "chamado": {"cor": "#0f766e", "cor_st": "primary", "forma": "star", "icone": "support_agent", "nome": "chamado"},
}

# Troca os 5 caracteres com significado em HTML por sósias Unicode (como o core faz com < >
# em `como_dado`): o rótulo continua legível no canvas e no tooltip, e nada vira tag.
_SEGURO = str.maketrans({"<": "‹", ">": "›", "&": "＆", '"': "”", "'": "’"})

# Depois que o layout estabiliza, a física desliga: o grafo para de "tremer" e fica onde está.
_JS_DESLIGA_FISICA = """network.once("stabilizationIterationsDone", function () {
                      network.setOptions({ physics: false });
                  });
                  """

# O iframe só roda o que está no próprio HTML: nada de rede, nada de recurso externo.
CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:"
_META_CSP = f'<meta http-equiv="Content-Security-Policy" content="{CSP}">'

# O template do pyvis carrega o Bootstrap do jsdelivr (só para o cartão em volta). O grafo não usa.
_RE_BOOTSTRAP = re.compile(
    r"<link\b[^>]*bootstrap[^>]*>\s*|<script\b[^>]*bootstrap[^>]*>\s*</script>\s*",
    re.IGNORECASE,
)

_OPCOES: dict[str, Any] = {
    "physics": {
        "enabled": True,
        "solver": "forceAtlas2Based",
        "forceAtlas2Based": {"gravitationalConstant": -60, "springLength": 110},
        "stabilization": {"enabled": True, "iterations": 400, "fit": True},
    },
    "interaction": {"hover": True, "tooltipDelay": 120, "navigationButtons": False},
    "edges": {"smooth": False, "font": {"size": 11, "align": "middle", "strokeWidth": 3}},
    "nodes": {"font": {"size": 13}},
}


def rotulo_para_grafo(texto: str) -> str:
    """Rótulo seguro para label/title: sem < > & " ' e com no máximo 40 caracteres."""
    texto = " ".join(str(texto).split()).translate(_SEGURO)
    return texto if len(texto) <= LIMITE_ROTULO else texto[: LIMITE_ROTULO - 1] + "…"


def _no(v: dict[str, Any], selecionado: str) -> dict[str, Any]:
    """Atributos vis-network de um vértice, já com os destaques."""
    vis = TIPO_VISUAL[v["tipo"]]
    notas = []
    cor = {"background": vis["cor"], "border": vis["cor"]}  # componente do chamado: cor cheia
    borda = 1
    if v["fora_do_grupo"]:
        cor = dict(COR_FORA_DO_GRUPO)
        notas.append("fora do grupo (produto só dá contexto)")
    if v["no_caminho_fraude"]:
        cor["border"], borda = COR_FRAUDE, 3
        notas.append("no caminho até a fraude")
    if v["fraude_confirmada"]:
        cor["border"], borda = COR_FRAUDE, 6
        notas.append("fraude confirmada")
    titulo = "\n".join([f"{vis['nome']}: {rotulo_para_grafo(v['rotulo'])}", *notas])
    return {
        "label": rotulo_para_grafo(v["rotulo"]),
        "title": titulo,
        "shape": vis["forma"],
        "color": cor,
        "borderWidth": borda,
        "size": 34 if v["id"] == selecionado else 18,
    }


def montar_rede(grafo: dict[str, Any]) -> Network:
    """Network do pyvis a partir da saída de `grafo_do_chamado` (já mascarada)."""
    rede = Network(height=f"{ALTURA_PX}px", width="100%", directed=False, cdn_resources="in_line")
    selecionado = grafo["chamado_id"]
    for v in grafo["vertices"]:
        attrs = _no(v, selecionado)
        rede.add_node(v["id"], label=attrs.pop("label"), shape=attrs.pop("shape"), color=attrs.pop("color"), **attrs)
    for a in grafo["arestas"]:
        no_caminho = a["no_caminho_fraude"]
        rotulo = rotulo_para_grafo(a["rotulo"])
        rede.add_edge(
            a["origem"],
            a["destino"],
            label=rotulo,
            title=rotulo + ("\ncaminho até a fraude" if no_caminho else ""),
            color=COR_FRAUDE if no_caminho else COR_ARESTA,
            width=4 if no_caminho else 1.5,
        )
    rede.options = dict(_OPCOES)
    return rede


def _trocar_uma_vez(html: str, alvo: str, novo: str) -> str:
    """Substitui `alvo` uma vez; se o template do pyvis mudar e o alvo sumir, falha alto."""
    if alvo not in html:
        raise RuntimeError(f"template do pyvis mudou: não achei {alvo!r}")
    return html.replace(alvo, novo, 1)


def html_do_grafo(grafo: dict[str, Any]) -> str:
    """HTML autocontido para st.iframe (generate_html; nunca show(), que grava arquivo).

    Pós-processamento: tira o Bootstrap externo, põe a CSP no <head> e desliga a física
    depois de estabilizar. Ids e rótulos entram no JS via `tojson` do Jinja, que escapa
    '<' como \\u003c: um "</script>" num id não fecha o bloco de dados (há teste).
    """
    html = _RE_BOOTSTRAP.sub("", montar_rede(grafo).generate_html())
    html = _trocar_uma_vez(html, "<head>", "<head>\n        " + _META_CSP)
    return _trocar_uma_vez(html, "return network;", _JS_DESLIGA_FISICA + "return network;")
