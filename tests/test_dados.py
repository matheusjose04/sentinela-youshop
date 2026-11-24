"""Carga e validação dos dados fictícios em data/."""
import json
import re
import shutil
from pathlib import Path

import pytest

from sentinela.core.dados import DadosInvalidos, carregar
from tests.conftest import PASTA_DADOS


def _cpf_valido(cpf: str) -> bool:
    """Validação oficial dos dígitos verificadores do CPF."""
    d = [int(c) for c in re.sub(r"\D", "", cpf)]
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for n in (9, 10):
        soma = sum(d[i] * (n + 1 - i) for i in range(n))
        if (soma * 10 % 11) % 10 != d[n]:
            return False
    return True


def test_carrega_tudo(base):
    assert len(base.vertices) > 30
    assert base.arestas and base.chamados and base.reembolsos and base.eventos_saque and base.posts


def test_chamado_vira_vertice_com_aresta_abriu_chamado(base):
    for ch in base.chamados.values():
        assert base.vertices[ch.id].tipo == "chamado"
        assert any(a.origem == ch.autor_id and a.destino == ch.id and a.rotulo == "abriu chamado" for a in base.arestas)


def test_datas_tem_fuso(base):
    assert all(ch.aberto_em.tzinfo is not None for ch in base.chamados.values())


def test_cpfs_sao_ficticios(base):
    """Nenhum CPF passa na validação oficial: não pode pertencer a uma pessoa real."""
    cpfs = [v.cpf for v in base.vertices.values() if v.cpf]
    textos = " ".join(ch.texto for ch in base.chamados.values())
    cpfs += re.findall(r"\d{3}\.\d{3}\.\d{3}-\d{2}", textos)
    assert cpfs
    assert not any(_cpf_valido(c) for c in cpfs)


def test_ips_sao_de_documentacao(base):
    ips = [v.ip for v in base.vertices.values() if v.ip]
    assert ips
    assert all(ip.startswith(("192.0.2.", "198.51.100.", "203.0.113.")) for ip in ips)


def test_emails_sao_de_dominio_reservado(base):
    todos = json.dumps([json.loads(p.read_text(encoding="utf-8")) for p in PASTA_DADOS.glob("*.json")])
    # \w antes do @: pega e-mail, não @perfil de creator.
    dominios = set(re.findall(r"\w@([a-z0-9.-]+\.[a-z]+)", todos))
    assert dominios <= {"example.com", "example.org"}


def _copiar(tmp_path: Path) -> Path:
    destino = tmp_path / "dados com espaço"
    shutil.copytree(PASTA_DADOS, destino)
    return destino


def test_aresta_com_vertice_inexistente_e_rejeitada(tmp_path):
    pasta = _copiar(tmp_path)
    arq = pasta / "arestas.json"
    arestas = json.loads(arq.read_text(encoding="utf-8"))
    arestas.append({"origem": "cr-lu.dicas", "destino": "nao-existe", "rotulo": "divulga"})
    arq.write_text(json.dumps(arestas, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(DadosInvalidos, match="nao-existe"):
        carregar(pasta)


def test_rotulo_desconhecido_e_rejeitado(tmp_path):
    pasta = _copiar(tmp_path)
    arq = pasta / "arestas.json"
    arestas = json.loads(arq.read_text(encoding="utf-8"))
    arestas[0]["rotulo"] = "é amigo de"
    arq.write_text(json.dumps(arestas, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(DadosInvalidos, match="rótulo"):
        carregar(pasta)


def test_chamado_com_autor_inexistente_e_rejeitado(tmp_path):
    pasta = _copiar(tmp_path)
    arq = pasta / "chamados.json"
    chamados = json.loads(arq.read_text(encoding="utf-8"))
    chamados[0]["autor_id"] = "fantasma"
    arq.write_text(json.dumps(chamados, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(DadosInvalidos, match="fantasma"):
        carregar(pasta)


# ---------------------------------------------------------------- regressões (revisão 1)
from sentinela.core.modelos import MOTIVOS_CODIGO  # noqa: E402


def _alterar(tmp_path: Path, nome: str, mudar) -> Path:
    pasta = _copiar(tmp_path)
    arq = pasta / f"{nome}.json"
    dados = json.loads(arq.read_text(encoding="utf-8"))
    dados = mudar(dados)
    arq.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    return pasta


def _primeiro(dados, **campos):
    dados[0].update(campos)
    return dados


def _primeiro_com(_chave, _busca, **campos):
    def mudar(dados):
        alvo = next(d for d in dados if d.get(_chave) == _busca)
        alvo.update(campos)
        return dados

    return mudar


def test_motivos_estruturados(base):
    assert all(r.motivo_codigo in MOTIVOS_CODIGO for r in base.reembolsos)
    reembolsos = [c for c in base.chamados.values() if c.tipo == "reembolso"]
    assert reembolsos and all(c.motivo_codigo in MOTIVOS_CODIGO for c in reembolsos)
    assert any(p.promete for p in base.posts)


def test_rotulo_do_vertice_chamado_e_so_o_id(base):
    for cid in base.chamados:
        assert base.vertices[cid].rotulo == cid


@pytest.mark.parametrize(
    "nome, mudar, trecho",
    [
        ("reembolsos", lambda d: _primeiro(d, motivo_codigo="inventado"), "motivo_codigo"),
        ("vertices", lambda d: d + [dict(d[0])], "repetido"),
        ("chamados", lambda d: d + [dict(d[0])], "repetido"),
        ("reembolsos", lambda d: d + [dict(d[0])], "repetido"),
        ("vertices", lambda d: _primeiro(d, tipo="planeta"), "tipo"),
        ("vertices", _primeiro_com("id", "cr-cupom.fake", fraude_confirmada="sim"), "fraude_confirmada"),
        ("chamados", lambda d: _primeiro(d, valor=-1), "valor"),
        ("chamados", lambda d: _primeiro(d, valor=float("nan")), "valor"),
        ("reembolsos", lambda d: _primeiro(d, valor=float("inf")), "valor"),
        ("reembolsos", lambda d: _primeiro(d, percentual_assistido=1.5), "percentual"),
        ("eventos_saque", _primeiro_com("id", "e-43", valor=9999.0), "saldo"),
        ("posts", lambda d: {"nao": "lista"}, "lista"),
        ("arestas", lambda d: d + ["texto solto"], "objeto"),
    ],
)
def test_validacoes_rejeitam_dado_ruim(tmp_path, nome, mudar, trecho):
    pasta = _alterar(tmp_path, nome, mudar)
    with pytest.raises(DadosInvalidos, match=trecho):
        carregar(pasta)


def test_repr_nao_vaza_dado_sensivel(base):
    for v in base.vertices.values():
        r = repr(v)
        for sensivel in (v.cpf, v.ip, v.chave_pix):
            if sensivel:
                assert sensivel not in r
