"""Formatação para a tela. Puro: não importa streamlit (testável com pytest)."""
from __future__ import annotations

import string
import unicodedata
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from typing import Any, Literal

from sentinela.core.dados import AGORA_DEMO
from sentinela.core.injecao import FIM_DADO, INICIO_DADO

HORAS_MAX = 72  # limite do slider "Simular +horas"

NIVEIS: tuple[str, ...] = ("alta", "média", "baixa")  # faixa de prioridade e confiança
_MANTER = frozenset("\n\t")  # controles que continuam: quebra de linha e tab

_CORES_PRIORIDADE = {"alta": "red", "média": "orange", "baixa": "blue"}
_CORES_CONFIANCA = {"alta": "violet", "média": "blue", "baixa": "gray"}

# Toda pontuação ASCII ganha "\" na frente: em CommonMark qualquer pontuação escapada vira
# literal. Isso neutraliza markdown, LaTeX do Streamlit ($...$) e diretivas como :red[...].
_ESCAPES = str.maketrans({c: "\\" + c for c in string.punctuation})


def texto_citado(dado: str | Mapping[str, Any]) -> str:
    """Tira os delimitadores de `como_dado` para exibir o texto em st.code/st.text.

    Só remove a PRIMEIRA linha (abertura) e a ÚLTIMA (fechamento com nonce). Um "fim de dado"
    escrito pelo usuário no meio fica dentro do texto (e o core já trocou os seus < >).
    Aceita também o dict do core {"citacao": ..., "origem": ...}.
    """
    if isinstance(dado, Mapping):
        dado = str(dado.get("citacao", ""))
    linhas = dado.split("\n")
    if len(linhas) >= 2 and linhas[0].startswith(INICIO_DADO) and linhas[-1].startswith(FIM_DADO):
        dado = "\n".join(linhas[1:-1])
    return limpar_texto(dado)


def limpar_texto(texto: str) -> str:
    """Texto que vai para st.text/st.code: tira controles (Cc) e formatação/bidi (Cf).

    Mantém só quebra de linha e tab. Evita, p.ex., U+202E invertendo a leitura de um rótulo.
    """
    return "".join(c for c in str(texto) if c in _MANTER or unicodedata.category(c) not in ("Cc", "Cf"))


def nivel_seguro(valor: str) -> str:
    """Só "alta", "média" ou "baixa" entram numa diretiva :cor-badge[...]; o resto vira "desconhecida"."""
    return valor if valor in NIVEIS else "desconhecida"


def escapar_md(texto: str) -> str:
    """Texto do Sentinela que vai para markdown: escapa toda pontuação e tira quebras de linha."""
    return " ".join(str(texto).split()).translate(_ESCAPES)


def cor_badge(valor: str, tipo: Literal["prioridade", "confianca"] = "prioridade") -> str:
    """Cor do st.badge para a faixa de prioridade ou o nível de confiança."""
    tabela = _CORES_PRIORIDADE if tipo == "prioridade" else _CORES_CONFIANCA
    return tabela.get(valor, "gray")


def agora_simulado(horas: float) -> datetime:
    """Relógio da demo: AGORA_DEMO + horas simuladas (0 a 72)."""
    if not 0 <= horas <= HORAS_MAX:
        raise ValueError(f"horas simuladas fora de 0–{HORAS_MAX}: {horas!r}")
    return AGORA_DEMO + timedelta(hours=horas)


def _numero(valor: float) -> str:
    """21.0 -> '21'; 0.1 -> '0,1' (uma casa, vírgula decimal)."""
    texto = f"{float(valor):.1f}".removesuffix(".0")
    return texto.replace(".", ",")


def linhas_score(parcelas: Iterable[Mapping[str, Any]]) -> list[str]:
    """Uma linha por parcela: 'segurança: 40 de 40 · explicação' (ordem do core)."""
    return [f"{p['nome']}: {_numero(p['pontos'])} de {_numero(p['maximo'])} · {p['explicacao']}" for p in parcelas]
