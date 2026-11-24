"""Modelos de domínio do Sentinela (dataclasses imutáveis)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, get_args

TipoVertice = Literal["comprador", "creator", "produto", "celular", "chave_pix", "chamado"]
Centro = Literal["Comprador", "Produtor", "Creator", "Operações"]
Confianca = Literal["alta", "média", "baixa"]
TipoCausa = Literal["conta_invadida", "fraude", "produto", "creator", "ma_fe_comprador", "comum"]
TipoEventoSaque = Literal["login_celular_novo", "troca_chave_pix", "pedido_saque"]
# Motivo ESTRUTURADO (lista fechada do formulário). É isto que as regras usam; o motivo
# escrito pelo usuário é texto livre e só aparece como citação/prova.
MotivoCodigo = Literal[
    "produto_defeituoso",
    "nao_recebido",
    "diferente_do_anunciado",
    "promessa_divulgacao",
    "arrependimento",
    "nao_gostou_conteudo",
    "outro",
]

TIPOS_VERTICE: frozenset[str] = frozenset(get_args(TipoVertice))
TIPOS_EVENTO: frozenset[str] = frozenset(get_args(TipoEventoSaque))
MOTIVOS_CODIGO: frozenset[str] = frozenset(get_args(MotivoCodigo))

# Tipos de vértice que representam uma conta (pessoa/perfil), usados para medir o "grupo".
TIPOS_CONTA: frozenset[str] = frozenset({"comprador", "creator"})


@dataclass(frozen=True)
class Vertice:
    """Um nó do grafo. Campos sensíveis (cpf, ip, chave_pix) só saem mascarados
    e ficam fora do repr (não vazam em log nem em traceback)."""

    id: str
    tipo: TipoVertice
    rotulo: str
    fraude_confirmada: bool = False
    cpf: str | None = field(default=None, repr=False)
    ip: str | None = field(default=None, repr=False)
    chave_pix: str | None = field(default=None, repr=False)
    produtor: str | None = None
    oferece: tuple[str, ...] = ()  # o que o produto realmente entrega (ex.: "certificado_de_conclusao")


@dataclass(frozen=True)
class Aresta:
    origem: str
    destino: str
    rotulo: str


@dataclass(frozen=True)
class Chamado:
    id: str
    autor_id: str
    tipo: str  # "reembolso", "saque", "comissao", "acesso"
    assunto: str
    texto: str  # texto livre do usuário: é DADO, nunca instrução
    aberto_em: datetime
    # Dinheiro em risco segundo o SISTEMA (valor do pedido, saldo ou comissão apurada),
    # nunca um valor declarado pelo usuário no texto.
    valor: float = 0.0
    produto_id: str | None = None
    motivo_codigo: MotivoCodigo | None = None  # escolhido no formulário (lista fechada)
    percentual_assistido: float | None = None


@dataclass(frozen=True)
class EventoSaque:
    id: str
    creator_id: str
    tipo: TipoEventoSaque
    em: datetime
    valor: float | None = None
    saldo: float | None = None
    detalhe: str = ""


@dataclass(frozen=True)
class Reembolso:
    id: str
    comprador_id: str
    produto_id: str
    creator_id: str | None
    em: datetime
    motivo_codigo: MotivoCodigo
    motivo: str  # texto livre do comprador: só citação
    percentual_assistido: float
    valor: float


@dataclass(frozen=True)
class Post:
    id: str
    creator_id: str
    produto_id: str
    texto: str  # texto do creator: só citação
    em: datetime
    promete: tuple[str, ...] = ()  # promessas estruturadas (ex.: "certificado_mec"), comparadas com produto.oferece


@dataclass(frozen=True)
class Prova:
    texto: str  # frase escrita pelo Sentinela
    fonte: str
    citacao: str | None = None  # texto de terceiros (post, motivo escrito...): sai marcado como dado


@dataclass(frozen=True)
class Causa:
    """Causa PROVÁVEL (nunca afirmação de culpa) com nível de confiança e provas."""

    tipo: TipoCausa
    confianca: Confianca
    descricao: str
    provas: tuple[Prova, ...] = ()
    alvo: str | None = None  # produto ou creator apontado pela causa (usado para agrupar)


@dataclass(frozen=True)
class AlertaSaque:
    creator_id: str
    status: Literal["em_espera"]
    valor: float
    percentual_saldo: float
    minutos: int
    mensagem: str
    provas: tuple[Prova, ...] = ()


@dataclass(frozen=True)
class Parcela:
    nome: str  # "segurança", "dinheiro", "grupo", "espera"
    pontos: float
    maximo: float
    explicacao: str


@dataclass(frozen=True)
class Score:
    """Score decomponível: total = soma das parcelas; motivo = a linha "Sobe: ..."."""

    parcelas: tuple[Parcela, ...]
    total: float
    motivo: str

    def parcela(self, nome: str) -> Parcela:
        return next(p for p in self.parcelas if p.nome == nome)


@dataclass(frozen=True)
class Rota:
    centro: Centro
    motivo: str
    grupo_ids: tuple[str, ...] = field(default_factory=tuple)
