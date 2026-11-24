"""Máscaras de dados sensíveis (LGPD): nada de CPF, CNPJ, IP, telefone ou chave Pix completos na tela.

Todas as regex têm quantificadores limitados (sem backtracking explosivo / ReDoS).
Na dúvida, mascara: é melhor esconder um número inocente do que mostrar um CPF.
"""
from __future__ import annotations

import re
import unicodedata

from sentinela.core.modelos import Vertice

LIMITE_TEXTO = 5000
AVISO_TRUNCADO = " [texto truncado]"

_RE_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b|\b[0-9a-fA-F]{32}\b"
)
# E-mail: só começa onde o caractere anterior NÃO pode ser do e-mail (evita testar cada
# posição de um "a.a.a.a..." gigante) e cada parte tem tamanho máximo.
_RE_EMAIL = re.compile(
    r"(?<![A-Za-z0-9._%+-])([A-Za-z0-9])[A-Za-z0-9._%+-]{0,63}@"
    r"([A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63}){0,8}\.[A-Za-z]{2,24})\b"
)
_RE_IPV4 = re.compile(r"\b(\d{1,3})\.(\d{1,3})\.\d{1,3}\.\d{1,3}\b")
_RE_IPV6 = re.compile(r"(?<![\w:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![\w:])")
# Sequência de dígitos com separadores curtos entre eles (" ", ".", "-", "/", "(", ")").
# Cada repetição consome obrigatoriamente um dígito: casamento linear.
_RE_NUMERO = re.compile(r"[+(]?\d(?:[ .\-/()]{0,2}\d)*")
_RE_TELEFONE = re.compile(r"(?:\+?55 ?)?(?:\(?\d{2}\)? ?)?9?\d{4}[- ]?\d{4}")


def _limpar(texto: str) -> str:
    """NFKC (dígitos fullwidth viram comuns) + remove invisíveis (categoria Cf) entre dígitos."""
    texto = unicodedata.normalize("NFKC", texto)
    return "".join(c for c in texto if unicodedata.category(c) != "Cf")


def _so_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto)


def truncar(texto: str, limite: int = LIMITE_TEXTO) -> str:
    """Corta texto de terceiros muito longo, avisando que cortou."""
    return texto if len(texto) <= limite else texto[:limite] + AVISO_TRUNCADO


def mascarar_cpf(cpf: str) -> str:
    """'123.456.789-00' -> '***.456.789-**' (mostra só o miolo, padrão gov.br)."""
    d = _so_digitos(_limpar(cpf))
    if len(d) != 11:
        return "***"
    return f"***.{d[3:6]}.{d[6:9]}-**"


def _mascarar_cnpj(d: str) -> str:
    return f"**.***.***/{d[8:12]}-**"


def _mascarar_telefone(tel: str) -> str:
    return f"(**) *****-{_so_digitos(tel)[-4:]}"


def mascarar_ip(ip: str) -> str:
    """'192.0.2.15' -> '192.0.*.*'; IPv6 mostra só o primeiro bloco."""
    ip = _limpar(ip).strip()
    m = _RE_IPV4.fullmatch(ip)
    if m:
        return f"{m.group(1)}.{m.group(2)}.*.*"
    if ":" in ip:
        return ip.split(":")[0] + ":****:****"
    return "*.*.*.*"


def _mascarar_email(m: re.Match[str]) -> str:
    return f"{m.group(1)}***@{m.group(2)}"


def _mascarar_uuid(chave: str) -> str:
    return f"{chave[:4]}***{chave[-4:]}"


def _mascarar_ipv6(m: re.Match[str]) -> str:
    s = m.group(0)
    # Hora "14:40:00" tem só 2 dois-pontos e nenhum "::": não é IPv6.
    parece_ipv6 = ("::" in s or s.count(":") >= 4) and any(c in "0123456789abcdefABCDEF" for c in s)
    return mascarar_ip(s) if parece_ipv6 else s


def _mascarar_numero(m: re.Match[str]) -> str:
    """Classifica a sequência de dígitos: telefone, CPF (11), CNPJ (14), outro longo, ou inofensivo."""
    s = m.group(0)
    d = _so_digitos(s)
    if _RE_TELEFONE.fullmatch(s.strip()):
        return _mascarar_telefone(s)
    if len(d) == 11:
        return mascarar_cpf(d)
    if len(d) == 14:
        return _mascarar_cnpj(d)
    if len(d) >= 11:
        return f"***{d[-2:]}"
    return s


def mascarar_chave_pix(chave: str) -> str:
    """Detecta o tipo da chave Pix (aleatória, e-mail, telefone, CPF, CNPJ) e mascara. Senão, '***'."""
    chave = _limpar(chave).strip()
    if _RE_UUID.fullmatch(chave):
        return _mascarar_uuid(chave)
    m = _RE_EMAIL.fullmatch(chave)
    if m:
        return _mascarar_email(m)
    d = _so_digitos(chave)
    if _RE_TELEFONE.fullmatch(chave) or (chave.startswith("+") and len(d) >= 10):
        return _mascarar_telefone(chave)
    if len(d) == 11 and len(d) >= len(chave) - 3:
        return mascarar_cpf(d)
    if len(d) == 14 and len(d) >= len(chave) - 4:
        return _mascarar_cnpj(d)
    return "***"


def rotulo_seguro(v: Vertice) -> str:
    """Rótulo do vértice para a tela; chave Pix aparece só mascarada."""
    if v.chave_pix:
        return f"{v.rotulo} {mascarar_chave_pix(v.chave_pix)}"
    return v.rotulo


def mascarar_texto(texto: str) -> str:
    """Mascara chave aleatória, e-mail, IPv6, IPv4, telefone, CPF e CNPJ dentro de texto livre."""
    texto = _limpar(texto)
    texto = _RE_UUID.sub(lambda m: _mascarar_uuid(m.group(0)), texto)
    texto = _RE_EMAIL.sub(_mascarar_email, texto)
    texto = _RE_IPV6.sub(_mascarar_ipv6, texto)
    texto = _RE_IPV4.sub(lambda m: f"{m.group(1)}.{m.group(2)}.*.*", texto)
    return _RE_NUMERO.sub(_mascarar_numero, texto)
