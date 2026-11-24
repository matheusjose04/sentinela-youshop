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

LIMITE_ROTULO = 40  # tooltip (title): rótulo inteiro, até este limite seguro
LIMITE_LABEL = 18  # texto desenhado no canvas: curto, para os rótulos não se sobreporem
COR_FRAUDE = "#d62728"
COR_ARESTA = "#9ca3af"
COR_FORA_DO_GRUPO = {"background": "#e5e7eb", "border": "#9ca3af"}
ALTURA_PX = 520
MOLA_CONTEXTO = 300  # comprimento das arestas até produto fora do grupo (a mola padrão é menor)

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
# Dentro de um st.expander fechado o iframe nasce com largura 0: o vis-network (autoResize)
# redesenha quando o expander abre, e a cada resize o grafo é reenquadrado até a pessoa mexer nele.
_JS_DESLIGA_FISICA = """function ajustarComFolga() {
                      // Enquadra pelas POSIÇÕES dos vértices, não pelo fit() do vis: enquanto o iframe está
                      // escondido nada é desenhado e as caixas que o fit() usa ficam velhas.
                      // Folga de 130 (lados) e 50 (cima/baixo) unidades para os rótulos não cortarem na borda.
                      var tela = network.canvas.frame.canvas;
                      var largura = tela.clientWidth, altura = tela.clientHeight;
                      var pos = Object.values(network.getPositions());
                      if (!largura || !altura || !pos.length) { return; }
                      var xs = pos.map(function (p) { return p.x; }), ys = pos.map(function (p) { return p.y; });
                      var x0 = Math.min.apply(null, xs) - 130, x1 = Math.max.apply(null, xs) + 130;
                      var y0 = Math.min.apply(null, ys) - 50, y1 = Math.max.apply(null, ys) + 50;
                      var escala = Math.min(largura / (x1 - x0), altura / (y1 - y0), 1.2);
                      network.moveTo({ position: { x: (x0 + x1) / 2, y: (y0 + y1) / 2 }, scale: escala });
                  }
                  network.once("stabilizationIterationsDone", function () {
                      network.setOptions({ physics: false });
                      // depois do fit interno do vis (stabilization.fit): enquadra as posições finais com folga
                      setTimeout(ajustarComFolga, 50);
                  });
                  // Escondido, o iframe pode ter tamanho 0 ou provisório: reenquadra a cada resize
                  // (inclusive quando o expander abre) até a pessoa arrastar ou dar zoom.
                  var pessoaMexeu = false;
                  network.on("dragStart", function () { pessoaMexeu = true; });
                  network.on("zoom", function () { pessoaMexeu = true; });
                  network.on("resize", function (p) {
                      if (!pessoaMexeu && p.width > 0 && p.height > 0) {
                          ajustarComFolga();
                      }
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
        # Repulsão forte + molas longas + avoidOverlap: os vértices (e seus rótulos) ficam afastados.
        "solver": "barnesHut",
        "barnesHut": {
            "gravitationalConstant": -30000,
            "centralGravity": 0.3,
            "springLength": 220,
            "springConstant": 0.03,
            "damping": 0.4,
            "avoidOverlap": 1,
        },
        "stabilization": {"enabled": True, "iterations": 1000, "fit": True},
    },
    "layout": {"randomSeed": 7},  # layout reproduzível: o mesmo grafo abre sempre igual
    "autoResize": True,  # padrão do vis-network, explícito: redesenha quando o expander abre
    "interaction": {"hover": True, "tooltipDelay": 120, "navigationButtons": False},
    "edges": {"smooth": False, "font": {"size": 10, "align": "middle", "strokeWidth": 3, "color": "#4b5563"}},
    "nodes": {"font": {"size": 26, "strokeWidth": 4, "strokeColor": "#ffffff"}, "margin": 6},
}


def rotulo_para_grafo(texto: str) -> str:
    """Rótulo seguro para label/title: sem < > & " ' e com no máximo 40 caracteres."""
    texto = " ".join(str(texto).split()).translate(_SEGURO)
    return texto if len(texto) <= LIMITE_ROTULO else texto[: LIMITE_ROTULO - 1] + "…"


def rotulo_curto(texto: str) -> str:
    """Rótulo desenhado no canvas: seguro e com no máximo 18 caracteres (o inteiro fica no tooltip)."""
    texto = rotulo_para_grafo(texto)
    return texto if len(texto) <= LIMITE_LABEL else texto[: LIMITE_LABEL - 1].rstrip() + "…"


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
        "label": rotulo_curto(v["rotulo"]),
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
    grau: dict[str, int] = {}
    for a in grafo["arestas"]:
        for v in (a["origem"], a["destino"]):
            grau[v] = grau.get(v, 0) + 1
    fora = {v["id"] for v in grafo["vertices"] if v["fora_do_grupo"]}
    for v in grafo["vertices"]:
        attrs = _no(v, selecionado)
        # Massa maior = repulsão maior: hubs (celular/chave Pix dividida) abrem espaço para os rótulos.
        attrs["mass"] = 1 + 0.4 * max(0, grau.get(v["id"], 0) - 1)
        rede.add_node(v["id"], label=attrs.pop("label"), shape=attrs.pop("shape"), color=attrs.pop("color"), **attrs)
    for a in grafo["arestas"]:
        no_caminho = a["no_caminho_fraude"]
        rotulo = rotulo_para_grafo(a["rotulo"])
        extra = {}
        if a["origem"] in fora or a["destino"] in fora:
            extra["length"] = MOLA_CONTEXTO  # produto é só contexto: fica mais afastado do grupo
        rede.add_edge(
            a["origem"],
            a["destino"],
            label=rotulo_curto(a["rotulo"]),
            title=rotulo + ("\ncaminho até a fraude" if no_caminho else ""),
            color=COR_FRAUDE if no_caminho else COR_ARESTA,
            width=4 if no_caminho else 1.5,
            **extra,
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
