"""Máscaras de dados sensíveis: CPF, IP, chave Pix e texto livre."""
import re

from sentinela.core.mascara import (
    mascarar_chave_pix,
    mascarar_cpf,
    mascarar_ip,
    mascarar_texto,
)


def test_cpf_com_e_sem_pontuacao():
    assert mascarar_cpf("123.456.789-00") == "***.456.789-**"
    assert mascarar_cpf("12345678900") == "***.456.789-**"


def test_ip_esconde_final():
    assert mascarar_ip("192.0.2.15") == "192.0.*.*"
    assert mascarar_ip("198.51.100.23") == "198.51.*.*"


def test_chave_pix_email():
    assert mascarar_chave_pix("repasse.promo@example.com") == "r***@example.com"


def test_chave_pix_telefone():
    assert mascarar_chave_pix("+55 11 98765-4321").endswith("4321")
    assert "98765" not in mascarar_chave_pix("+55 11 98765-4321")


def test_chave_pix_cpf():
    assert mascarar_chave_pix("123.456.789-00") == "***.456.789-**"


def test_chave_pix_aleatoria():
    chave = "7f3c9a12-4b5e-4c6d-8e9f-0a1b2c3d9f3c"
    m = mascarar_chave_pix(chave)
    assert m.startswith("7f3c") and m.endswith("9f3c")
    assert chave not in m


def test_texto_livre_mascara_tudo():
    texto = (
        "Meu CPF é 123.456.789-00, IP 192.0.2.15, e-mail ana.f@example.com, "
        "celular +55 11 98765-4321 e chave 7f3c9a12-4b5e-4c6d-8e9f-0a1b2c3d9f3c."
    )
    m = mascarar_texto(texto)
    assert not re.search(r"\d{3}\.\d{3}\.\d{3}-\d{2}", m)
    assert not re.search(r"\d+\.\d+\.\d+\.\d+", m)
    assert "ana.f@" not in m
    assert "98765" not in m
    assert "7f3c9a12-4b5e" not in m


def test_texto_sem_dado_sensivel_fica_igual():
    texto = "Saque de R$ 4.200 em 12 min, aberto em 2026-11-20T14:40:00-03:00."
    assert mascarar_texto(texto) == texto


# ---------------------------------------------------------------- regressões (revisão 1)
import time  # noqa: E402

import pytest  # noqa: E402


@pytest.mark.parametrize(
    "entrada",
    ["a." * 50000, "a" * 100000 + "@", ("x" * 63 + "@") * 1500, "1." * 50000, "1 " * 50000, "ab:" * 33000],
)
def test_sem_redos_em_texto_grande(entrada):
    inicio = time.perf_counter()
    mascarar_texto(entrada)
    assert time.perf_counter() - inicio < 0.2


@pytest.mark.parametrize(
    "texto",
    [
        "CPF 123 456 789 00",
        "CPF 123.456.789 00",
        "CPF.12345678900",
        "item1.123.456.789-00",
        "doc:12345678900fim",
        "1​2​3.456.789-00",  # invisíveis entre dígitos
        "１２３.４５６.７８９-００",  # dígitos fullwidth
    ],
)
def test_cpf_em_formatos_variados(texto):
    m = mascarar_texto(texto)
    assert "789-00" not in m and "78900" not in m and "789 00" not in m, m
    assert "12345678900" not in m.replace(".", "").replace("-", "").replace(" ", "")


@pytest.mark.parametrize(
    "texto, final",
    [
        ("fixo (11) 3456-7890", "7890"),
        ("cel 11 98765 4321", "4321"),
        ("cel +5511987654321", "4321"),
        ("cel +55 (11) 98765-4321", "4321"),
        ("sem DDD 98765-4321", "4321"),
        ("fixo sem DDD 3456-7890", "7890"),
    ],
)
def test_telefones(texto, final):
    m = mascarar_texto(texto)
    assert m.endswith(final)
    digitos = "".join(c for c in m if c.isdigit())
    assert len(digitos) <= 4 + 2, m  # só os 4 finais (+ "55" no máximo)


def test_cnpj():
    m = mascarar_texto("CNPJ 12.345.678/0001-95 e 12345678000195")
    assert "12.345.678" not in m and "12345678000195" not in m


def test_chave_aleatoria_sem_hifen():
    chave = "7f3c9a124b5e4c6d8e9f0a1b2c3d9f3c"
    assert chave not in mascarar_texto(f"pix {chave}")
    assert chave not in mascarar_chave_pix(chave)


@pytest.mark.parametrize("ip", ["2001:0db8:85a3:0000:0000:8a2e:0370:7334", "2001:db8::8a2e:370:7334", "fe80::1ff:fe23:4567:890a"])
def test_ipv6(ip):
    assert ip not in mascarar_texto(f"ip {ip} ok")


def test_horario_e_data_nao_viram_ipv6_nem_telefone():
    texto = "aberto 2026-11-20T14:40:00-03:00, às 14:20 e 20/11 14:32; saque de R$ 4.200"
    assert mascarar_texto(texto) == texto


def test_fallback_da_chave_pix_nao_vaza_nada():
    assert mascarar_chave_pix("chave-estranha-1234") == "***"


# ---------------------------------------------------------------- revisão da Etapa 3: separadores e IPv4 mapeado
@pytest.mark.parametrize("texto", ["123\n456\n789\n00", "123_456_789_00", "123\t456 789_00", "123 _456.789-00"])
def test_cpf_com_quebra_de_linha_ou_sublinhado_e_mascarado(texto):
    from sentinela.core.mascara import mascarar_texto

    saida = mascarar_texto(f"CPF {texto} fim")
    assert "***.456.789-**" in saida
    assert "00 fim" not in saida.replace("-**", "")


def test_ipv4_mapeado_em_ipv6_e_mascarado():
    from sentinela.core.mascara import mascarar_texto

    saida = mascarar_texto("acesso de ::ffff:192.0.2.15 agora")
    assert "192.0.2.15" not in saida
    assert "2.15" not in saida


def test_numeros_curtos_continuam_legiveis():
    from sentinela.core.mascara import mascarar_texto

    assert mascarar_texto("R$ 4.200 em 12 min") == "R$ 4.200 em 12 min"


@pytest.mark.parametrize(
    "texto",
    [
        "CPF 123.456.789-00, IP 192.0.2.15, tel (11) 98765-4321",
        "123\n456\n789\n00 e 123_456_789_00",
        "chave 7f3c2a10-1b2c-4d5e-8f90-123456789f3c e ana@example.com",
        "::ffff:192.0.2.15 e 2001:db8::1",
        "4200 4200 / 12.345.678/0001-90",
    ],
)
def test_mascarar_texto_e_idempotente(texto):
    from sentinela.core.mascara import mascarar_texto

    uma = mascarar_texto(texto)
    assert mascarar_texto(uma) == uma
