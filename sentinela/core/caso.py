"""Caso montado: ponto único de SAÍDA para a UI (Streamlit) e o servidor MCP.

A UI e o MCP usam SOMENTE estas quatro funções (todas devolvem dict já mascarado e com aviso):
  - montar_caso(chamado_id, base, agora)
  - montar_fila(base, agora, centro=None)
  - grafo_do_chamado(chamado_id, base, agora)
  - alertas_saque_para_saida(base, agora)
Nada de dataclass cru (com CPF/IP/chave Pix) sai daqui.

Mostra causa, provas e alertas; NÃO sugere o que fazer: quem decide é o atendente.
Todo texto de terceiros (assunto, texto, post, motivo escrito, detalhe de evento) sai
marcado como dado: {"citacao": <bloco delimitado>, "origem": "dado de terceiros"}.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sentinela.core.algoritmos import caminho_ate_fraude
from sentinela.core.causa import (
    Sinais,
    coletar_sinais,
    compradores_afetados,
    identificar_causa,
    reembolsos_recentes,
)
from sentinela.core.dados import Base
from sentinela.core.fila import ContextoScore, FilaPrioridade, calcular_score, faixa, formatar_brl, formatar_espera
from sentinela.core.grafo import NAO_ATRAVESSA, Grafo
from sentinela.core.injecao import MENSAGEM_ALERTA, como_dado, detectar_injecao
from sentinela.core.mascara import mascarar_cpf, mascarar_ip, mascarar_texto, rotulo_seguro, truncar
from sentinela.core.modelos import Causa, Chamado, Prova, Rota, Score
from sentinela.core.roteamento import agrupar_chamados, rotear, texto_grupo
from sentinela.core.saque import listar_alertas_saque

AVISO = "Dados fictícios · protótipo"
ORIGEM_TERCEIROS = "dado de terceiros"
LEMBRETE_ARREPENDIMENTO = (
    "O direito de arrependimento de 7 dias (CDC, art. 49) continua valendo para este comprador. O humano decide."
)
EFEITO_INJECAO = "Instrução ignorada: o texto é tratado só como dado e não altera causa, rota nem prioridade."


@dataclass(frozen=True)
class Analise:
    """Tudo que o core calcula sobre a base num instante `agora`."""

    grafo: Grafo
    sinais: dict[str, Sinais]
    causas: dict[str, Causa]
    rotas: dict[str, Rota]
    contextos: dict[str, ContextoScore]
    caminhos: dict[str, tuple[list[str], int] | None]  # Dijkstra até fraude (sem atravessar produto)


def analisar(base: Base, agora: datetime) -> Analise:
    grafo = Grafo.de_base(base)
    alertas = {a.creator_id: a for a in listar_alertas_saque(base, agora)}
    sinais = {cid: coletar_sinais(grafo, ch, alertas) for cid, ch in base.chamados.items()}
    causas = {cid: identificar_causa(ch, base, sinais[cid], agora) for cid, ch in base.chamados.items()}
    grupos = agrupar_chamados(causas, {cid: s.componente for cid, s in sinais.items()})
    rotas = {cid: rotear(causas[cid], grupos[cid]) for cid in base.chamados}
    contextos = {
        cid: ContextoScore(
            alerta_saque=s.alerta_saque,
            fraude_no_grupo=bool(s.fraudes),
            compartilhamento=bool(s.compartilhados),
            contas_no_grupo=s.contas,
            contas_da_causa=compradores_afetados(causas[cid], base.chamados[cid], base, agora),
            alvo_causa=rotulo_seguro(base.vertices[causas[cid].alvo]) if causas[cid].alvo else None,
        )
        for cid, s in sinais.items()
    }
    caminhos = {cid: caminho_ate_fraude(grafo, cid, NAO_ATRAVESSA) for cid in base.chamados}
    return Analise(grafo, sinais, causas, rotas, contextos, caminhos)


# ---------------------------------------------------------------- helpers de saída
def _mascarar_tudo(obj: Any) -> Any:
    """Última barreira: passa a máscara em toda string da saída."""
    if isinstance(obj, str):
        return mascarar_texto(obj)
    if isinstance(obj, dict):
        return {k: _mascarar_tudo(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_mascarar_tudo(v) for v in obj]
    return obj


def _citar(texto: str) -> str:
    """Texto de terceiros: mascara, trunca e delimita como dado."""
    return como_dado(truncar(mascarar_texto(texto)))


def _dado(texto: str) -> dict[str, str]:
    return {"citacao": _citar(texto), "origem": ORIGEM_TERCEIROS}


def _prova(p: Prova) -> dict[str, str]:
    saida = {"texto": p.texto, "fonte": p.fonte}
    if p.citacao:
        saida |= {"citacao": _citar(p.citacao), "origem_citacao": ORIGEM_TERCEIROS}
    return saida


def _score_dict(score: Score) -> dict[str, Any]:
    return {
        "total": score.total,
        "faixa": faixa(score.total),
        "motivo": score.motivo,
        "parcelas": [
            {"nome": p.nome, "pontos": p.pontos, "maximo": p.maximo, "explicacao": p.explicacao} for p in score.parcelas
        ],
    }


def _texto_distancia(n: int | None) -> str:
    if n is None:
        return "nenhuma fraude confirmada ligada a este chamado"
    return f"a {n} {'ligação' if n == 1 else 'ligações'} de uma fraude confirmada"


def _distancia(analise: Analise, chamado_id: str) -> dict[str, Any]:
    achado = analise.caminhos[chamado_id]
    if achado is None:
        return {"ligacoes": None, "caminho": [], "texto": _texto_distancia(None)}
    caminho, n = achado
    vs = analise.grafo.vertices
    return {"ligacoes": n, "caminho": [rotulo_seguro(vs[v]) for v in caminho], "texto": _texto_distancia(n)}


def _alerta_seguranca(causa: Causa, sinais: Sinais, distancia: dict[str, Any]) -> dict[str, Any] | str:
    provas = [_prova(p) for p in causa.provas]
    if causa.tipo == "conta_invadida" and sinais.alerta_saque:
        a = sinais.alerta_saque
        return {"tipo": "saque_em_espera", "status": a.status, "mensagem": a.mensagem, "provas": provas}
    if causa.tipo == "fraude":
        perto = f" ({distancia['texto']})" if distancia["ligacoes"] is not None else ""
        return {
            "tipo": "rede_suspeita",
            "mensagem": f"Sinais de contas ligadas no grafo{perto}; revisão humana.",
            "provas": provas,
        }
    if causa.tipo == "ma_fe_comprador":
        return {
            "tipo": "padrao_de_abuso",
            "mensagem": "Padrão de abuso possível: muitos reembolsos recentes, em produtores diferentes, com o conteúdo quase todo assistido.",
            "lembrete": LEMBRETE_ARREPENDIMENTO,
            "provas": provas,
        }
    return "nenhum"


def _alertas_injecao(chamado: Chamado, base: Base, causa: Causa, sinais: Sinais) -> list[dict[str, Any]]:
    """Varre todo texto de terceiros ligado ao caso. Só gera alerta; não muda nada."""
    fontes: list[tuple[str, str]] = [("assunto do chamado", chamado.assunto), ("texto do chamado", chamado.texto)]
    fontes += [(p.fonte, p.citacao) for p in causa.provas if p.citacao]
    fontes += [(f"post do creator ({p.id})", p.texto) for p in base.posts if p.creator_id in sinais.componente]
    alertas, vistos = [], set()
    for fonte, texto in fontes:
        if (fonte, texto) in vistos:
            continue
        vistos.add((fonte, texto))
        trechos = detectar_injecao(texto)
        if trechos:
            alertas.append(
                {
                    "fonte": fonte,
                    "mensagem": MENSAGEM_ALERTA,
                    "trechos": [_citar(t) for t in trechos],
                    "efeito": EFEITO_INJECAO,
                }
            )
    return alertas


def _historico(chamado: Chamado, base: Base, analise: Analise, agora: datetime) -> dict[str, Any]:
    autor = base.vertices[chamado.autor_id]
    reembolsos = [r for r in base.reembolsos if r.comprador_id == autor.id]
    eventos = sorted((e for e in base.eventos_saque if e.creator_id == autor.id and e.em <= agora), key=lambda e: e.em)
    return {
        "conta": rotulo_seguro(autor),
        "tipo": autor.tipo,
        "cpf": mascarar_cpf(autor.cpf) if autor.cpf else "não informado",
        "ultimo_ip": mascarar_ip(autor.ip) if autor.ip else "não informado",
        "reembolsos_30_dias": len(reembolsos_recentes(base, autor.id, agora)),
        "reembolsos_total": len(reembolsos),
        "chamados_do_autor": sorted(c.id for c in base.chamados.values() if c.autor_id == autor.id),
        "eventos_da_conta": [f"{e.em.strftime('%d/%m %H:%M')} {e.tipo.replace('_', ' ')}" for e in eventos],
        "ligacoes_no_grafo": sorted(
            f"{rot} {rotulo_seguro(base.vertices[v])}" for v, rot, _ in analise.grafo.vizinhos(autor.id) if v != chamado.id
        ),
    }


# ---------------------------------------------------------------- saídas públicas
def montar_caso(chamado_id: str, base: Base, agora: datetime, analise: Analise | None = None) -> dict[str, Any]:
    """Caso montado do chamado (já mascarado). Levanta KeyError se o id não existe."""
    chamado = base.chamados[chamado_id]
    analise = analise or analisar(base, agora)
    causa, rota, sinais = analise.causas[chamado_id], analise.rotas[chamado_id], analise.sinais[chamado_id]
    distancia = _distancia(analise, chamado_id)
    caso = {
        "aviso": AVISO,
        "chamado": {
            "id": chamado.id,
            "assunto": _dado(chamado.assunto),
            "tipo": chamado.tipo,
            "aberto_em": chamado.aberto_em.isoformat(),
            "esperando": formatar_espera(agora - chamado.aberto_em),
            "autor": rotulo_seguro(base.vertices[chamado.autor_id]),
            "texto": _dado(chamado.texto),
        },
        "causa": {
            "tipo": causa.tipo,
            "descricao": causa.descricao,
            "confianca": causa.confianca,
            "provas": [_prova(p) for p in causa.provas],
        },
        "historico": _historico(chamado, base, analise, agora),
        "alerta_seguranca": _alerta_seguranca(causa, sinais, distancia),
        "alertas_injecao": _alertas_injecao(chamado, base, causa, sinais),
        "rota": {
            "centro": rota.centro,
            "motivo": rota.motivo,
            "grupo_ids": list(rota.grupo_ids),
            "grupo_texto": texto_grupo(len(rota.grupo_ids)),
        },
        "distancia_fraude": distancia,
        "score": _score_dict(calcular_score(chamado, analise.contextos[chamado_id], agora)),
    }
    return _mascarar_tudo(caso)


def montar_fila(base: Base, agora: datetime, centro: str | None = None) -> dict[str, Any]:
    """Fila priorizada (heap). `centro=None` ou "Todos" = todos os centros."""
    analise = analisar(base, agora)
    fila = FilaPrioridade()
    for cid, ch in base.chamados.items():
        fila.adicionar(ch, analise.contextos[cid])
    itens = []
    for ch, score in fila.ordenar(agora):
        rota = analise.rotas[ch.id]
        if centro not in (None, "Todos") and rota.centro != centro:
            continue
        itens.append(
            {
                "id": ch.id,
                "assunto": _dado(ch.assunto),
                "centro": rota.centro,
                "esperando": formatar_espera(agora - ch.aberto_em),
                "grupo_texto": texto_grupo(len(rota.grupo_ids)),
                **_score_dict(score),
            }
        )
    return _mascarar_tudo({"aviso": AVISO, "itens": itens})


def grafo_do_chamado(chamado_id: str, base: Base, agora: datetime, analise: Analise | None = None) -> dict[str, Any]:
    """Grupo de segurança do chamado + produtos vizinhos (folhas, só contexto) + caminho até fraude."""
    analise = analise or analisar(base, agora)
    grafo = analise.grafo
    grupo = analise.sinais[chamado_id].componente
    produtos = {viz for v in grupo for viz, _, _ in grafo.vizinhos(v) if grafo.vertices[viz].tipo in NAO_ATRAVESSA}
    achado = analise.caminhos[chamado_id]
    caminho = achado[0] if achado else []
    arestas_caminho = {frozenset(par) for par in zip(caminho, caminho[1:])}
    visiveis = sorted(grupo | produtos)
    vertices = [
        {
            "id": v,
            "tipo": grafo.vertices[v].tipo,
            "rotulo": rotulo_seguro(grafo.vertices[v]),
            "fraude_confirmada": grafo.vertices[v].fraude_confirmada,
            "no_caminho_fraude": v in caminho,
            "fora_do_grupo": v in produtos,  # produto não liga contas: só contexto
        }
        for v in visiveis
    ]
    arestas, vistas = [], set()
    for v in sorted(grupo):
        for viz, rot, peso in grafo.vizinhos(v):
            chave = (min(v, viz), max(v, viz), rot)
            if chave in vistas:
                continue  # cada aresta aparece duas vezes na lista de adjacência
            vistas.add(chave)
            arestas.append(
                {
                    "origem": v,
                    "destino": viz,
                    "rotulo": rot,
                    "peso": peso,
                    "no_caminho_fraude": frozenset((v, viz)) in arestas_caminho,
                }
            )
    n = achado[1] if achado else None
    return _mascarar_tudo(
        {
            "aviso": AVISO,
            "chamado_id": chamado_id,
            "vertices": vertices,
            "arestas": arestas,
            "caminho_fraude": caminho,
            "ligacoes_ate_fraude": n,
            "distancia_texto": _texto_distancia(n),
        }
    )


def alertas_saque_para_saida(base: Base, agora: datetime) -> dict[str, Any]:
    """Alertas de saque em espera, mascarados e com aviso (para UI e MCP)."""
    itens = [
        {
            "creator": rotulo_seguro(base.vertices[a.creator_id]),
            "status": a.status,
            "valor": formatar_brl(a.valor),
            "percentual_saldo": a.percentual_saldo,
            "minutos": a.minutos,
            "mensagem": a.mensagem,
            "provas": [_prova(p) for p in a.provas],
        }
        for a in listar_alertas_saque(base, agora)
    ]
    return _mascarar_tudo({"aviso": AVISO, "itens": itens})
