"""Proteção do saque: sinal clássico de conta invadida.

Login de celular novo + troca de chave Pix + pedido de saque de quase todo o saldo,
tudo em poucos minutos. Resultado: saque "em espera" para revisão humana.
Nada é feito automaticamente; quem decide é o atendente.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sentinela.core.fila import formatar_brl
from sentinela.core.modelos import AlertaSaque, EventoSaque, Prova

if TYPE_CHECKING:
    from sentinela.core.dados import Base

JANELA_PADRAO = timedelta(minutes=30)
PERCENTUAL_MINIMO = 0.90  # saque de 90% do saldo ou mais
FONTE = "eventos da conta (eventos_saque)"


def _hora(ev: EventoSaque) -> str:
    return ev.em.strftime("%H:%M")


def avaliar_saque(
    creator_id: str, eventos: Iterable[EventoSaque], janela: timedelta = JANELA_PADRAO
) -> AlertaSaque | None:
    """Procura um pedido de saque quase total precedido, dentro da janela, pelos dois sinais."""
    meus = sorted((e for e in eventos if e.creator_id == creator_id), key=lambda e: e.em)
    for saque in (e for e in meus if e.tipo == "pedido_saque"):
        if not saque.valor or not saque.saldo:
            continue
        percentual = saque.valor / saque.saldo
        if percentual + 1e-9 < PERCENTUAL_MINIMO:
            continue
        # Só contam sinais ANTES do saque e dentro da janela.
        antes = [e for e in meus if saque.em - janela <= e.em <= saque.em and e is not saque]
        login = next((e for e in reversed(antes) if e.tipo == "login_celular_novo"), None)
        troca = next((e for e in reversed(antes) if e.tipo == "troca_chave_pix"), None)
        if login is None or troca is None:
            continue
        inicio = min(login.em, troca.em)
        minutos = int((saque.em - inicio).total_seconds() // 60)
        provas = (
            # `detalhe` vem do registro do evento: vai como citação (dado), não como frase nossa.
            Prova(f"Login de celular novo às {_hora(login)}", FONTE, login.detalhe or None),
            Prova(f"Chave Pix trocada às {_hora(troca)}", FONTE, troca.detalhe or None),
            Prova(
                f"Pedido de saque de {formatar_brl(saque.valor)} ({percentual:.0%} do saldo) às {_hora(saque)}", FONTE
            ),
        )
        mensagem = (
            f"Saque de {formatar_brl(saque.valor)} em espera para revisão humana: celular novo + chave Pix "
            f"trocada + saque de {percentual:.0%} do saldo em {minutos} min. Nenhuma ação automática foi tomada."
        )
        return AlertaSaque(
            creator_id=creator_id,
            status="em_espera",
            valor=saque.valor,
            percentual_saldo=round(percentual, 4),
            minutos=minutos,
            mensagem=mensagem,
            provas=provas,
        )
    return None


def listar_alertas_saque(base: Base, agora: datetime | None = None) -> list[AlertaSaque]:
    """Avalia todo creator que tem eventos; só eventos até `agora` contam.

    Saída CRUA (sem máscara): a UI e o MCP usam caso.alertas_saque_para_saida.
    """
    eventos = [e for e in base.eventos_saque if agora is None or e.em <= agora]
    creators = sorted({e.creator_id for e in eventos})
    alertas = (avaliar_saque(c, eventos) for c in creators)
    return [a for a in alertas if a is not None]
