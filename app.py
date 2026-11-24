"""Sentinela: tela do atendente (Streamlit). Só layout e chamadas; a lógica está no core.

Regras desta tela:
- O caso montado NUNCA mostra sugestão do que fazer: causa provável, provas, alertas e rota.
- Texto de terceiros e texto digitado pelo atendente só vão para st.text ou st.code
  (limpos de controles/bidi), nunca para markdown, rótulos de widget ou HTML.
- Frases do Sentinela que vão para markdown passam antes por `escapar_md`.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import streamlit as st

from sentinela.core.caso import (
    AVISO,
    alertas_saque_para_saida,
    analisar,
    grafo_do_chamado,
    grupos_dos_chamados,
    montar_caso,
    montar_fila,
    resumo_do_caso,
)
from sentinela.core.dados import AGORA_DEMO, carregar
from sentinela.core.dados import assinatura as _assinatura_core
from sentinela.ui.agrupamento import agrupar_fila
from sentinela.ui.acoes import CENTROS, centros_para_devolver, registrar_acao, status_do_chamado
from sentinela.ui.formatacao import (
    HORAS_MAX,
    agora_simulado,
    cor_badge,
    escapar_md,
    limpar_texto,
    linhas_score,
    nivel_seguro,
    texto_citado,
    tooltip_origem,
)
from sentinela.ui.grafo_html import ALTURA_PX, TIPO_VISUAL, html_do_grafo

STATUS_SAQUE = {"em_espera": "em espera, revisão humana"}
# Texto de terceiros ganha um ícone com tooltip. O tooltip é uma das constantes de
# formatacao (cliente / creator / texto de fora), escolhida pela fonte que o core informa.
ICONE_ORIGEM = ":material/person_edit:"
# ?chamado=ch-301 na URL: só formato fixo, curto e ASCII. Usado com fullmatch, porque
# com match o "$" aceitaria uma quebra de linha no fim.
PADRAO_LINK = re.compile(r"^ch-[0-9]{3,6}$")
LINK_MAX = 20
AVISO_DEVOLVER = "aviso_devolver"  # {"chamado": id, "ok": bool}, mostrado uma vez depois do form

# CSS 100% estático (nenhum texto de usuário).
# DOM (mobile-first, também a ordem de leitura e de Tab): fila → caso → grafo.
# Desktop (≥ 641px): `order` mostra fila | grafo | caso. Celular: colunas empilhadas na ordem
# do DOM, e a lista da fila ganha altura máxima com rolagem própria, para o caso aberto
# ficar logo abaixo sem rolar a fila inteira.
CSS = """
<style>
@media (min-width: 641px) {
  .st-key-layout [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2) { order: 3; }
  .st-key-layout [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(3) { order: 2; }
}
@media (max-width: 640px) {
  .st-key-fila_itens { max-height: 55vh; overflow-y: auto; }
}
</style>
"""


# ---------------------------------------------------------------- cache (chaves sempre string)
def _assinatura() -> str:
    """Assinatura de data/*.json (core: nome, mtime, tamanho): mudou o JSON, muda a chave do cache."""
    return _assinatura_core()


@st.cache_resource(max_entries=2)
def _base(assinatura: str):
    return carregar()


@st.cache_resource(max_entries=32)
def _analise(assinatura: str, agora_iso: str):
    """Uma análise por instante: caso e grafo de todos os chamados reaproveitam."""
    return analisar(_base(assinatura), datetime.fromisoformat(agora_iso))


@st.cache_data(max_entries=128)
def _fila(assinatura: str, agora_iso: str, centro: str) -> dict[str, Any]:
    agora = datetime.fromisoformat(agora_iso)
    return montar_fila(_base(assinatura), agora, None if centro == "Todos" else centro)


# caso e grafo em cache_resource: não copia o HTML grande a cada rerun (são só lidos, nunca alterados).
@st.cache_resource(max_entries=128)
def _caso(assinatura: str, agora_iso: str, chamado_id: str) -> dict[str, Any]:
    agora = datetime.fromisoformat(agora_iso)
    return montar_caso(chamado_id, _base(assinatura), agora, analise=_analise(assinatura, agora_iso))


@st.cache_resource(max_entries=24)
def _grafo(assinatura: str, agora_iso: str, chamado_id: str) -> tuple[dict[str, Any], str]:
    agora = datetime.fromisoformat(agora_iso)
    grafo = grafo_do_chamado(chamado_id, _base(assinatura), agora, analise=_analise(assinatura, agora_iso))
    return grafo, html_do_grafo(grafo)


@st.cache_resource(max_entries=128)
def _resumo(assinatura: str, agora_iso: str, chamado_id: str) -> dict[str, Any]:
    agora = datetime.fromisoformat(agora_iso)
    return resumo_do_caso(chamado_id, _base(assinatura), agora, analise=_analise(assinatura, agora_iso))


@st.cache_data(max_entries=32)
def _grupos(assinatura: str, agora_iso: str) -> dict[str, Any]:
    agora = datetime.fromisoformat(agora_iso)
    return grupos_dos_chamados(_base(assinatura), agora, analise=_analise(assinatura, agora_iso))["grupos"]


@st.cache_data(max_entries=128)
def _saques(assinatura: str, agora_iso: str) -> dict[str, Any]:
    return alertas_saque_para_saida(_base(assinatura), datetime.fromisoformat(agora_iso))


# ---------------------------------------------------------------- link
def _chamado_do_link(existentes: Any) -> str | None:
    """Id vindo de ?chamado=, se válido e existente na base; senão None (ignorado em silêncio)."""
    valor = st.query_params.get("chamado")
    if not isinstance(valor, str) or len(valor) > LINK_MAX:
        return None  # tamanho antes da regex: nada grande chega ao re
    if not PADRAO_LINK.fullmatch(valor) or valor not in existentes:
        return None
    return valor


def _selecao_inicial(assinatura: str) -> None:
    """O link só vale enquanto o atendente não escolheu nada; depois o clique prevalece."""
    if "chamado_escolhido" in st.session_state:
        return
    cid = _chamado_do_link(_base(assinatura).chamados)
    if cid is not None:
        st.session_state["chamado_escolhido"] = cid


# ---------------------------------------------------------------- ações (callbacks: rodam ANTES do script)
def _abrir(chamado_id: str) -> None:
    st.session_state["chamado_escolhido"] = chamado_id
    # A URL acompanha o caso aberto: quem copiar o link compartilha o caso que está na tela.
    # O id veio da própria fila (já validado), nunca do usuário.
    st.query_params["chamado"] = chamado_id


def _registrar(**campos: Any) -> None:
    st.session_state["acoes"] = registrar_acao(st.session_state.get("acoes", []), **campos)


def _resolver(chamado_id: str, centro: str, em: datetime) -> None:
    _registrar(tipo="resolvido", chamado_id=chamado_id, centro=centro, em=em)


def _encaminhar(chamado_id: str, centro: str, em: datetime) -> None:
    chave = f"obs_{chamado_id}"
    _registrar(tipo="encaminhado", chamado_id=chamado_id, centro=centro, em=em,
               observacao=st.session_state.get(chave, ""))
    st.session_state[chave] = ""


def _devolver(chamado_id: str, centro: str, em: datetime) -> None:
    """Lê destino e motivo do form; só grava (e limpa o motivo) se o motivo não estiver vazio."""
    chave_motivo = f"devolver_motivo_{chamado_id}"
    motivo = st.session_state.get(chave_motivo, "")
    if not motivo.strip():
        st.session_state[AVISO_DEVOLVER] = {"chamado": chamado_id, "ok": False}
        return
    _registrar(tipo="devolvido", chamado_id=chamado_id, centro=centro, em=em,
               destino=st.session_state.get(f"devolver_centro_{chamado_id}"), observacao=motivo)
    st.session_state[chave_motivo] = ""
    st.session_state[AVISO_DEVOLVER] = {"chamado": chamado_id, "ok": True}


# ---------------------------------------------------------------- pedaços da tela
def _texto(texto: str) -> None:
    """Texto de terceiros ou do atendente em texto puro, sem controles nem bidi."""
    st.text(limpar_texto(texto))


def _origem(fonte: str = "cliente") -> None:
    """Ícone de origem com tooltip estático (cliente, creator ou texto de fora), abaixo de um texto de terceiros."""
    st.caption(ICONE_ORIGEM, help=tooltip_origem(fonte))


def _citacao(dado: Any, fonte: str = "cliente") -> None:
    """Texto de terceiros: só em st.code, com o ícone de origem."""
    st.code(texto_citado(dado), language=None, wrap_lines=True)
    _origem(fonte)


def _prova(prova: dict[str, Any]) -> None:
    st.markdown(f"- {escapar_md(prova['texto'])}")
    st.caption(f"fonte: {escapar_md(prova['fonte'])}")
    if prova.get("citacao"):
        _citacao(prova["citacao"], prova["fonte"])


def _topo() -> tuple[str, int, Any]:
    """Título, selo, filtros. Devolve também o lugar (no topo) da contagem "X chamados → Y causas"."""
    st.title("Sentinela")
    st.badge(AVISO, icon=":material/science:", color="orange")
    contagem = st.empty()
    c_centro, c_horas = st.columns([1, 2])
    centro = c_centro.selectbox("Centro de atendimento", ["Todos", *CENTROS], key="centro")
    horas = c_horas.slider("Simular +horas", 0, HORAS_MAX, 0, step=1, key="horas")
    agora = agora_simulado(horas)
    st.caption(
        f"Relógio da demo: {AGORA_DEMO:%d/%m/%Y %H:%M} (fixo, os dados fictícios foram escritos em torno dele)"
        f" · agora efetivo: {agora:%d/%m/%Y %H:%M}"
    )
    return centro, horas, contagem


def _contagem(lugar: Any, n_chamados: int, n_causas: int) -> None:
    lugar.markdown(f"**{n_chamados} chamados → {n_causas} causas** · chamados com a mesma causa ficam juntos na fila")


def _faixa_saques(saques: dict[str, Any]) -> None:
    for item in saques["itens"]:
        status = STATUS_SAQUE.get(item["status"], item["status"])
        st.warning(
            f"**Saque {escapar_md(status)}** · {escapar_md(item['creator'])} · {escapar_md(item['valor'])}"
            f" · {escapar_md(item['mensagem'])}",
            icon=":material/pause_circle:",
        )
        with st.expander("Provas do alerta de saque"):
            for prova in item["provas"]:
                _prova(prova)


def _badge(item: dict[str, Any]) -> str:
    faixa = nivel_seguro(item["faixa"])
    return f":{cor_badge(faixa)}-badge[{faixa} · {item['total']:.0f}]"


def _popover_score(item: dict[str, Any]) -> None:
    with st.popover("Score"):
        st.markdown(f"**Total: {escapar_md(str(item['total']))} de 100**")
        for linha in linhas_score(item["parcelas"]):
            st.markdown(escapar_md(linha))


def _botao_abrir(chave: str, chamado_id: str, ativo: bool, rotulo: str = "Abrir caso") -> None:
    st.button(rotulo, key=chave, on_click=_abrir, args=(chamado_id,), type="primary" if ativo else "secondary")


def _alertas_da_fila(alertas: list[dict[str, Any]], com_botao: bool) -> None:
    """Alertas de qualquer membro, fora do expander: frase fixa do core + ids da base (escapados)."""
    for alerta in alertas:
        if alerta["tipo"] == "injecao":
            st.error(escapar_md(alerta["texto"]), icon=":material/report:")
        else:
            st.warning(escapar_md(alerta["texto"]), icon=":material/pause_circle:")
        if com_botao:
            prefixo = "alerta_abrir_" if alerta["tipo"] == "injecao" else "alerta_saque_abrir_"
            for cid in alerta["ids"]:
                st.button(f"Abrir caso {cid}", key=f"{prefixo}{cid}", on_click=_abrir, args=(cid,))


def _item_fila(
    item: dict[str, Any], selecionado: str, acoes: list[dict[str, Any]], alertas: list[dict[str, Any]] | None = None
) -> None:
    """Chamado isolado (nenhum outro com a mesma causa)."""
    with st.container(border=True):
        st.markdown(f"{_badge(item)} **{escapar_md(item['id'])}**")
        st.caption(
            f"na fila · {escapar_md(item['id'])} · {escapar_md(item['centro'])}"
            f" · esperando {escapar_md(item['esperando'])}"
            f" · status: {escapar_md(status_do_chamado(acoes, item['id']))}"
        )
        st.text(texto_citado(item["assunto"]))
        _origem()
        st.caption(escapar_md(item["motivo"]))
        _alertas_da_fila(alertas or [], com_botao=False)  # o próprio "Abrir caso" já abre este chamado
        with st.container(horizontal=True):
            _popover_score(item)
            _botao_abrir(f"abrir_{item['id']}", item["id"], item["id"] == selecionado)


def _grupo_fila(grupo: dict[str, Any], selecionado: str, acoes: list[dict[str, Any]]) -> None:
    """Vários chamados com a mesma causa: um item só, com o score do maior (o líder)."""
    lider, membros = grupo["lider"], grupo["membros"]
    with st.container(border=True):
        st.markdown(f"{_badge(grupo)} **{escapar_md(grupo['titulo'])}**")
        st.caption(
            f"na fila · {escapar_md(grupo['centro'])} · maior espera {escapar_md(grupo['esperando'])}"
            f" · caso do grupo: {escapar_md(lider['id'])}"
        )
        st.caption(escapar_md(grupo["motivo"]))
        _alertas_da_fila(grupo["alertas"], com_botao=True)
        with st.container(horizontal=True):
            _popover_score(lider)
            _botao_abrir(f"abrir_grupo_{lider['id']}", lider["id"], any(m["id"] == selecionado for m in membros))
        with st.expander(f"Chamados do grupo ({len(membros)})"):
            for m in membros:
                st.markdown(f"{_badge(m)} **{escapar_md(m['id'])}**")
                st.caption(
                    f"na fila · {escapar_md(m['id'])} · esperando {escapar_md(m['esperando'])}"
                    f" · status: {escapar_md(status_do_chamado(acoes, m['id']))}"
                )
                st.text(texto_citado(m["assunto"]))
                _origem()
                st.caption(escapar_md(m["motivo"]))
                _botao_abrir(f"abrir_{m['id']}", m["id"], m["id"] == selecionado, f"Abrir caso {m['id']}")


def _coluna_fila(grupos: list[dict[str, Any]], selecionado: str | None, acoes: list[dict[str, Any]]) -> None:
    st.subheader("Fila")
    if not grupos:
        st.info("Nenhum chamado na fila deste centro.")
        return
    st.caption("Do maior score para o menor (heap); um grupo assume o maior score. Chamados antigos sobem com o tempo.")
    with st.container(key="fila_itens"):
        for grupo in grupos:
            if grupo["titulo"] is None:
                _item_fila(grupo["lider"], selecionado or "", acoes, grupo["alertas"])
            else:
                _grupo_fila(grupo, selecionado or "", acoes)


def _legenda() -> None:
    # cor_st e icone são constantes do código (TIPO_VISUAL); o nome também, mas passa por escapar_md.
    tipos = " · ".join(
        f":{v['cor_st']}[:material/{v['icone']}: {escapar_md(v['nome'])}]" for v in TIPO_VISUAL.values()
    )
    st.markdown(tipos)
    st.caption(
        "Borda vermelha grossa: fraude confirmada · linha vermelha: caminho até a fraude"
        " · cinza: produto fora do grupo (só contexto) · maior: chamado aberto"
    )


def _coluna_grafo(assinatura: str, agora_iso: str, chamado_id: str) -> None:
    st.subheader("Grafo de ligações")
    grafo, html = _grafo(assinatura, agora_iso, chamado_id)
    # Resumo da distância sempre visível; o desenho e o caminho ficam em expanders fechados.
    texto = escapar_md(grafo["distancia_texto"])
    st.markdown(f":red[**{texto}**]" if grafo["ligacoes_ate_fraude"] is not None else f"**{texto}**")
    with st.expander(f"Ver o grafo ({len(grafo['vertices'])} vértices)", icon=":material/hub:"):
        # O HTML do grafo faz fit() no 1º resize com tamanho real (o iframe nasce com largura 0 aqui).
        st.iframe(html, height=ALTURA_PX + 20)
        _legenda()
    caminho = _caso(assinatura, agora_iso, chamado_id)["distancia_fraude"]["caminho"]
    if caminho:
        with st.expander("Caminho mais curto até a fraude (Dijkstra)", icon=":material/route:"):
            _texto(" → ".join(caminho))


def _historico(h: dict[str, Any]) -> None:
    with st.expander("Histórico do cliente"):
        linhas = [
            f"conta: {h['conta']} ({h['tipo']})",
            f"CPF: {h['cpf']} · último IP: {h['ultimo_ip']}",
            f"reembolsos nos últimos 30 dias: {h['reembolsos_30_dias']} (total: {h['reembolsos_total']})",
            f"chamados desta conta: {', '.join(h['chamados_do_autor']) or 'nenhum'}",
        ]
        _texto("\n".join(linhas))
        if h["eventos_da_conta"]:
            st.caption("Eventos da conta")
            _texto("\n".join(h["eventos_da_conta"]))
        if h["ligacoes_no_grafo"]:
            st.caption("Ligações no grafo")
            _texto("\n".join(h["ligacoes_no_grafo"]))


def _alerta_seguranca(alerta: Any) -> None:
    if alerta == "nenhum":
        st.info("Alerta de segurança: nenhum", icon=":material/verified_user:")
        return
    st.warning(f"**Alerta de segurança** · {escapar_md(alerta['mensagem'])}", icon=":material/shield:")
    if alerta.get("lembrete"):
        st.info(escapar_md(alerta["lembrete"]), icon=":material/gavel:")


def _rota(caso: dict[str, Any]) -> None:
    rota = caso["rota"]
    st.markdown(f"**Roteado para:** {escapar_md(rota['centro'])}")
    st.caption("Por que este centro")
    st.markdown(escapar_md(rota["motivo"]))
    st.caption(escapar_md(rota["grupo_texto"]))
    if len(rota["grupo_ids"]) > 1:
        _texto("Chamados do grupo: " + ", ".join(rota["grupo_ids"]))


def _acoes_do_atendente(chamado_id: str, centro: str, agora: datetime) -> None:
    st.markdown("**Ações do atendente**")
    st.button("Marcar como resolvido", key=f"resolver_{chamado_id}", on_click=_resolver, args=(chamado_id, centro, agora))
    st.text_input("Observação para encaminhar", key=f"obs_{chamado_id}", max_chars=500)
    st.button("Encaminhar", key=f"encaminhar_{chamado_id}", on_click=_encaminhar, args=(chamado_id, centro, agora))
    # Sem clear_on_submit: o callback só limpa o motivo quando a devolução é válida.
    with st.form(f"devolver_{chamado_id}"):
        st.markdown("**Devolver para outro centro**")
        st.selectbox("Centro de destino", centros_para_devolver(centro), key=f"devolver_centro_{chamado_id}")
        st.text_area("Motivo (feedback do roteamento)", key=f"devolver_motivo_{chamado_id}", max_chars=500)
        st.form_submit_button(
            "Devolver para outro centro",
            key=f"devolver_enviar_{chamado_id}",
            on_click=_devolver,
            args=(chamado_id, centro, agora),
        )
    aviso = st.session_state.get(AVISO_DEVOLVER)
    if aviso and aviso["chamado"] == chamado_id:
        if aviso["ok"]:
            st.success("Devolução registrada nesta sessão.")
        else:
            st.warning("Escreva o motivo para devolver.")
        del st.session_state[AVISO_DEVOLVER]  # aparece uma vez só


def _registro_da_sessao(acoes: list[dict[str, Any]]) -> None:
    with st.expander(f"Registro da sessão ({len(acoes)})"):
        if not acoes:
            st.caption("Nenhuma ação registrada ainda.")
        for a in reversed(acoes):
            destino = f" → {a['destino']}" if a["destino"] else ""
            _texto(f"{a['em'][:16].replace('T', ' ')} · {a['chamado_id']} · {a['tipo']}{destino} ({a['centro']})")
            if a["observacao"]:
                _texto(f"   {a['observacao']}")


def _cartao_resumo(r: dict[str, Any]) -> None:
    """4 linhas para entender o caso em 10 segundos. Só fatos: nenhuma sugestão de decisão."""
    # Ponto de extensão (fora do protótipo): com chave em st.secrets, um LLM poderia só REESCREVER
    # r["causa"] em linguagem simples, recebendo o texto do usuário delimitado como dado.
    # Nunca decide, nunca muda causa, rota ou score. No deploy público fica desligado.
    confianca = nivel_seguro(r["confianca"])
    with st.container(border=True, key="cartao_resumo"):
        st.markdown(
            f":{cor_badge(confianca, 'confianca')}-badge[confiança {confianca}]"
            f" **Causa provável:** {escapar_md(r['causa'])}"
        )
        st.markdown(f":material/groups: {escapar_md(r['afeta_texto'])}")
        st.markdown(f":material/payments: {escapar_md(r['valor_texto'])}")
        st.markdown(f":material/alt_route: Setor de destino: **{escapar_md(r['centro'])}**")
        # Alerta de QUALQUER chamado do grupo (o líder não esconde o de outro membro).
        for alerta in r["alertas_grupo"]:
            if alerta["tipo"] == "injecao":
                st.error(escapar_md(alerta["texto"]), icon=":material/report:")
            else:
                st.warning(escapar_md(alerta["texto"]), icon=":material/pause_circle:")


def _coluna_caso(assinatura: str, agora_iso: str, chamado_id: str, agora: datetime, acoes: list[dict[str, Any]]) -> None:
    caso = _caso(assinatura, agora_iso, chamado_id)
    ch, causa = caso["chamado"], caso["causa"]
    st.subheader("Caso montado")
    st.caption(
        f"{escapar_md(ch['id'])} · {escapar_md(ch['tipo'])} · esperando {escapar_md(ch['esperando'])}"
        f" · status: {escapar_md(status_do_chamado(acoes, chamado_id))}"
    )
    _cartao_resumo(_resumo(assinatura, agora_iso, chamado_id))
    _texto(f"Autor: {ch['autor']}")
    _texto(f"Assunto: {texto_citado(ch['assunto'])}")
    _origem()

    if causa["provas"]:
        with st.expander(f"Provas ({len(causa['provas'])})", icon=":material/fact_check:"):
            for prova in causa["provas"]:
                _prova(prova)

    st.markdown("**Texto do chamado**")
    _citacao(ch["texto"])
    for alerta in caso["alertas_injecao"]:
        st.error(escapar_md(alerta["mensagem"]), icon=":material/report:")
        st.caption(f"fonte: {escapar_md(alerta['fonte'])} · {escapar_md(alerta['efeito'])}")
        for trecho in alerta["trechos"]:
            _citacao(trecho, alerta["fonte"])

    _historico(caso["historico"])
    _alerta_seguranca(caso["alerta_seguranca"])
    _rota(caso)
    st.divider()
    _acoes_do_atendente(chamado_id, caso["rota"]["centro"], agora)
    _registro_da_sessao(acoes)


def _rodape() -> None:
    st.divider()
    st.badge(AVISO, icon=":material/science:", color="orange")
    st.caption("O Sentinela mostra causa provável, provas e riscos. Quem decide é sempre o atendente.")


# ---------------------------------------------------------------- tela
def main() -> None:
    st.set_page_config(layout="wide", page_title="Sentinela")
    st.html(CSS)
    st.session_state.setdefault("acoes", [])

    assinatura = _assinatura()
    centro, horas, lugar_contagem = _topo()
    agora = agora_simulado(horas)
    agora_iso = agora.isoformat()
    _faixa_saques(_saques(assinatura, agora_iso))
    _selecao_inicial(assinatura)

    itens = _fila(assinatura, agora_iso, centro)["itens"]
    grupos = agrupar_fila(itens, _grupos(assinatura, agora_iso))
    _contagem(lugar_contagem, len(itens), len(grupos))
    ids = [i["id"] for i in itens]
    # A escolha do atendente sobrevive à troca de filtro; a seleção efetiva é derivada a cada rerun.
    escolha = st.session_state.get("chamado_escolhido")
    selecionado = escolha if escolha in ids else (ids[0] if ids else None)
    acoes = st.session_state["acoes"]  # callbacks já rodaram: inclui a ação deste clique

    with st.container(key="layout"):
        col_fila, col_caso, col_grafo = st.columns([1.05, 1.3, 1.35], gap="medium")
        with col_fila:
            _coluna_fila(grupos, selecionado, acoes)
        if selecionado is None:
            col_caso.info("Sem chamado para montar o caso.")
            col_grafo.info("Sem chamado para mostrar o grafo.")
        else:
            with col_caso:
                _coluna_caso(assinatura, agora_iso, selecionado, agora, acoes)
            with col_grafo:
                _coluna_grafo(assinatura, agora_iso, selecionado)

    _rodape()


main()
