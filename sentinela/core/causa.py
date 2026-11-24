"""Regras determinísticas de CAUSA PROVÁVEL (sem LLM).

As regras são testadas em ordem e a primeira que bate vence (ver REGRAS no fim):
  1. fraude / conta suspeita: o GRUPO DE SEGURANÇA do chamado (BFS que não atravessa
     produto) tem fraude confirmada, celular/Pix em comum ou saque fora do padrão
  2. produto: chamado de reembolso; mesmo motivo_codigo vindo de 3+ creators diferentes,
     sem concentração em um creator só (nos últimos 30 dias)
  3. creator: chamado de reembolso; 80%+ dos reembolsos do motivo vêm de 1 creator e o post
     dele promete (campo `promete`) algo que o produto não oferece (`oferece`)
  4. padrão de abuso do comprador: 5+ reembolsos em 30 dias, 3+ produtores, 80%+ assistido
  5. comum
Só dados ESTRUTURADOS decidem (grafo, códigos de motivo, promessas, números). Texto livre
(chamado, motivo escrito, post) nunca é critério: aparece só como citação nas provas.
O resultado é sempre "causa provável" com confiança; nunca afirmação de culpa.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sentinela.core.algoritmos import bfs_componente
from sentinela.core.grafo import NAO_ATRAVESSA, Grafo
from sentinela.core.mascara import rotulo_seguro
from sentinela.core.modelos import TIPOS_CONTA, AlertaSaque, Causa, Chamado, Prova, Reembolso

if TYPE_CHECKING:
    from sentinela.core.dados import Base

FONTE_GRAFO = "grafo de ligações"
FONTE_REEMBOLSOS = "histórico de reembolsos"
FONTE_CADASTRO = "cadastro do produto"

JANELA = timedelta(days=30)  # reembolsos considerados por todas as regras
MIN_CREATORS_PRODUTO = 3
MIN_REEMBOLSOS_CREATOR = 3
CONCENTRACAO_CREATOR = 0.80
MIN_REEMBOLSOS_ABUSO = 5
MIN_PRODUTORES_ABUSO = 3
MIN_ASSISTIDO_ABUSO = 0.80

# Motivos de formulário compatíveis com cada regra.
MOTIVOS_PRODUTO = frozenset({"produto_defeituoso", "nao_recebido", "diferente_do_anunciado"})
MOTIVOS_CREATOR = frozenset({"promessa_divulgacao", "diferente_do_anunciado"})

# Promessas estruturadas que um post pode fazer -> nome legível.
PROMESSAS: dict[str, str] = {
    "certificado_mec": "certificado reconhecido pelo MEC",
    "certificado_de_conclusao": "certificado de conclusão",
    "emprego_garantido": "emprego garantido",
    "resultado_garantido": "resultado garantido",
}


@dataclass(frozen=True)
class Sinais:
    """O que o grafo diz sobre o grupo de segurança do chamado."""

    componente: frozenset[str]
    fraudes: tuple[str, ...]  # vértices com fraude confirmada no grupo
    compartilhados: tuple[tuple[str, tuple[str, ...]], ...]  # (celular/Pix, contas que usam)
    alerta_saque: AlertaSaque | None
    contas: int


def coletar_sinais(grafo: Grafo, chamado: Chamado, alertas: dict[str, AlertaSaque]) -> Sinais:
    """BFS a partir do chamado SEM atravessar produto, e leitura dos sinais de segurança.

    Por que não atravessar produto: comprar ou divulgar o mesmo produto não liga duas contas.
    Senão um comprador comum do produto de uma rede de fraude "herdaria" a fraude.
    """
    comp = bfs_componente(grafo, chamado.id, NAO_ATRAVESSA)
    vs = grafo.vertices
    fraudes = tuple(sorted(v for v in comp if vs[v].fraude_confirmada))
    compartilhados = []
    for v in sorted(comp):
        if vs[v].tipo in ("celular", "chave_pix"):
            contas = sorted({viz for viz, _, _ in grafo.vizinhos(v) if vs[viz].tipo in TIPOS_CONTA})
            if len(contas) >= 2:
                compartilhados.append((v, tuple(contas)))
    alerta = next((alertas[v] for v in sorted(comp) if v in alertas), None)
    n_contas = sum(1 for v in comp if vs[v].tipo in TIPOS_CONTA)
    return Sinais(frozenset(comp), fraudes, tuple(compartilhados), alerta, n_contas)


def _nome(base: Base, vid: str | None) -> str:
    return rotulo_seguro(base.vertices[vid]) if vid else "venda direta"


def _nomes(base: Base, ids: list[str] | tuple[str, ...]) -> str:
    return ", ".join(_nome(base, i) for i in ids)


def _legivel(codigo: str) -> str:
    return codigo.replace("_", " ")


def _recentes(reembolsos: list[Reembolso], agora: datetime) -> list[Reembolso]:
    return [r for r in reembolsos if agora - JANELA <= r.em <= agora]


# ---------------------------------------------------------------- regra 1
def regra_seguranca(chamado: Chamado, base: Base, sinais: Sinais, agora: datetime) -> Causa | None:
    if sinais.alerta_saque:
        a = sinais.alerta_saque
        provas = list(a.provas)
        for disp, contas in sinais.compartilhados:
            outras = [c for c in contas if c != a.creator_id]
            if a.creator_id in contas and outras:
                provas.append(Prova(f"{_nome(base, disp)} também usado por {_nomes(base, outras)}", FONTE_GRAFO))
        return Causa(
            tipo="conta_invadida",
            confianca="alta",
            descricao=(
                f"Causa provável: acesso indevido à conta {_nome(base, a.creator_id)} "
                f"(celular novo, chave Pix trocada e saque de {a.percentual_saldo:.0%} do saldo em {a.minutos} min)."
            ),
            provas=tuple(provas),
        )
    if not (sinais.fraudes or sinais.compartilhados):
        return None
    provas = [
        Prova(f"{_nome(base, disp)} usado por {len(contas)} contas: {_nomes(base, contas)}", FONTE_GRAFO)
        for disp, contas in sinais.compartilhados
    ]
    for f in sinais.fraudes:
        provas.append(Prova(f"{_nome(base, f)} tem fraude confirmada e está no mesmo grupo", FONTE_GRAFO))
    provas += _provas_proprio_link(base, sinais)
    # Os dois sinais juntos (fraude confirmada + dispositivo/Pix em comum) dão confiança alta.
    confianca = "alta" if sinais.fraudes and sinais.compartilhados else "média"
    return Causa(
        tipo="fraude",
        confianca=confianca,
        descricao=(
            f"Causa provável: rede de contas ligadas (fraude de comissão): o grupo do chamado reúne "
            f"{sinais.contas} contas que dividem celular ou chave Pix"
            + (" com uma fraude confirmada." if sinais.fraudes else ".")
        ),
        provas=tuple(provas),
    )


def _provas_proprio_link(base: Base, sinais: Sinais) -> list[Prova]:
    """Comprador e creator no mesmo celular = compra pelo próprio link de divulgação."""
    provas = []
    for disp, contas in sinais.compartilhados:
        compradores = [c for c in contas if base.vertices[c].tipo == "comprador"]
        creators = [c for c in contas if base.vertices[c].tipo == "creator"]
        if compradores and creators:
            provas.append(
                Prova(
                    f"Compras de {_nomes(base, compradores)} feitas do mesmo {_nome(base, disp)} dos creators "
                    f"(compra pelo próprio link)",
                    FONTE_GRAFO,
                )
            )
    return provas


# ---------------------------------------------------------------- regras 2 e 3
def _reembolsos_do_motivo(base: Base, chamado: Chamado, agora: datetime) -> list[Reembolso]:
    """Reembolsos recentes do MESMO produto e do MESMO motivo_codigo do chamado."""
    return _recentes(
        [r for r in base.reembolsos if r.produto_id == chamado.produto_id and r.motivo_codigo == chamado.motivo_codigo],
        agora,
    )


def _concentracao(reembolsos: list[Reembolso]) -> tuple[str | None, int, float]:
    """(creator com mais reembolsos, quantos, fração do total)."""
    creator, qtd = Counter(r.creator_id for r in reembolsos).most_common(1)[0]
    return creator, qtd, qtd / len(reembolsos)


def _citar_motivos(reembolsos: list[Reembolso]) -> str:
    """Exemplos do que os compradores escreveram (texto livre, sai como citação)."""
    vistos: list[str] = []
    for r in reembolsos:
        if r.motivo not in vistos:
            vistos.append(r.motivo)
    return " / ".join(vistos[:3])


def regra_produto(chamado: Chamado, base: Base, sinais: Sinais, agora: datetime) -> Causa | None:
    if chamado.tipo != "reembolso" or chamado.motivo_codigo not in MOTIVOS_PRODUTO:
        return None
    grupo = _reembolsos_do_motivo(base, chamado, agora)
    creators = sorted({r.creator_id for r in grupo if r.creator_id})
    if len(creators) < MIN_CREATORS_PRODUTO:
        return None
    # Muitos creators diferentes com a mesma reclamação: a divulgação não explica o padrão.
    # Mas se um creator concentra 80%+, o padrão é dele, não do produto.
    _, _, share = _concentracao(grupo)
    if share >= CONCENTRACAO_CREATOR:
        return None
    produto = _nome(base, chamado.produto_id)
    motivo = _legivel(chamado.motivo_codigo)
    return Causa(
        tipo="produto",
        confianca="alta" if len(creators) >= 4 else "média",
        descricao=f"Causa provável: problema no próprio produto {produto} (mesmo motivo vindo de {len(creators)} creators diferentes).",
        provas=(
            Prova(
                f"{len(grupo)} reembolsos com o motivo '{motivo}' nos últimos 30 dias, vindos de "
                f"{len(creators)} creators diferentes: {_nomes(base, creators)}",
                FONTE_REEMBOLSOS,
                citacao=_citar_motivos(grupo),
            ),
            Prova(f"Maior concentração em um creator só: {share:.0%} (abaixo de 80%)", FONTE_REEMBOLSOS),
        ),
        alvo=chamado.produto_id,
    )


def regra_creator(chamado: Chamado, base: Base, sinais: Sinais, agora: datetime) -> Causa | None:
    if chamado.tipo != "reembolso" or chamado.motivo_codigo not in MOTIVOS_CREATOR:
        return None
    grupo = _reembolsos_do_motivo(base, chamado, agora)
    if len(grupo) < MIN_REEMBOLSOS_CREATOR:
        return None
    creator, qtd, share = _concentracao(grupo)
    if creator is None or share < CONCENTRACAO_CREATOR:
        return None
    produto = base.vertices[chamado.produto_id]
    # Promessa falsa = o post promete (campo estruturado) algo fora do que o produto oferece.
    achados = [
        (p, [c for c in p.promete if c not in produto.oferece])
        for p in base.posts
        if p.creator_id == creator and p.produto_id == produto.id
    ]
    achados = [(p, falsas) for p, falsas in achados if falsas]
    if not achados:
        return None  # concentração sem promessa falsa não basta
    post, falsas = achados[0]
    nomes_falsas = [PROMESSAS.get(c, _legivel(c)) for c in falsas]
    provas = [
        Prova(
            f"{qtd} de {len(grupo)} reembolsos de {produto.rotulo} nos últimos 30 dias vieram de "
            f"{_nome(base, creator)} ({share:.0%})",
            FONTE_REEMBOLSOS,
        ),
        Prova(
            f"Post de {_nome(base, creator)} promete: {', '.join(nomes_falsas)}",
            f"post do creator ({post.id})",
            citacao=post.texto,
        ),
        Prova(f"O cadastro de {produto.rotulo} não inclui {', '.join(nomes_falsas)}", FONTE_CADASTRO),
    ]
    outros = sorted(
        {p.creator_id for p in base.posts if p.produto_id == produto.id and p.creator_id != creator}
        - {r.creator_id for r in grupo}
    )
    if outros:
        provas.append(Prova(f"{_nomes(base, outros)} divulga o mesmo produto sem reembolsos", FONTE_REEMBOLSOS))
    return Causa(
        tipo="creator",
        confianca="alta" if qtd >= 5 else "média",
        descricao=(
            f"Causa provável: a divulgação de {_nome(base, creator)} promete '{nomes_falsas[0]}', "
            f"que o {produto.rotulo} não oferece."
        ),
        provas=tuple(provas),
        alvo=creator,
    )


def compradores_afetados(causa: Causa, chamado: Chamado, base: Base, agora: datetime) -> int:
    """Compradores distintos com reembolso da mesma causa (mesmo produto, motivo e, se for
    causa creator, o mesmo creator) nos últimos 30 dias. Usado na parcela "grupo" do score."""
    if causa.tipo not in ("produto", "creator"):
        return 0
    grupo = _reembolsos_do_motivo(base, chamado, agora)
    if causa.tipo == "creator":
        grupo = [r for r in grupo if r.creator_id == causa.alvo]
    return len({r.comprador_id for r in grupo})


# ---------------------------------------------------------------- regra 4
def reembolsos_recentes(base: Base, comprador_id: str, agora: datetime) -> list[Reembolso]:
    return _recentes([r for r in base.reembolsos if r.comprador_id == comprador_id], agora)


def regra_ma_fe(chamado: Chamado, base: Base, sinais: Sinais, agora: datetime) -> Causa | None:
    if chamado.tipo != "reembolso" or base.vertices[chamado.autor_id].tipo != "comprador":
        return None
    recentes = reembolsos_recentes(base, chamado.autor_id, agora)
    produtores = sorted({base.vertices[r.produto_id].produtor or "?" for r in recentes})
    if len(recentes) < MIN_REEMBOLSOS_ABUSO or len(produtores) < MIN_PRODUTORES_ABUSO:
        return None
    media = sum(r.percentual_assistido for r in recentes) / len(recentes)
    if media < MIN_ASSISTIDO_ABUSO:
        return None
    provas = [
        Prova(f"{len(recentes)} reembolsos nos últimos 30 dias", FONTE_REEMBOLSOS),
        Prova(f"Em {len(produtores)} produtores diferentes: {', '.join(produtores)}", FONTE_REEMBOLSOS),
        Prova(f"Média de {media:.0%} do conteúdo assistido antes de pedir reembolso", FONTE_REEMBOLSOS),
    ]
    if chamado.percentual_assistido is not None:
        provas.append(
            Prova(f"Neste pedido: {chamado.percentual_assistido:.0%} de {_nome(base, chamado.produto_id)} assistido", "chamado")
        )
    return Causa(
        tipo="ma_fe_comprador",
        # Média de propósito: o padrão é forte, mas intenção não se prova só com dados.
        confianca="média",
        descricao=(
            "Causa provável: padrão de reembolsos fora do comum no histórico do comprador (possível abuso). "
            "É um padrão, não uma prova de intenção."
        ),
        provas=tuple(provas),
        alvo=chamado.autor_id,
    )


# ---------------------------------------------------------------- regra 5
DESCRICAO_COMUM = {
    "acesso": "Causa provável: problema comum de acesso à conta ou ao curso, sem sinal de risco no grafo.",
}


def causa_comum(chamado: Chamado, base: Base, sinais: Sinais, agora: datetime) -> Causa:
    recentes = len(reembolsos_recentes(base, chamado.autor_id, agora))
    return Causa(
        tipo="comum",
        confianca="média",
        descricao=DESCRICAO_COMUM.get(
            chamado.tipo, "Causa provável: pedido comum, sem padrão anormal no grafo nem no histórico."
        ),
        provas=(
            Prova(
                f"Grupo no grafo com {sinais.contas} conta(s), sem fraude confirmada nem celular/Pix em comum",
                FONTE_GRAFO,
            ),
            Prova(f"{recentes} reembolso(s) do autor nos últimos 30 dias", FONTE_REEMBOLSOS),
        ),
    )


Regra = Callable[[Chamado, "Base", Sinais, datetime], Causa | None]
# Ordem = precedência (também a dos centros: Operações > Produtor > Creator > Comprador).
REGRAS: tuple[Regra, ...] = (regra_seguranca, regra_produto, regra_creator, regra_ma_fe)


def identificar_causa(chamado: Chamado, base: Base, sinais: Sinais, agora: datetime) -> Causa:
    """Primeira regra que bate vence; se nenhuma bater, é um chamado comum."""
    for regra in REGRAS:
        causa = regra(chamado, base, sinais, agora)
        if causa is not None:
            return causa
    return causa_comum(chamado, base, sinais, agora)
