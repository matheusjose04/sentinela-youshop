"""Carga e validação da base fictícia (data/*.json)."""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sentinela.core.grafo import PESOS
from sentinela.core.injecao import detectar_injecao
from sentinela.core.modelos import (
    MOTIVOS_CODIGO,
    TIPOS_EVENTO,
    TIPOS_VERTICE,
    Aresta,
    Chamado,
    EventoSaque,
    Post,
    Reembolso,
    Vertice,
)

# "Agora" de referência da demo: os dados fictícios foram escritos em torno desta data.
# O core nunca chama datetime.now(); quem chama decide o relógio.
AGORA_DEMO = datetime(2026, 11, 20, 15, 0, tzinfo=timezone(timedelta(hours=-3)))

PASTA_PADRAO = Path(__file__).resolve().parents[2] / "data"

# Rótulos (handles, nomes de produto e de comprador) são escolhidos por terceiros e aparecem
# fora de "citacao" (provas, motivo do score, grafo). Por isso só aceitamos uma allowlist curta:
# letras (com acento), dígitos, espaço, "@", ".", "-", "_", "•" e parênteses, até 40 caracteres.
ROTULO_RE = re.compile(r"[@\w .\-•()À-ÿ]{1,40}")


class DadosInvalidos(ValueError):
    """Os JSON de data/ têm referência quebrada ou campo inválido."""


@dataclass(frozen=True)
class Base:
    vertices: dict[str, Vertice]  # inclui um vértice por chamado
    arestas: list[Aresta]  # inclui "abriu chamado" (autor -> chamado)
    chamados: dict[str, Chamado]
    eventos_saque: list[EventoSaque]
    reembolsos: list[Reembolso]
    posts: list[Post]


def _ler(pasta: Path, nome: str) -> list[dict[str, Any]]:
    caminho = pasta / f"{nome}.json"
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erro:
        raise DadosInvalidos(f"não consegui ler {caminho.name}: {erro}") from erro
    _exigir(isinstance(dados, list), f"{caminho.name} deve ser uma lista")
    _exigir(all(isinstance(r, dict) for r in dados), f"cada item de {caminho.name} deve ser um objeto")
    ids = [r["id"] for r in dados if "id" in r]
    repetidos = sorted({i for i in ids if ids.count(i) > 1})
    _exigir(not repetidos, f"id repetido em {caminho.name}: {repetidos}")
    return dados


def _numero(valor: Any, campo: str, dono: str, maximo: float = math.inf) -> None:
    """Número de verdade (não bool), finito e entre 0 e `maximo`."""
    ok = isinstance(valor, (int, float)) and not isinstance(valor, bool) and math.isfinite(valor)
    _exigir(ok and 0 <= valor <= maximo, f"{campo} inválido em {dono}: {valor!r}")


def _datas(registro: dict[str, Any], *campos: str) -> dict[str, Any]:
    out = dict(registro)
    for c in campos:
        out[c] = datetime.fromisoformat(out[c])
        if out[c].tzinfo is None:
            raise DadosInvalidos(f"data sem fuso horário em {registro.get('id')}: {c}")
    return out


def _construir(cls: type, registros: list[dict[str, Any]], *datas: str) -> list[Any]:
    try:
        return [cls(**_datas(r, *datas)) for r in registros]
    except (TypeError, ValueError, KeyError) as erro:
        if isinstance(erro, DadosInvalidos):
            raise
        raise DadosInvalidos(f"registro inválido para {cls.__name__}: {erro}") from erro


def _exigir(existe: bool, mensagem: str) -> None:
    if not existe:
        raise DadosInvalidos(mensagem)


def assinatura(pasta: Path | str = PASTA_PADRAO) -> str:
    """Assinatura de data/*.json (nome, mtime, tamanho): mudou um JSON, muda a assinatura.

    Usada como chave de cache pela UI e pelo MCP (recarregam a base sem reiniciar).
    """
    arquivos = sorted(Path(pasta).glob("*.json"))
    partes = [f"{p.name}:{p.stat().st_mtime_ns}:{p.stat().st_size}" for p in arquivos]
    return hashlib.sha256("|".join(partes).encode()).hexdigest()[:16]


def _validar_rotulo(registro: dict[str, Any]) -> None:
    """Allowlist + detector de injeção. A mensagem não repete o rótulo ruim (só o id)."""
    rotulo = registro.get("rotulo")
    dono = registro.get("id")
    _exigir(isinstance(rotulo, str) and ROTULO_RE.fullmatch(rotulo) is not None, f"rótulo inválido em {dono}")
    _exigir(not detectar_injecao(rotulo), f"rótulo com tentativa de injeção em {dono}")


def carregar(pasta: Path | str = PASTA_PADRAO) -> Base:
    """Lê os JSON, cria um vértice + aresta "abriu chamado" por chamado e valida referências."""
    pasta = Path(pasta)
    brutos_v = _ler(pasta, "vertices")
    for r in brutos_v:
        _exigir(r.get("tipo") in TIPOS_VERTICE, f"tipo de vértice inválido em {r.get('id')}: {r.get('tipo')!r}")
        _exigir(
            isinstance(r.get("fraude_confirmada", False), bool),
            f"fraude_confirmada deve ser true/false em {r.get('id')}",
        )
        _validar_rotulo(r)
        if "oferece" in r:
            r["oferece"] = tuple(r["oferece"])
    vertices = {v.id: v for v in _construir(Vertice, brutos_v)}
    arestas: list[Aresta] = _construir(Aresta, _ler(pasta, "arestas"))
    brutos_c = _ler(pasta, "chamados")
    for r in brutos_c:
        _numero(r.get("valor", 0.0), "valor", r.get("id"))
        if r.get("percentual_assistido") is not None:
            _numero(r["percentual_assistido"], "percentual_assistido", r.get("id"), 1.0)
        _exigir(
            r.get("motivo_codigo") is None or r["motivo_codigo"] in MOTIVOS_CODIGO,
            f"motivo_codigo inválido em {r.get('id')}: {r.get('motivo_codigo')!r}",
        )
    chamados = {c.id: c for c in _construir(Chamado, brutos_c, "aberto_em")}
    brutos_e = _ler(pasta, "eventos_saque")
    for r in brutos_e:
        _exigir(r.get("tipo") in TIPOS_EVENTO, f"tipo de evento inválido em {r.get('id')}: {r.get('tipo')!r}")
        for campo in ("valor", "saldo"):
            if r.get(campo) is not None:
                _numero(r[campo], campo, r.get("id"))
        if r.get("valor") is not None and r.get("saldo") is not None:
            _exigir(r["valor"] <= r["saldo"], f"saque maior que o saldo em {r.get('id')}")
    eventos: list[EventoSaque] = _construir(EventoSaque, brutos_e, "em")
    brutos_r = _ler(pasta, "reembolsos")
    for r in brutos_r:
        _numero(r.get("valor"), "valor", r.get("id"))
        _numero(r.get("percentual_assistido"), "percentual_assistido", r.get("id"), 1.0)
        _exigir(r.get("motivo_codigo") in MOTIVOS_CODIGO, f"motivo_codigo inválido em {r.get('id')}: {r.get('motivo_codigo')!r}")
    reembolsos: list[Reembolso] = _construir(Reembolso, brutos_r, "em")
    brutos_p = _ler(pasta, "posts")
    for r in brutos_p:
        r["promete"] = tuple(r.get("promete", ()))
    posts: list[Post] = _construir(Post, brutos_p, "em")

    for a in arestas:
        _exigir(a.rotulo in PESOS, f"rótulo de aresta desconhecido: {a.rotulo!r}")
        for ponta in (a.origem, a.destino):
            _exigir(ponta in vertices, f"aresta referencia vértice inexistente: {ponta!r}")

    # Cada chamado vira vértice do grafo, ligado a quem abriu.
    for ch in chamados.values():
        _exigir(ch.autor_id in vertices, f"chamado {ch.id} com autor inexistente: {ch.autor_id!r}")
        _exigir(ch.produto_id is None or ch.produto_id in vertices, f"chamado {ch.id}: produto {ch.produto_id!r}")
        _exigir(ch.id not in vertices, f"id de chamado repetido como vértice: {ch.id!r}")
        # Rótulo = só o id: o assunto é texto de terceiros e não vira rótulo do grafo.
        vertices[ch.id] = Vertice(id=ch.id, tipo="chamado", rotulo=ch.id)
        arestas.append(Aresta(origem=ch.autor_id, destino=ch.id, rotulo="abriu chamado"))

    for r in reembolsos:
        for ref in (r.comprador_id, r.produto_id, r.creator_id):
            _exigir(ref is None or ref in vertices, f"reembolso {r.id} referencia {ref!r} inexistente")
    for e in eventos:
        _exigir(e.creator_id in vertices, f"evento {e.id} referencia {e.creator_id!r} inexistente")
    for p in posts:
        _exigir(p.creator_id in vertices and p.produto_id in vertices, f"post {p.id} com referência inexistente")

    return Base(vertices, arestas, chamados, eventos, reembolsos, posts)
