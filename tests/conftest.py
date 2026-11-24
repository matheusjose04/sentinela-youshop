"""Fixtures compartilhadas: base fictícia carregada de data/ e um 'agora' fixo."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

PASTA_DADOS = Path(__file__).resolve().parent.parent / "data"


def textos_das_provas(provas) -> str:
    """Frases do Sentinela + citações (dados de terceiros) numa string só, para os asserts."""
    return " | ".join(p["texto"] + " " + p.get("citacao", "") for p in provas)


@pytest.fixture(scope="session")
def agora() -> datetime:
    from sentinela.core.dados import AGORA_DEMO

    return AGORA_DEMO


@pytest.fixture(scope="session")
def base():
    from sentinela.core.dados import carregar

    return carregar(PASTA_DADOS)
