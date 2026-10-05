"""Geração das saídas: relatório HTML autocontido, planilha XLSX, CSVs e RESUMO.md."""
from __future__ import annotations

import html
import math
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Config
from .metricas import n0, n1, n2

# =========================================================================== formatação

ROTULOS = {
    "nm_municipio": "Município", "sg_uf": "UF", "regiao": "Região", "aptos": "Eleitores", "eleitorado": "Eleitores",
    "faixa_eleitorado": "Porte", "validos_pres": "Válidos (pres.)", "validos": "Válidos", "renan_votos": "Votos pres.",
    "renan_pct": "% pres.", "renan_pct100": "% pres.", "renan_pos": "Posição", "lider_pres": "Líder no município",
    "df_total": "Dep. Fed. (votos)", "df_pct": "% Dep. Fed.", "df_pct100": "% Dep. Fed.", "df_nominais": "DF nominais",
    "df_legenda": "DF legenda", "de_total": "Dep. Est. (votos)", "de_pct": "% Dep. Est.", "top_df_nome": "Dep. Fed. + votado",
    "top_df_votos": "Votos do + votado (DF)", "top_de_nome": "Dep. Est. + votado", "top_de_votos": "Votos do + votado (DE)",
    "razao_df": "DF ÷ pres.", "razao_de": "DE ÷ pres.", "razao_df_renan": "DF ÷ pres.", "razao_de_renan": "DE ÷ pres.",
    "legenda_por_renan": "Legenda ÷ pres.", "idr": "Índice vs. Brasil", "participacao_no_total": "% do total do pres.",
    "corr_renan_df_mun": "Correlação pres. × DF", "municipios": "Municípios", "mun_renan_1o_3o": "Mun. no top 3",
    "gov_votos": "Governador (votos)", "sen_votos": "Senador (votos)", "mediana_mun_pct": "Mediana municipal %",
    "pct_uf": "% na UF", "pct_uf100": "% na UF", "capital_vs_uf": "Capital ÷ UF", "pct_suav100": "% suavizado",
    "idr_suav": "Índice vs. UF", "z_robusto": "z robusto", "gap_pres_df_pp": "Pres. − DF (p.p.)",
    "distorcao_pos_z3": "Distorções + (z≥3)", "distorcao_neg_z3": "Distorções − (z≤−3)",
    "amplitude_pct_suav": "Amplitude (p.p.)", "pct_esperado": "% esperado", "residuo_pp": "Resíduo (p.p.)",
    "razao_real_esperado": "Real ÷ esperado", "votos_esperados": "Votos esperados",
    "votos_acima_esperado": "Votos acima do esperado", "cargo": "Cargo", "vagas": "Vagas", "qe": "QE",
    "votos_partido": "Votos do partido", "pct_do_qe": "% do QE", "quocientes_partidarios": "QP",
    "faltaram_para_qe": "Faltaram p/ QE", "faltaram_para_80pct_qe": "Faltaram p/ 80% QE", "eleitos": "Eleitos",
    "candidatos": "Candidatos", "mais_votado": "Mais votado", "votos_mais_votado": "Votos do + votado",
    "mais_votado_pct_qe": "+ votado (% QE)", "posicao_partido_na_uf": "Posição do partido",
    "votos_presidente_na_uf": "Votos pres. na UF", "conversao_necessaria_pct": "Conversão necessária",
    "conversao_obtida_pct": "Conversão obtida", "nr": "Nº", "candidato": "Candidato", "partido": "Partido",
    "federacao": "Federação", "votos_presidente": "Votos pres.", "df_votos_partido": "Votos DF do partido",
    "de_votos_partido": "Votos DE do partido", "razao_df_federacao": "DF federação ÷ pres.",
    "legenda_por_voto_pres": "Legenda ÷ pres.", "legenda_share_partido": "Legenda (% do partido)",
    "ufs_com_chapa_df": "UFs com chapa DF", "corr_mun_pres_df": "Correlação pres. × DF",
    "elasticidade_df": "Elasticidade DF", "quintil": "Quintil", "pct_pres_min": "% pres. mín.",
    "pct_pres_max": "% pres. máx.", "nm_urna": "Candidato", "nr_candidato": "Nº", "votos": "Votos",
    "razao_cand_renan": "Cand. ÷ pres.", "municipios_acima_do_presidente": "Municípios acima do pres.",
    "votos_nesses_municipios": "Votos nesses municípios", "votos_presidente_nesses": "Votos pres. nesses",
    "votos_totais": "Votos totais", "pct_votos_do_cand_nesses": "% dos votos do cand.",
    "df_maior_que_pres": "DF > pres.", "de_maior_que_pres": "DE > pres.", "algum_candidato_maior": "Cand. > pres.",
    "pct_mun_df_maior": "% mun. DF > pres.", "todos_municipios": "Municípios", "pct": "%", "nome": "Candidato",
    "situacao": "Situação", "pct_uf_cand": "% na UF", "municipios_com_voto": "Mun. com voto",
    "hhi_concentracao": "Concentração (HHI)", "reduto": "Reduto", "pct_votos_no_reduto": "% no reduto",
    "corr_com_presidente": "Correlação c/ pres.", "votos_cand_por_voto_pres_uf": "Cand. ÷ pres. (UF)",
    "rank_no_partido_uf": "Rank no partido", "nr_zona": "Zona", "zonas": "Zonas", "pct_min": "% mín.",
    "pct_max": "% máx.", "amplitude_pp": "Amplitude (p.p.)", "grupo_referencia": "Grupo de referência",
    "taxa_migracao_estimada": "Taxa estimada", "votos_implicitos": "Votos implícitos",
    "pct_dos_votos_do_candidato": "% dos votos do pres.", "variavel": "Variável",
    "coef_logit_por_1dp": "Coef. (logit / 1 dp)", "erro_padrao": "Erro padrão", "p_valor": "p-valor",
    "efeito_relativo_pct": "Efeito relativo (%)", "indicador": "Indicador", "valor": "Valor", "item": "Item",
    "fatia_dos_votos": "Fatia dos votos", "municipios_candidato": "Municípios (pres.)",
    "municipios_eleitorado_geral": "Municípios (válidos gerais)", "municipios_em_1o": "Municípios em 1º",
    "tema": "Tema", "fato": "Fato", "tipo": "Tipo", "validos_df": "Válidos DF", "validos_de": "Válidos DE",
}

INT = re.compile(r"^(aptos|eleitorado|validos.*|renan_votos|df_total|df_nominais|df_legenda|de_total|top_d._votos|"
                 r"votos.*|municipios.*|gov_votos|sen_votos|qe|faltaram.*|vagas|eleitos|candidatos|zonas|"
                 r"quocientes_partidarios|mun_renan_1o_3o|distorcao_.*_z3|df_votos_partido|de_votos_partido|"
                 r"ufs_com_chapa_df|df_maior_que_pres|de_maior_que_pres|algum_candidato_maior|todos_municipios|"
                 r"posicao_partido_na_uf|nr_zona|nr|nr_candidato|quintil|rank_no_partido_uf|renan_pos)$")
PCT = re.compile(r"^(renan_pct|renan_pct100|pct_uf100|pct_uf|pct_suav100|df_pct|df_pct100|de_pct|"
                 r"participacao_no_total|mediana_mun_pct|pct_esperado|pct_do_qe|mais_votado_pct_qe|conversao_.*|"
                 r"pct_min|pct_max|pct|pct_votos.*|pct_mun_df_maior|pct_pres_m..|pct_dos_votos_do_candidato|"
                 r"legenda_share_partido|efeito_relativo_pct)$")
PP = re.compile(r"^(residuo_pp|gap_pres_df_pp|amplitude_pp|amplitude_pct_suav)$")
RAZAO = re.compile(r"^(idr|idr_suav|razao_.*|capital_vs_uf|legenda_por_.*|votos_cand_por_voto_pres_uf)$")
DEC = re.compile(r"^(corr_.*|elasticidade.*|z_robusto|hhi_concentracao|coef_.*|erro_padrao|taxa_migracao_estimada)$")


def tipo_coluna(col: str) -> str:
    for nome, rx in (("pct", PCT), ("pp", PP), ("razao", RAZAO), ("dec", DEC), ("int", INT)):
        if rx.match(col):
            return nome
    if col == "p_valor":
        return "p"
    return "txt"


def fmt(v, tipo: str) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)) or (not isinstance(v, str) and pd.isna(v)):
        return "–"
    if isinstance(v, (bool, np.bool_)):
        return "sim" if v else "não"
    if tipo == "txt" or isinstance(v, str):
        if isinstance(v, (int, np.integer)):
            return n0(v)
        if isinstance(v, (float, np.floating)):
            return n2(v) if abs(v) < 1000 else n0(v)
        return str(v)
    if tipo == "int":
        return n0(v)
    if tipo == "pct":
        return n2(v) + "%"
    if tipo == "pp":
        return ("+" if v > 0 else "") + n2(v)
    if tipo == "razao":
        return n2(v) + "×"
    if tipo == "p":
        return "< 0,001" if v < 0.001 else n2(v) if v >= 0.01 else f"{v:.3f}".replace(".", ",")
    return n2(v)


def valor_ordenacao(v) -> str:
    if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool) and np.isfinite(v):
        return repr(float(v))
    return html.escape(str(v), quote=True) if v is not None and not (isinstance(v, float) and np.isnan(v)) else ""


def tabela(df: pd.DataFrame, colunas: list[str] | None = None, id_: str = "", visiveis: int = 12,
           busca: bool = False, destaque: str | None = None, rotulos: dict | None = None) -> str:
    """Tabela HTML ordenável (clique no cabeçalho), com 'mostrar todas' e busca opcional."""
    if df is None or df.empty:
        return '<p class="vazio">Sem registros para esta análise.</p>'
    colunas = [c for c in (colunas or list(df.columns)) if c in df.columns]
    rot = {**ROTULOS, **(rotulos or {})}
    tipos = {c: tipo_coluna(c) for c in colunas}
    th = "".join(f'<th scope="col" class="{"num" if tipos[c] != "txt" else ""}" data-col="{i}">'
                 f'{html.escape(rot.get(c, c))}</th>' for i, c in enumerate(colunas))
    linhas = []
    for i, (_, r) in enumerate(df[colunas + ([destaque] if destaque and destaque not in colunas else [])].iterrows()):
        classes = []
        if i >= visiveis:
            classes.append("extra")
        if destaque and bool(r.get(destaque)):
            classes.append("destaque")
        tds = "".join(f'<td class="{"num" if tipos[c] != "txt" else ""}" data-v="{valor_ordenacao(r[c])}">'
                      f'{html.escape(fmt(r[c], tipos[c]))}</td>' for c in colunas)
        linhas.append(f'<tr class="{" ".join(classes)}">{tds}</tr>')
    n = len(df)
    controles = []
    if busca:
        controles.append(f'<input type="search" class="busca" id="busca-{id_}" placeholder="Filtrar linhas…" '
                         f'aria-label="Filtrar linhas da tabela">')
    if n > visiveis:
        controles.append(f'<button type="button" class="mais" id="mais-{id_}" data-total="{n}">'
                         f'Mostrar todas as {n0(n)} linhas</button>')
    barra = f'<div class="tabela-ctrl">{"".join(controles)}</div>' if controles else ""
    return (f'<div class="tabela" id="t-{id_}">{barra}<div class="rolagem"><table><thead><tr>{th}</tr></thead>'
            f'<tbody>{"".join(linhas)}</tbody></table></div></div>')


# =========================================================================== gráficos (SVG)

def _e(s) -> str:
    return html.escape(str(s), quote=True)


def _ticks(maximo: float, n: int = 5) -> list[float]:
    if maximo <= 0:
        return [0]
    passo = 10 ** math.floor(math.log10(maximo / n))
    for m in (1, 2, 2.5, 5, 10):
        if maximo / (passo * m) <= n:
            passo *= m
            break
    return [round(i * passo, 10) for i in range(int(maximo / passo) + 1)]


def _box(svg: str) -> str:
    return f'<div class="grafico-box">{svg}</div>'


def _legenda(itens: list[tuple[str, str]]) -> str:
    return '<div class="legenda">' + "".join(
        f'<span><i class="ponto {c}"></i>{_e(t)}</span>' for c, t in itens) + "</div>"


def svg_halteres(rotulos, a, b, tips, ref: float | None, nome_a: str, nome_b: str, titulo: str) -> str:
    """Gráfico de halteres: dois % por linha (pres. × chapa), mesma escala."""
    n = len(rotulos)
    L, R, T, h = 46, 24, 28, 21
    W, H = 720, T + n * h + 30
    vmax = max([*a, *b, ref or 0]) * 1.08 or 1
    x = lambda v: L + (W - L - R) * v / vmax  # noqa: E731
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{_e(titulo)}" class="grafico">']
    for t in _ticks(vmax):
        out.append(f'<line x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{T - 6}" y2="{H - 24}" class="grade"/>'
                   f'<text x="{x(t):.1f}" y="{H - 8}" class="eixo" text-anchor="middle">{n1(t)}%</text>')
    if ref:
        out.append(f'<line x1="{x(ref):.1f}" x2="{x(ref):.1f}" y1="{T - 14}" y2="{H - 24}" class="ref"/>'
                   f'<text x="{x(ref) + 4:.1f}" y="{T - 16}" class="eixo">Brasil {n2(ref)}%</text>')
    for i, (r, va, vb, tip) in enumerate(zip(rotulos, a, b, tips)):
        y = T + i * h + h / 2
        out.append(f'<g class="alvo" data-tip="{_e(tip)}"><rect x="0" y="{y - h / 2}" width="{W}" height="{h}" class="faixa"/>'
                   f'<text x="{L - 10}" y="{y + 4}" class="rot" text-anchor="end">{_e(r)}</text>'
                   f'<line x1="{x(min(va, vb)):.1f}" x2="{x(max(va, vb)):.1f}" y1="{y}" y2="{y}" class="haste"/>'
                   f'<circle cx="{x(vb):.1f}" cy="{y}" r="5" class="m-b"/>'
                   f'<circle cx="{x(va):.1f}" cy="{y}" r="5" class="m-a"/></g>')
    out.append("</svg>")
    return _legenda([("m-a", nome_a), ("m-b", nome_b)]) + _box("".join(out))


def svg_colunas(rotulos, series: list[tuple[str, str, list[float]]], titulo: str, sufixo: str = "%",
                tips: list[str] | None = None) -> str:
    """Colunas agrupadas (até 3 séries, mesma unidade)."""
    n, k = len(rotulos), len(series)
    L, R, T, B = 44, 12, 16, 46
    W, H = 720, 300
    vmax = max(max(v for _, _, vs in series for v in vs if np.isfinite(v)), 1e-9) * 1.12
    y = lambda v: T + (H - T - B) * (1 - v / vmax)  # noqa: E731
    banda = (W - L - R) / n
    larg = min(26, (banda - 10) / k)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{_e(titulo)}" class="grafico">']
    for t in _ticks(vmax):
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y(t):.1f}" y2="{y(t):.1f}" class="grade"/>'
                   f'<text x="{L - 6}" y="{y(t) + 4:.1f}" class="eixo" text-anchor="end">{n1(t)}{sufixo}</text>')
    for i, r in enumerate(rotulos):
        cx = L + banda * (i + 0.5)
        x0 = cx - larg * k / 2 - (k - 1)
        tip = tips[i] if tips else r
        out.append(f'<g class="alvo" data-tip="{_e(tip)}"><rect x="{L + banda * i:.1f}" y="{T}" width="{banda:.1f}" '
                   f'height="{H - T - B}" class="faixa"/>')
        for j, (cls, _, vs) in enumerate(series):
            v = vs[i] if np.isfinite(vs[i]) else 0
            xx = x0 + j * (larg + 2)
            hh = max(0.0, y(0) - y(v))
            rr = min(4, larg / 2, hh)
            out.append(f'<path d="M{xx:.1f},{y(0):.1f} v{-(hh - rr):.1f} q0,{-rr:.1f} {rr:.1f},{-rr:.1f} '
                       f'h{larg - 2 * rr:.1f} q{rr:.1f},0 {rr:.1f},{rr:.1f} v{hh - rr:.1f} z" class="{cls}"/>')
        out.append(f'<text x="{cx:.1f}" y="{H - B + 18}" class="eixo" text-anchor="middle">{_e(r)}</text></g>')
    out.append(f'<line x1="{L}" x2="{W - R}" y1="{y(0):.1f}" y2="{y(0):.1f}" class="base"/></svg>')
    return (_legenda([(c, t) for c, t, _ in series]) if k > 1 else "") + _box("".join(out))


def svg_barras_qe(rotulos, valores, eleitos, tips, titulo) -> str:
    """% do quociente eleitoral por UF, com linhas de 80% e 100%."""
    n = len(rotulos)
    L, R, T, h = 46, 30, 26, 19
    W, H = 720, T + n * h + 28
    vmax = max(120.0, min(max(valores) * 1.05, 200.0) if valores else 120)
    x = lambda v: L + (W - L - R) * min(v, vmax) / vmax  # noqa: E731
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{_e(titulo)}" class="grafico">']
    for t in _ticks(vmax):
        out.append(f'<line x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{T - 4}" y2="{H - 22}" class="grade"/>'
                   f'<text x="{x(t):.1f}" y="{H - 6}" class="eixo" text-anchor="middle">{n0(t)}%</text>')
    for lim, txt in ((80, "80% (cláusula)"), (100, "QE")):
        out.append(f'<line x1="{x(lim):.1f}" x2="{x(lim):.1f}" y1="{T - 12}" y2="{H - 22}" class="ref"/>'
                   f'<text x="{x(lim) + 3:.1f}" y="{T - 14}" class="eixo">{txt}</text>')
    for i, (r, v, el, tip) in enumerate(zip(rotulos, valores, eleitos, tips)):
        yy = T + i * h
        cls = "m-b" if v >= 100 else ("m-b2" if v >= 80 else "m-ctx")
        w = max(0.0, x(v) - L)
        out.append(f'<g class="alvo" data-tip="{_e(tip)}"><rect x="0" y="{yy}" width="{W}" height="{h}" class="faixa"/>'
                   f'<text x="{L - 8}" y="{yy + h / 2 + 4}" class="rot" text-anchor="end">{_e(r)}</text>'
                   f'<rect x="{L}" y="{yy + 3}" width="{w:.1f}" height="{h - 6}" rx="3" class="{cls}"/>')
        rotulo = (f"{n0(v)}% · " if v > vmax else "") + (f'{el} eleito{"s" if el > 1 else ""}' if el else "")
        if rotulo:
            if v > vmax:
                out.append(f'<text x="{L + w - 6:.1f}" y="{yy + h / 2 + 4}" class="rot forte sobre" text-anchor="end">{rotulo}</text>')
            else:
                out.append(f'<text x="{L + w + 5:.1f}" y="{yy + h / 2 + 4}" class="rot forte">{rotulo}</text>')
        out.append("</g>")
    out.append("</svg>")
    return _legenda([("m-b", "Atingiu o QE"), ("m-b2", "Entre 80% e 100% do QE"), ("m-ctx", "Abaixo de 80%")]) + _box("".join(out))


def svg_divergente(rotulos, valores, tips, titulo) -> str:
    """Barras divergentes: desempenho real ÷ esperado − 1 (em %)."""
    n = len(rotulos)
    L, R, T, h = 46, 20, 10, 19
    W, H = 720, T + n * h + 26
    m = max(10.0, max(abs(v) for v in valores) * 1.1) if valores else 10
    x = lambda v: L + (W - L - R) * (v + m) / (2 * m)  # noqa: E731
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{_e(titulo)}" class="grafico">']
    for t in _ticks(m, 3):
        for s in ((t, -t) if t else (0,)):
            out.append(f'<line x1="{x(s):.1f}" x2="{x(s):.1f}" y1="{T}" y2="{H - 22}" class="grade"/>'
                       f'<text x="{x(s):.1f}" y="{H - 6}" class="eixo" text-anchor="middle">{"+" if s > 0 else ""}{n0(s)}%</text>')
    for i, (r, v, tip) in enumerate(zip(rotulos, valores, tips)):
        yy = T + i * h
        x0, x1 = sorted((x(0), x(v)))
        out.append(f'<g class="alvo" data-tip="{_e(tip)}"><rect x="0" y="{yy}" width="{W}" height="{h}" class="faixa"/>'
                   f'<text x="{L - 8}" y="{yy + h / 2 + 4}" class="rot" text-anchor="end">{_e(r)}</text>'
                   f'<rect x="{x0:.1f}" y="{yy + 3}" width="{max(x1 - x0, 1):.1f}" height="{h - 6}" rx="3" '
                   f'class="{"m-pos" if v >= 0 else "m-neg"}"/></g>')
    out.append(f'<line x1="{x(0):.1f}" x2="{x(0):.1f}" y1="{T}" y2="{H - 22}" class="base"/></svg>')
    return _legenda([("m-pos", "Acima do esperado"), ("m-neg", "Abaixo do esperado")]) + _box("".join(out))


def svg_pontos_log(rotulos, valores, destaque, tips, titulo) -> str:
    """Pontos em escala log (razões): destaca o partido, demais em cinza."""
    pares = [(r, v, d, t) for r, v, d, t in zip(rotulos, valores, destaque, tips) if v and v > 0 and np.isfinite(v)]
    n = len(pares)
    L, R, T, h = 170, 30, 10, 26
    W, H = 720, T + n * h + 28
    lo = 10 ** math.floor(math.log10(min(v for _, v, _, _ in pares)))
    hi = 10 ** math.ceil(math.log10(max(v for _, v, _, _ in pares)))
    x = lambda v: L + (W - L - R) * (math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo))  # noqa: E731
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{_e(titulo)}" class="grafico">']
    d = lo
    while d <= hi * 1.0001:
        for m in (1, 3):
            t = d * m
            if lo <= t <= hi:
                out.append(f'<line x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{T}" y2="{H - 22}" class="grade"/>'
                           f'<text x="{x(t):.1f}" y="{H - 6}" class="eixo" text-anchor="middle">'
                           f'{n2(t) if t < 1 else n0(t)}×</text>')
        d *= 10
    if lo <= 1 <= hi:
        out.append(f'<line x1="{x(1):.1f}" x2="{x(1):.1f}" y1="{T}" y2="{H - 22}" class="ref"/>')
    for i, (r, v, dst, tip) in enumerate(pares):
        yy = T + i * h + h / 2
        out.append(f'<g class="alvo" data-tip="{_e(tip)}"><rect x="0" y="{yy - h / 2}" width="{W}" height="{h}" class="faixa"/>'
                   f'<text x="{L - 10}" y="{yy + 4}" class="rot{" forte" if dst else ""}" text-anchor="end">{_e(r)}</text>'
                   f'<line x1="{L}" x2="{x(v):.1f}" y1="{yy}" y2="{yy}" class="haste"/>'
                   f'<circle cx="{x(v):.1f}" cy="{yy}" r="{6 if dst else 5}" class="{"m-a" if dst else "m-ctx"}"/>'
                   f'<text x="{x(v) + 10:.1f}" y="{yy + 4}" class="rot{" forte" if dst else ""}">{n2(v)}×</text></g>')
    out.append("</svg>")
    return _box("".join(out))


def svg_dispersao(x_, y_, acima, tips, titulo, nome_x, nome_y) -> str:
    """Dispersão município a município em escala de raiz quadrada (acomoda zeros e caudas longas)."""
    L, R, T, B = 52, 16, 14, 44
    W, H = 720, 460
    xs, ys = np.sqrt(np.clip(x_, 0, None)), np.sqrt(np.clip(y_, 0, None))
    mx = math.sqrt(max(np.nanpercentile(x_, 99.7), 1e-6)) * 1.05
    my = math.sqrt(max(np.nanpercentile(y_, 99.7), 1e-6)) * 1.05
    m = max(mx, my)
    px = lambda v: L + (W - L - R) * min(v, m) / m  # noqa: E731
    py = lambda v: H - B - (H - T - B) * min(v, m) / m  # noqa: E731
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{_e(titulo)}" class="grafico">']
    for t in (0, 1, 2, 5, 10, 20, 40, 60):
        if math.sqrt(t) <= m:
            s = math.sqrt(t)
            out.append(f'<line x1="{px(s):.1f}" x2="{px(s):.1f}" y1="{T}" y2="{H - B}" class="grade"/>'
                       f'<text x="{px(s):.1f}" y="{H - B + 16}" class="eixo" text-anchor="middle">{t}%</text>'
                       f'<line x1="{L}" x2="{W - R}" y1="{py(s):.1f}" y2="{py(s):.1f}" class="grade"/>'
                       f'<text x="{L - 6}" y="{py(s) + 4:.1f}" class="eixo" text-anchor="end">{t}%</text>')
    out.append(f'<line x1="{px(0):.1f}" y1="{py(0):.1f}" x2="{px(m):.1f}" y2="{py(m):.1f}" class="ref"/>')
    ordem = np.argsort(acima, kind="stable")
    for i in ordem:
        if not (np.isfinite(xs[i]) and np.isfinite(ys[i])):
            continue
        cls = "m-b ponto-d" if acima[i] else "m-ctx ponto-d"
        out.append(f'<circle cx="{px(xs[i]):.1f}" cy="{py(ys[i]):.1f}" r="3" class="{cls} alvo" data-tip="{_e(tips[i])}"/>')
    out.append(f'<text x="{(L + W - R) / 2}" y="{H - 6}" class="eixo" text-anchor="middle">{_e(nome_x)} (escala raiz)</text>'
               f'<text x="14" y="{(T + H - B) / 2}" class="eixo" text-anchor="middle" '
               f'transform="rotate(-90 14 {(T + H - B) / 2})">{_e(nome_y)}</text></svg>')
    return _legenda([("m-b", "Chapa de Dep. Federal com mais votos que o presidenciável"),
                     ("m-ctx", "Demais municípios")]) + _box("".join(out))


# =========================================================================== página

CSS = r"""
:root{
  /* Layout: coluna única de leitura (máx. 1120px), navegação fixa por seções, tabelas roláveis */
  --bg:#f4f6f9; --surface:#ffffff; --ink:#111827; --ink-2:#4a5464; --muted:#7a8494; --line:#dfe3ea; --grid:#e8ebf0;
  --band:#eef1f6; --accent:#c4501f; --accent-soft:#fbe9e1;
  --c-a:#eb6834; --c-b:#2a78d6; --c-b2:#86b6ef; --c-c:#1baf7a; --c-ctx:#b5bcc8; --c-pos:#2a78d6; --c-neg:#e34948;
  --warn-bg:#fff4d6; --warn-ink:#6b4a00;
  --f-display:"Archivo","Arial Narrow",system-ui,sans-serif; --f-body:"Public Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  --f-mono:"JetBrains Mono",ui-monospace,"SFMono-Regular",Menlo,monospace;
  color-scheme:light;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0f1216; --surface:#171b21; --ink:#eef1f5; --ink-2:#b4bcc8; --muted:#8a93a1; --line:#2a313b; --grid:#232932;
  --band:#1d232b; --accent:#f08a5d; --accent-soft:#3a2219;
  --c-a:#d95926; --c-b:#3987e5; --c-b2:#1c5cab; --c-c:#199e70; --c-ctx:#5a6372; --c-pos:#3987e5; --c-neg:#e66767;
  --warn-bg:#3a2e0b; --warn-ink:#ffd66b; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#0f1216; --surface:#171b21; --ink:#eef1f5; --ink-2:#b4bcc8; --muted:#8a93a1; --line:#2a313b; --grid:#232932;
  --band:#1d232b; --accent:#f08a5d; --accent-soft:#3a2219;
  --c-a:#d95926; --c-b:#3987e5; --c-b2:#1c5cab; --c-c:#199e70; --c-ctx:#5a6372; --c-pos:#3987e5; --c-neg:#e66767;
  --warn-bg:#3a2e0b; --warn-ink:#ffd66b; color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font:15px/1.55 var(--f-body);margin:0}
.pagina{max-width:1120px;margin:0 auto;padding-inline:20px;padding-block:0 64px}
h1,h2,h3{font-family:var(--f-display);font-stretch:85%;line-height:1.15;text-wrap:balance;margin:0}
h1{font-size:clamp(30px,5vw,46px);font-weight:800;letter-spacing:-.01em}
h2{font-size:clamp(23px,3vw,30px);font-weight:750}
h3{font-size:17px;font-weight:700;margin-top:8px}
p{margin:0;max-width:72ch}
.aviso{background:var(--warn-bg);color:var(--warn-ink);font-weight:700;padding:10px 14px;border-radius:6px;margin-top:16px}
header.topo{padding-block:36px 20px;display:grid;gap:14px}
.sobretitulo{font:600 12px/1 var(--f-mono);letter-spacing:.12em;text-transform:uppercase;color:var(--muted);display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.urna{display:inline-grid;place-items:center;min-width:42px;height:30px;padding-inline:6px;border-radius:5px;background:var(--ink);color:var(--bg);font:800 18px/1 var(--f-display);letter-spacing:0}
.lead{color:var(--ink-2);font-size:16px}
nav.secoes{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--bg);border-bottom:1px solid var(--line);margin-inline:-20px;padding:8px 20px;overflow-x:auto;white-space:nowrap}
nav.secoes a{display:inline-block;color:var(--ink-2);text-decoration:none;font-size:13px;font-weight:600;padding:5px 9px;border-radius:5px}
nav.secoes a:hover,nav.secoes a:focus-visible{background:var(--band);color:var(--ink);outline:none}
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;background:var(--line);border:1px solid var(--line);border-radius:8px;overflow:hidden;margin-top:8px}
.kpi{background:var(--surface);padding:14px 16px;display:grid;gap:4px;align-content:start}
.kpi b{font:750 26px/1.1 var(--f-display);font-stretch:85%}
.kpi span{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;font-weight:600}
.kpi small{color:var(--ink-2);font-size:12.5px}
section.secao{padding-top:44px;display:grid;gap:16px;scroll-margin-top:52px}
.secao>header{display:grid;gap:8px;border-top:2px solid var(--ink);padding-top:12px}
.num-secao{font:600 12px/1 var(--f-mono);color:var(--accent);letter-spacing:.08em}
.bloco{display:grid;gap:10px;min-width:0}
.nota{font-size:13px;color:var(--muted);max-width:80ch}
.fatos{list-style:none;margin:0;padding:0;display:grid;gap:0;border:1px solid var(--line);border-radius:8px;background:var(--surface);overflow:hidden}
.fatos li{display:grid;grid-template-columns:150px 1fr;gap:12px;padding:10px 14px;border-top:1px solid var(--line)}
.fatos li:first-child{border-top:0}
.fatos .tema{font:600 11.5px/1.6 var(--f-mono);text-transform:uppercase;letter-spacing:.06em;color:var(--accent)}
@media (max-width:760px){.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:560px){.fatos li{grid-template-columns:1fr;gap:2px}}
.duas{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr));gap:20px}
.duas>*{min-width:0}
.grafico-box{overflow-x:auto;max-width:900px}
.grafico{width:100%;min-width:600px;height:auto;display:block;background:var(--surface);border:1px solid var(--line);border-radius:8px}
.grafico text{font-family:var(--f-body)}
.grafico .grade{stroke:var(--grid);stroke-width:1}
.grafico .base{stroke:var(--muted);stroke-width:1}
.grafico .ref{stroke:var(--ink-2);stroke-width:1.2}
.grafico .eixo{fill:var(--muted);font-size:12px}
.grafico .rot{fill:var(--ink-2);font-size:12.5px}
.grafico .rot.forte{fill:var(--ink);font-weight:700}
.grafico .rot.sobre{fill:#ffffff}
.grafico .faixa{fill:transparent}
.grafico .alvo:hover .faixa{fill:var(--band)}
.grafico .haste{stroke:var(--c-ctx);stroke-width:2}
.m-a{fill:var(--c-a);stroke:var(--surface);stroke-width:2}
.m-b{fill:var(--c-b);stroke:var(--surface);stroke-width:2}
.m-b2{fill:var(--c-b2)} .m-c{fill:var(--c-c);stroke:var(--surface);stroke-width:2} .m-ctx{fill:var(--c-ctx)}
.m-pos{fill:var(--c-pos)} .m-neg{fill:var(--c-neg)}
path.m-a,path.m-b,path.m-c{stroke-width:0}
.ponto-d{stroke:var(--surface);stroke-width:.8;opacity:.85}
.ponto-d:hover{opacity:1;stroke:var(--ink)}
.legenda{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:12.5px;color:var(--ink-2)}
.legenda span{display:inline-flex;align-items:center;gap:6px}
.legenda .ponto{width:10px;height:10px;border-radius:50%;display:inline-block}
.legenda .m-a{background:var(--c-a)} .legenda .m-b{background:var(--c-b)} .legenda .m-b2{background:var(--c-b2)}
.legenda .m-c{background:var(--c-c)} .legenda .m-ctx{background:var(--c-ctx)} .legenda .m-pos{background:var(--c-pos)} .legenda .m-neg{background:var(--c-neg)}
.tabela{display:grid;gap:8px;min-width:0}
.tabela-ctrl{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.rolagem{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:7px 10px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
th{font-weight:700;color:var(--ink-2);font-size:12px;background:var(--band);cursor:pointer;user-select:none;position:sticky;top:0}
th:hover{color:var(--ink)} th[aria-sort="ascending"]::after{content:" ▲";font-size:9px} th[aria-sort="descending"]::after{content:" ▼";font-size:9px}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:var(--band)}
tr.extra{display:none} .tabela.aberta tr.extra{display:table-row}
tr.oculta{display:none!important}
tr.destaque td{background:var(--accent-soft);font-weight:700}
button.mais,input.busca{font:inherit;font-size:13px;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:6px 10px}
button.mais{cursor:pointer;font-weight:600} button.mais:hover{background:var(--band)}
button.mais:focus-visible,input.busca:focus-visible,th:focus-visible{outline:2px solid var(--c-b);outline-offset:1px}
input.busca{min-width:0;width:min(280px,100%)}
.vazio{color:var(--muted);font-style:italic}
.leitura{display:grid;gap:12px;max-width:78ch}
.leitura h3{margin-top:10px}
.leitura ul{margin:0;padding-left:20px;display:grid;gap:6px}
.leitura p,.leitura li{color:var(--ink);font-size:15px}
.glossario{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:12px}
.glossario div{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:12px 14px;display:grid;gap:4px}
.glossario b{font-family:var(--f-display);font-stretch:85%;font-size:16px}
.glossario p{font-size:13.5px;color:var(--ink-2)}
#dica{position:fixed;pointer-events:none;z-index:20;background:var(--ink);color:var(--bg);font-size:12.5px;line-height:1.4;padding:7px 9px;border-radius:6px;max-width:300px;white-space:pre-line}
footer{margin-top:56px;padding-top:16px;border-top:1px solid var(--line);color:var(--muted);font-size:12.5px;display:grid;gap:6px}
code{font-family:var(--f-mono);font-size:.92em}
@media (prefers-reduced-motion:no-preference){html{scroll-behavior:smooth}}
"""

JS = r"""
(function(){
  document.querySelectorAll('.tabela').forEach(function(box){
    var tb=box.querySelector('tbody'), ths=box.querySelectorAll('th');
    ths.forEach(function(th,i){
      th.tabIndex=0;
      function ordenar(){
        var asc=th.getAttribute('aria-sort')!=='descending'&&th.getAttribute('aria-sort')!==null?false:th.getAttribute('aria-sort')!=='descending';
        var dir=th.getAttribute('aria-sort')==='descending'?'ascending':'descending';
        ths.forEach(function(o){o.removeAttribute('aria-sort')}); th.setAttribute('aria-sort',dir);
        var rows=Array.prototype.slice.call(tb.rows);
        rows.sort(function(a,b){
          var x=a.cells[i].dataset.v,y=b.cells[i].dataset.v,nx=parseFloat(x),ny=parseFloat(y),r;
          if(x===''&&y!=='')return 1; if(y===''&&x!=='')return -1;
          r=(!isNaN(nx)&&!isNaN(ny))?nx-ny:x.localeCompare(y,'pt-BR');
          return dir==='ascending'?r:-r;});
        var lim=box.dataset.vis?parseInt(box.dataset.vis,10):Infinity;
        rows.forEach(function(r,k){tb.appendChild(r); r.classList.toggle('extra',k>=lim);});
      }
      th.addEventListener('click',ordenar);
      th.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();ordenar();}});
    });
    var extras=box.querySelectorAll('tr.extra').length, total=tb.rows.length; box.dataset.vis=total-extras;
    var b=box.querySelector('button.mais');
    if(b){b.addEventListener('click',function(){var a=box.classList.toggle('aberta');
      b.textContent=a?'Mostrar menos':'Mostrar todas as '+b.dataset.total.replace(/\B(?=(\d{3})+(?!\d))/g,'.')+' linhas';});}
    var s=box.querySelector('input.busca');
    if(s){s.addEventListener('input',function(){var q=s.value.trim().toLowerCase();
      if(q){box.classList.add('aberta')}
      Array.prototype.forEach.call(tb.rows,function(r){r.classList.toggle('oculta',q!==''&&r.textContent.toLowerCase().indexOf(q)<0)});});}
  });
  var dica=document.createElement('div'); dica.id='dica'; dica.hidden=true; document.body.appendChild(dica);
  document.addEventListener('pointermove',function(e){
    var el=e.target.closest&&e.target.closest('[data-tip]');
    if(!el){dica.hidden=true;return}
    dica.textContent=el.getAttribute('data-tip'); dica.hidden=false;
    var x=e.clientX+14,y=e.clientY+14,w=dica.offsetWidth,h=dica.offsetHeight;
    if(x+w>innerWidth-8)x=e.clientX-w-14; if(y+h>innerHeight-8)y=e.clientY-h-14;
    dica.style.left=x+'px'; dica.style.top=y+'px';
  });
})();
"""


def _kpi(valor: str, rotulo: str, detalhe: str = "") -> str:
    return f'<div class="kpi"><span>{_e(rotulo)}</span><b>{_e(valor)}</b>{f"<small>{_e(detalhe)}</small>" if detalhe else ""}</div>'


def _secao(id_: str, numero: str, titulo: str, lead: str, corpo: str) -> str:
    return (f'<section class="secao" id="{id_}"><header><span class="num-secao">{numero}</span><h2>{_e(titulo)}</h2>'
            f'<p class="lead">{lead}</p></header>{corpo}</section>')


def _bloco(titulo: str, corpo: str, nota: str = "") -> str:
    return f'<div class="bloco"><h3>{_e(titulo)}</h3>{f"<p class=nota>{nota}</p>" if nota else ""}{corpo}</div>'


def _val(df: pd.DataFrame, indicador: str, padrao=float("nan")):
    s = df.loc[df["indicador"] == indicador, "valor"]
    return s.iat[0] if len(s) else padrao


class _Resultados(dict):
    """Resultados com tabela vazia no lugar de análises sem linhas (ex.: nenhum município em 1º lugar)."""

    def __missing__(self, chave):
        return pd.DataFrame()


def montar_html(cfg: Config, r: dict, sintetico: bool = False) -> str:
    r = _Resultados(r)
    nome, pnome, pnum = cfg.presidente_nome, cfg.partido_nome, cfg.partido_numero
    primeiro = nome.split()[0]
    rot = {"renan_votos": f"Votos {primeiro}", "renan_pct": f"% {primeiro}", "renan_pct100": f"% {primeiro}",
           "votos_presidente_na_uf": f"Votos {primeiro} na UF", "renan_pos": f"Posição {primeiro}",
           "razao_df": f"DF ÷ {primeiro}", "razao_de": f"DE ÷ {primeiro}", "razao_df_renan": f"DF ÷ {primeiro}",
           "razao_de_renan": f"DE ÷ {primeiro}", "legenda_por_renan": f"Legenda ÷ {primeiro}",
           "razao_cand_renan": f"Cand. ÷ {primeiro}", "gap_pres_df_pp": f"{primeiro} − DF (p.p.)",
           "votos_presidente_nesses": f"Votos {primeiro} nesses", "corr_com_presidente": f"Correlação c/ {primeiro}",
           "votos_cand_por_voto_pres_uf": f"Cand. ÷ {primeiro} (UF)", "pct_dos_votos_do_candidato": f"% dos votos de {primeiro}"}
    def T(df, cols=None, rotulos=None, **kw):  # noqa: N802
        return tabela(df, cols, rotulos={**rot, **(rotulos or {})}, **kw)

    res = r["resumo"]
    votos = _val(res, "Votos do candidato a Presidente", 0)
    pct = _val(res, "% dos válidos (Brasil + exterior)", 0)
    pos = _val(res, "Posição nacional", 0)
    top3 = sum(int(_val(res, f"Municípios em {k}º lugar", 0)) for k in (1, 2, 3))
    df_votos = _val(res, "Deputado Federal: votos do partido (nominal + legenda)", 0)
    df_eleitos = _val(res, "Deputado Federal: eleitos", 0)
    de_votos = _val(res, "Deputado Estadual/Distrital: votos do partido (nominal + legenda)", 0)
    de_eleitos = _val(res, "Deputado Estadual/Distrital: eleitos", 0)
    razao = _val(res, "Deputado Federal: votos do partido ÷ votos do presidente", 0)
    dm = r.get("df_maior_que_pres", pd.DataFrame())

    kpis = "".join([
        _kpi(n0(votos), f"Votos de {nome}", f"{n2(pct)}% dos válidos"),
        _kpi(f"{pos}º", "Posição nacional", "1º turno para Presidente"),
        _kpi(n0(top3), "Municípios no top 3", f"{n0(_val(res, 'Municípios em 1º lugar', 0))} em 1º lugar"),
        _kpi(n0(df_votos), "Votos para Dep. Federal", f"{n0(df_eleitos)} eleito(s)"),
        _kpi(n0(de_votos), "Votos para Dep. Estadual", f"{n0(de_eleitos)} eleito(s)"),
        _kpi(n2(razao) + "×", "Guarda-chuva", f"votos de Dep. Federal por voto em {primeiro}"),
        _kpi(n0(len(dm)), "Municípios onde DF > presidente", "chapa federal à frente do presidenciável"),
        _kpi(n0(_val(res, "Votos no exterior", 0)), "Votos no exterior",
             f"{n0(_val(res, 'Municípios com ≥ 5% dos válidos', 0))} municípios com ≥ 5%"),
    ])

    fatos = "".join(f'<li><span class="tema">{_e(t)}</span><span>{_e(f)}</span></li>'
                    for t, f in r["fatos"][["tema", "fato"]].itertuples(index=False))

    # -------- 1. Presidenciáveis
    pres = r["presidenciaveis"].copy()
    pres["destaque"] = pres["nr"] == cfg.presidente_numero
    s_pres = _secao("presidenciaveis", "01", "Corrida presidencial",
                    f"Posição de {nome} entre os presidenciáveis no 1º turno, com votos nominais válidos somados "
                    "em todos os municípios e no exterior.",
                    T(pres, ["nr", "candidato", "votos", "pct", "municipios_em_1o"], id_="pres", destaque="destaque"))

    # -------- 2. Estados
    uf = r["por_uf"]
    ufg = uf[uf["sg_uf"] != "ZZ"].sort_values("renan_pct", ascending=False)
    nac = 100 * votos / max(r["base_municipal"]["validos_pres"].sum(), 1)
    tips = [f"{u}: {primeiro} {n2(a)}% · Dep. Fed. {n2(b)}%\n{n0(v)} votos ({n1(p)}% do total)"
            for u, a, b, v, p in ufg[["sg_uf", "renan_pct", "df_pct", "renan_votos", "participacao_no_total"]].itertuples(index=False)]
    g_uf = svg_halteres(ufg["sg_uf"].tolist(), ufg["renan_pct"].fillna(0).tolist(), ufg["df_pct"].fillna(0).tolist(),
                        tips, nac, f"{nome} (% dos válidos)", f"Chapa de Dep. Federal do {pnome} (% dos válidos)",
                        "Percentual por UF")
    s_uf = _secao("estados", "02", "Estados e regiões",
                  f"Percentual de {nome} e da chapa de Deputado Federal em cada UF. A distância entre os dois pontos "
                  "mostra quanto do voto no presidenciável a chapa proporcional conseguiu acompanhar.",
                  _bloco("Presidente × chapa federal por UF", g_uf)
                  + _bloco("Tabela por UF", T(uf, ["sg_uf", "regiao", "eleitorado", "renan_votos", "renan_pct", "idr",
                                                   "participacao_no_total", "mun_renan_1o_3o", "df_total", "df_pct",
                                                   "razao_df_renan", "legenda_por_renan", "de_total", "de_pct",
                                                   "corr_renan_df_mun"], id_="uf", visiveis=28),
                           "Índice vs. Brasil = % na UF ÷ % nacional. ZZ = exterior.")
                  + '<div class="duas">'
                  + _bloco("Por região", T(r["por_regiao"], ["regiao", "municipios", "renan_votos", "renan_pct",
                                                             "participacao_no_total", "df_pct", "razao_df_renan"], id_="reg"))
                  + _bloco("Capital × interior", T(r["capital_interior"], ["tipo", "municipios", "renan_votos", "renan_pct",
                                                                            "participacao_no_total", "df_pct", "razao_df_renan"], id_="capint"))
                  + "</div>"
                  + _bloco("Capitais", T(r["capitais"], ["nm_municipio", "sg_uf", "aptos", "renan_votos", "renan_pct",
                                                         "renan_pos", "pct_uf", "capital_vs_uf", "df_total", "df_pct",
                                                         "razao_df", "lider_pres"], id_="cap", visiveis=27)))

    # -------- 3. Cidades
    porte = r["por_porte"]
    g_porte = svg_colunas([str(x) for x in porte["faixa_eleitorado"]],
                          [("m-a", f"{nome}", porte["renan_pct"].tolist()),
                           ("m-b", "Chapa Dep. Federal", porte["df_pct"].tolist())],
                          "Percentual por porte do município",
                          tips=[f"{f}: {n0(m)} municípios\n{primeiro} {n2(a)}% · DF {n2(b)}%"
                                for f, m, a, b in porte[["faixa_eleitorado", "municipios", "renan_pct", "df_pct"]].itertuples(index=False)])
    cols_rk = ["nm_municipio", "sg_uf", "aptos", "renan_votos", "renan_pct100", "renan_pos", "lider_pres", "df_total",
               "df_pct100", "top_df_nome"]
    s_cid = _secao("cidades", "03", "Cidades: onde o percentual foi maior",
                   f"Rankings municipais. O ranking principal considera só municípios com pelo menos "
                   f"{n0(cfg.min_eleitores_ranking)} eleitores, porque em cidades muito pequenas poucos votos mudam muito o percentual.",
                   _bloco("Percentual por porte do município", g_porte,
                          "Porte = eleitores aptos. Barras mostram o % agregado de cada faixa.")
                   + _bloco(f"Maiores percentuais (≥ {n0(cfg.min_eleitores_ranking)} eleitores)", T(r["top_pct"], cols_rk, id_="toppct", busca=True))
                   + _bloco("Maiores votações absolutas", T(r["top_votos"], cols_rk, id_="topvot"))
                   + _bloco("Top 10 por porte", T(r["top_pct_por_faixa"], ["faixa_eleitorado"] + cols_rk, id_="topfaixa", busca=True))
                   + _bloco("Top 5 por UF", T(r["top_pct_por_uf"], cols_rk, id_="topuf", busca=True))
                   + _bloco(f"Municípios onde {primeiro} ficou em 1º ou 2º", T(r["podio"], cols_rk, id_="podio"))
                   + _bloco("Piores percentuais entre cidades grandes (≥ 50 mil eleitores)", T(r["bottom_pct_grandes"], cols_rk, id_="bottom"))
                   + _bloco("Municípios sem nenhum voto (maiores)", T(r["sem_votos"], cols_rk, id_="zero"))
                   + _bloco("Concentração geográfica", T(r["concentracao"], id_="conc"),
                            f"Quantos municípios somam cada fatia dos votos de {primeiro}, comparado com a mesma fatia dos "
                            "votos válidos do país. Menos municípios = voto mais concentrado em grandes centros."))

    # -------- 4. Distorções
    cols_d = ["nm_municipio", "sg_uf", "aptos", "renan_votos", "renan_pct100", "pct_uf100", "pct_suav100", "idr_suav",
              "z_robusto", "df_pct100", "razao_df", "top_df_nome"]
    s_dist = _secao("distorcoes", "04", "Distorções e pontos fora da curva",
                    f"Municípios cujo resultado foge do padrão da própria UF. O % suavizado corrige o ruído de cidades "
                    f"pequenas (encolhimento bayesiano em direção à média da UF); o z robusto mede quantos desvios "
                    f"(mediana/MAD) o município está acima ou abaixo dos demais da UF. |z| ≥ 3 é uma distorção forte.",
                    _bloco("Distorções positivas", T(r["distorcao_positiva"], cols_d, id_="dpos", busca=True))
                    + _bloco("Distorções negativas (≥ 20 mil eleitores)", T(r["distorcao_negativa"], cols_d, id_="dneg", busca=True))
                    + _bloco(f"{primeiro} muito acima da chapa federal", T(r["gap_pres_maior_que_dep"], cols_d + ["gap_pres_df_pp"], id_="gp1"),
                             "Diferença em pontos percentuais entre o % do presidenciável e o % da chapa de Dep. Federal.")
                    + _bloco(f"Chapa federal muito acima de {primeiro}", T(r["gap_dep_maior_que_pres"], cols_d + ["gap_pres_df_pp"], id_="gp2"))
                    + _bloco("Distorções por UF", T(r["distorcao_por_uf"], id_="duf", visiveis=27)))

    # -------- 5. Acertos e erros
    if "esperado_por_uf" in r:
        eu = r["esperado_por_uf"].sort_values("razao_real_esperado", ascending=False)
        g_esp = svg_divergente(eu["sg_uf"].tolist(), (100 * (eu["razao_real_esperado"] - 1)).tolist(),
                               [f"{u}: {n0(a)} votos reais vs. {n0(b)} esperados ({'+' if a >= b else ''}{n0(a - b)})"
                                for u, a, b in eu[["sg_uf", "renan_votos", "votos_esperados"]].itertuples(index=False)],
                               "Real versus esperado por UF")
        cols_m = ["nm_municipio", "sg_uf", "aptos", "renan_votos", "renan_pct", "pct_esperado", "residuo_pp",
                  "razao_real_esperado", "votos_acima_esperado", "top_df_nome"]
        corpo_m = (_bloco("Desempenho real ÷ esperado por UF", g_esp,
                          "Dentro de cada UF o modelo inclui efeito fixo; desvios por UF vêm da soma dos municípios.")
                   + '<div class="duas">'
                   + _bloco("Acertos: mais votos acima do esperado", T(r["acertos_absolutos"], cols_m, id_="ac1", visiveis=15))
                   + _bloco("Erros: mais votos abaixo do esperado", T(r["erros_absolutos"], cols_m, id_="er1", visiveis=15))
                   + "</div>"
                   + _bloco("Acertos relativos (≥ 20 mil eleitores)", T(r["acertos_relativos"], cols_m, id_="ac2"))
                   + _bloco("Erros relativos (≥ 20 mil eleitores)", T(r["erros_relativos"], cols_m, id_="er2"))
                   + _bloco("Real × esperado por porte", T(r["esperado_por_faixa"], id_="espfx"))
                   + _bloco("O que explica o voto (coeficientes do modelo)", T(r["modelo_coeficientes"], id_="coef", visiveis=20),
                            "Efeito relativo = variação % na chance de votar no presidenciável para +1 desvio-padrão da "
                            "variável, mantidas as demais. Fatias de votos do ano de comparação são lidas contra a maior "
                            "delas, que fica de fora como referência.")
                   + _bloco("Ficha do modelo", T(r["modelo_meta"], id_="meta")))
    else:
        corpo_m = T(r.get("modelo_meta"), id_="meta")
    s_ae = _secao("acertos", "05", "Onde acertamos, onde erramos",
                  f"Um modelo estatístico estima o % que {nome} 'deveria' ter em cada município, dado o perfil local "
                  "(UF, porte, capital, abstenção, votação da eleição anterior e perfil do eleitorado). Acerto = votos "
                  "acima do previsto; erro = votos abaixo. É o retrato de onde a campanha rendeu mais ou menos do que o "
                  "eleitorado sugeria.", corpo_m)

    # -------- 6. Guarda-chuva
    gc = r["guarda_chuva_partidos"]
    gcv = gc[gc["razao_df"] > 0]
    g_gc = svg_pontos_log([f"{c} ({p})" if p else c for c, p in gcv[["candidato", "partido"]].itertuples(index=False)],
                          gcv["razao_df"].tolist(), gcv["destaque"].tolist(),
                          [f"{c}: {n0(v)} votos para presidente\nChapa DF do partido: {n0(d)} votos ({n2(x)}×)"
                           for c, v, d, x in gcv[["candidato", "votos_presidente", "df_votos_partido", "razao_df"]].itertuples(index=False)],
                          "Votos da chapa federal por voto no presidenciável")
    q = r["guarda_chuva_quintis"]
    g_q = svg_colunas([f"Q{int(k)}" for k in q["quintil"]],
                      [("m-a", nome, q["renan_pct"].tolist()), ("m-b", "Chapa Dep. Federal", q["df_pct"].tolist()),
                       ("m-c", "Chapa Dep. Estadual", q["de_pct"].tolist())],
                      "Quintis de municípios pelo % do presidenciável",
                      tips=[f"Quintil {int(k)}: {n0(m)} municípios ({n2(a)}%–{n2(b)}% para {primeiro})\nDF ÷ {primeiro}: {n2(x)}×"
                            for k, m, a, b, x in q[["quintil", "municipios", "pct_pres_min", "pct_pres_max", "razao_df_renan"]].itertuples(index=False)])
    b = r["base_municipal"]
    bb = b[(~b["exterior"]) & (b["validos_pres"] > 0)]
    g_sc = svg_dispersao((100 * bb["renan_pct"]).to_numpy(), (100 * bb["df_pct"]).to_numpy(),
                         (bb["df_total"] > bb["renan_votos"]).to_numpy(),
                         [f"{m} ({u})\n{primeiro}: {n0(a)} votos ({n2(100 * p)}%)\nDep. Fed.: {n0(d)} votos ({n2(100 * dp)}%)"
                          for m, u, a, p, d, dp in bb[["nm_municipio", "sg_uf", "renan_votos", "renan_pct", "df_total", "df_pct"]].itertuples(index=False)],
                         "Dispersão municipal", f"% {nome}", "% chapa Dep. Federal")
    s_gc = _secao("guarda-chuva", "06", "Guarda-chuva do presidenciável",
                  f"Quanto o voto em {nome} se converteu em voto para a chapa proporcional do {pnome}, e como isso se "
                  "compara com os outros presidenciáveis. Razão acima de 1 indica partido maior que o candidato; "
                  "abaixo de 1, candidato maior que o partido.",
                  _bloco("Indicadores de arrasto", T(r["guarda_chuva_resumo"], id_="gcr", visiveis=20),
                         "Retenção mínima: em cada município, conta-se no máximo o número de votos do presidenciável "
                         "como 'acompanhados' pela chapa. Elasticidade: +1% no % do presidenciável ⇒ +β% no % da chapa.")
                  + _bloco("Comparação entre presidenciáveis (escala log)", g_gc,
                           "Votos da chapa de Dep. Federal do partido de cada presidenciável divididos pelos votos dele. "
                           "Linha vertical = 1×.")
                  + _bloco("Tabela de comparação", T(gc, ["nr", "candidato", "partido", "federacao", "votos_presidente",
                                                          "df_votos_partido", "df_legenda", "razao_df", "razao_df_federacao",
                                                          "razao_de", "legenda_por_voto_pres", "legenda_share_partido",
                                                          "ufs_com_chapa_df", "corr_mun_pres_df", "elasticidade_df"],
                                                     id_="gcp", destaque="destaque", visiveis=15))
                  + _bloco("A chapa acompanha onde o presidenciável é forte?", g_q,
                           "Municípios ordenados pelo % do presidenciável e divididos em cinco grupos com o mesmo número de votos válidos.")
                  + _bloco("Tabela de quintis", T(q, ["quintil", "municipios", "pct_pres_min", "pct_pres_max", "renan_pct",
                                                      "df_pct", "de_pct", "razao_df_renan", "legenda_por_renan"], id_="qt"))
                  + _bloco("Município a município", g_sc,
                           "Cada ponto é um município. Acima da diagonal, a chapa federal teve percentual maior que o "
                           "presidenciável; em azul, os municípios onde ela teve mais votos absolutos."))

    # -------- 7. Deputados > presidente
    cols_dm = ["nm_municipio", "sg_uf", "aptos", "renan_votos", "renan_pct", "df_total", "df_legenda", "razao_df",
               "top_df_nome", "top_df_votos", "de_total", "razao_de", "top_de_nome", "top_de_votos"]
    s_dep = _secao("deputados", "07", f"Onde os deputados tiveram mais votos que {primeiro}",
                   f"Municípios em que a chapa do {pnome} para Deputado Federal ou Estadual (nominal + legenda) superou "
                   f"os votos de {nome}, e candidatos que sozinhos fizeram mais votos que ele. Indicam redutos de "
                   "candidatos locais, com voto próprio e não arrastado pelo presidenciável.",
                   '<div class="duas">'
                   + _bloco("Por UF", T(r["maior_que_pres_por_uf"], ["sg_uf", "municipios", "df_maior_que_pres",
                                                                     "pct_mun_df_maior", "de_maior_que_pres",
                                                                     "algum_candidato_maior"], id_="dmuf", visiveis=10))
                   + _bloco("Por porte", T(r["maior_que_pres_por_porte"], id_="dmpt"))
                   + "</div>"
                   + _bloco("Chapa de Dep. Federal > presidenciável", T(r["df_maior_que_pres"], cols_dm, id_="dmdf", busca=True))
                   + _bloco("Chapa de Dep. Estadual > presidenciável", T(r["de_maior_que_pres"], cols_dm, id_="dmde", busca=True))
                   + _bloco(f"Candidatos que sozinhos superaram {primeiro}", T(r["candidato_maior_que_pres"], id_="cmp", busca=True))
                   + _bloco("Puxadores locais", T(r["candidatos_puxadores_locais"], id_="pux", busca=True),
                            "Quantos municípios cada candidato 'carregou' acima do presidenciável e que fatia dos seus "
                            "votos veio desses municípios."))

    # -------- 8. Quociente eleitoral
    qe = r["quociente"]
    qdf = qe[qe["cargo"] == "Dep. Federal"].sort_values("pct_do_qe", ascending=False)
    g_qe = svg_barras_qe(qdf["sg_uf"].tolist(), qdf["pct_do_qe"].fillna(0).tolist(), qdf["eleitos"].tolist(),
                         [f"{u}: {n0(v)} votos = {n1(p)}% do QE ({n0(q_)})\nFaltaram {n0(f)} votos para 1 QE"
                          for u, v, p, q_, f in qdf[["sg_uf", "votos_partido", "pct_do_qe", "qe", "faltaram_para_qe"]].itertuples(index=False)],
                         "Percentual do quociente eleitoral por UF")
    s_qe = _secao("quociente", "08", "Quociente eleitoral: onde faltou pouco",
                  "Votos do partido (nominal + legenda) em relação ao quociente eleitoral (QE = válidos ÷ vagas) de "
                  f"cada UF. 'Conversão necessária' é a fração dos votos de {primeiro} na UF que a chapa precisaria "
                  "reter para atingir um QE; 'conversão obtida' é o que de fato reteve.",
                  _bloco("Dep. Federal: % do QE por UF", g_qe)
                  + _bloco("Tabela do quociente", T(qe, ["cargo", "sg_uf", "vagas", "qe", "votos_partido", "pct_do_qe",
                                                         "quocientes_partidarios", "eleitos", "faltaram_para_qe",
                                                         "faltaram_para_80pct_qe", "candidatos", "mais_votado",
                                                         "votos_mais_votado", "mais_votado_pct_qe", "posicao_partido_na_uf",
                                                         "votos_presidente_na_uf", "conversao_necessaria_pct",
                                                         "conversao_obtida_pct"], id_="qe", visiveis=27, busca=True),
                           "Regras de 2021 (Lei 14.211): para disputar as sobras o partido precisa de 80% do QE e o "
                           "candidato de 20% do QE; para ocupar vaga pelo quociente partidário, 10% do QE. Vagas inferidas "
                           "pelos eleitos nos dados; se ainda não houver totalização, usa-se a distribuição oficial."))

    # -------- 9. Candidatos
    s_cand = _secao("candidatos", "09", f"Candidatos do {pnome}",
                    "Desempenho individual: votos, fatia da UF, quantos municípios alcançou, concentração (HHI: 1 = todo "
                    "voto num só município), reduto, correlação com o mapa do presidenciável e % do quociente eleitoral.",
                    T(r["candidatos_partido"], ["cargo", "sg_uf", "nr", "nome", "situacao", "votos", "pct_uf",
                                               "rank_no_partido_uf", "municipios_com_voto", "hhi_concentracao", "reduto",
                                               "pct_votos_no_reduto", "corr_com_presidente",
                                               "votos_cand_por_voto_pres_uf", "pct_do_qe"],
                      id_="cand", visiveis=25, busca=True, rotulos={"pct_uf": "% na UF"}))

    # -------- 10. Zonas e exterior
    blocos_z = ""
    if "zonas_top" in r:
        blocos_z = (_bloco("Zonas eleitorais com maior % (≥ 5 mil válidos)", T(r["zonas_top"], id_="ztop", busca=True))
                    + _bloco("Maior desigualdade entre zonas do mesmo município", T(r["zonas_amplitude"], id_="zamp"))
                    + _bloco("Zonas das capitais", T(r["zonas_capitais"], id_="zcap", busca=True, visiveis=15)))
    if not blocos_z:
        blocos_z = ('<p class="nota">Votação por zona eleitoral indisponível nesta fonte: a API de divulgação do TSE '
                    'traz resultados por município. As zonas entram quando os arquivos consolidados forem publicados.</p>')
    s_zona = _secao("zonas", "10", "Zonas eleitorais e exterior",
                    "Dentro das grandes cidades o voto varia muito de bairro para bairro. As zonas eleitorais são a menor "
                    "unidade territorial dos arquivos consolidados do TSE.",
                    blocos_z + _bloco("Exterior", T(r.get("exterior"), id_="ext", busca=True)))

    # -------- 11. Origem dos votos
    ov = r.get("origem_votos", pd.DataFrame())
    corpo_o = '<p class="vazio">Sem dados da eleição de comparação.</p>'
    if ov is not None and len(ov):
        ovv = ov[ov["pct_dos_votos_do_candidato"] > 0.05]
        g_ov = svg_colunas(ovv["grupo_referencia"].tolist(), [("m-a", "", ovv["pct_dos_votos_do_candidato"].tolist())],
                           "Origem estimada dos votos",
                           tips=[f"{g}: {n1(p)}% dos votos de {primeiro}\ntaxa estimada {n1(100 * t)}% do eleitorado do grupo"
                                 for g, p, t in ovv[["grupo_referencia", "pct_dos_votos_do_candidato", "taxa_migracao_estimada"]].itertuples(index=False)])
        corpo_o = (_bloco(f"De onde vieram os votos de {primeiro} (estimativa ecológica)", g_ov,
                          "Regressão ecológica com coeficientes entre 0 e 1. Mostra associação geográfica com o voto de "
                          f"{cfg.ano_comparacao}, não o comportamento individual de cada eleitor.")
                   + _bloco("Tabela", T(ov, id_="orig")))
    corpo_o += _bloco("Correlação geográfica entre presidenciáveis", T(r["correlacao_presidenciaveis"], id_="corrp"),
                      "Correlação ponderada, entre municípios, dos percentuais de cada par de candidatos. Valores "
                      "positivos indicam que disputam o mesmo eleitorado no território.")
    s_orig = _secao("origem", "11", "De onde vieram os votos",
                    f"Comparação geográfica com {cfg.ano_comparacao} e com os outros presidenciáveis de {cfg.ano}.", corpo_o)

    # -------- Metodologia
    glossario = [
        ("Fonte", "Portal de Dados Abertos do TSE (votação por candidato, por partido e detalhe por município/zona; "
                  "cadastro de candidatos; perfil do eleitorado) ou, enquanto os consolidados não saem, a API de "
                  "divulgação de resultados."),
        ("Votos válidos", "Presidente: votos nominais. Proporcionais: nominal + legenda. Brancos e nulos ficam fora."),
        ("Chapa (DF/DE)", f"Soma dos votos nominais em todos os candidatos do {pnome} mais os votos de legenda ({pnum})."),
        ("Guarda-chuva", "Votos da chapa ÷ votos do presidenciável. Também: legenda ÷ presidente, correlação e "
                         "elasticidade municipal."),
        ("% suavizado", "Encolhimento empírico-bayesiano beta-binomial por UF: (votos + α) ÷ (válidos + α + β)."),
        ("z robusto", "Desvio do logit do % suavizado em relação à mediana da UF, em unidades de MAD × 1,4826."),
        ("Esperado", "GLM binomial (logit) ponderado por válidos, com efeito fixo de UF e perfil do município."),
        ("Quociente eleitoral", "Válidos do cargo na UF ÷ vagas, com arredondamento do TSE (fração > 0,5 sobe)."),
    ]
    s_met = _secao("metodologia", "12", "Metodologia e fontes",
                   "Definições usadas em todo o relatório. A planilha que acompanha este relatório traz todas as tabelas, "
                   "inclusive a base municipal completa.",
                   '<div class="glossario">' + "".join(f"<div><b>{_e(a)}</b><p>{_e(b)}</p></div>" for a, b in glossario) + "</div>")

    leitura = cfg.dir_saida / "LEITURA.md"
    s_leitura = ""
    if leitura.exists():
        s_leitura = (f'<section class="secao" id="leitura"><header><span class="num-secao">00</span><h2>Leitura do '
                     f'resultado</h2></header><div class="leitura">{markdown_simples(leitura.read_text(encoding="utf-8"))}'
                     f'</div></section>')
    nav = "".join(f'<a href="#{i}">{t}</a>' for i, t in [("leitura", "Leitura")] * bool(s_leitura) + [
        ("destaques", "Destaques"), ("presidenciaveis", "Presidente"), ("estados", "Estados"), ("cidades", "Cidades"),
        ("distorcoes", "Distorções"), ("acertos", "Acertos e erros"), ("guarda-chuva", "Guarda-chuva"),
        ("deputados", "Deputados × pres."), ("quociente", "Quociente"), ("candidatos", "Candidatos"),
        ("zonas", "Zonas"), ("origem", "Origem"), ("metodologia", "Metodologia")])
    aviso = ('<div class="aviso" role="alert">DADOS SINTÉTICOS — gerados para testar o pipeline. '
             'Nenhum número desta página é resultado real.</div>') if sintetico else ""
    gerado = datetime.now().strftime("%d/%m/%Y %H:%M")
    return f"""<title>Raio-X {_e(pnome)} {cfg.ano}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,600..800&family=JetBrains+Mono:wght@500;600&family=Public+Sans:wght@400;600;700&display=swap">
<style>{CSS}</style>
<div class="pagina">
{aviso}
<header class="topo">
  <div class="sobretitulo"><span class="urna">{pnum}</span><span>Eleições Gerais {cfg.ano}</span><span>·</span><span>{cfg.turno}º turno</span><span>·</span><span>TSE</span></div>
  <h1>Raio-X da votação do {_e(pnome)}</h1>
  <p class="lead">{_e(nome)} para Presidente e as chapas do {_e(pnome)} nos {n0((~r['base_municipal']['exterior']).sum())} municípios e no exterior: onde o voto se concentrou, onde fugiu do padrão, onde a campanha rendeu acima ou abaixo do esperado e quanto o presidenciável puxou a chapa.</p>
</header>
<nav class="secoes" aria-label="Seções">{nav}</nav>
<section class="secao" id="destaques"><header><span class="num-secao">00</span><h2>Destaques</h2></header>
<div class="kpis">{kpis}</div>
<ul class="fatos">{fatos}</ul></section>
{s_leitura}{s_pres}{s_uf}{s_cid}{s_dist}{s_ae}{s_gc}{s_dep}{s_qe}{s_cand}{s_zona}{s_orig}{s_met}
<footer><span>Gerado em {gerado} por <code>python -m missao analisar</code>.</span>
<span>Fonte: Tribunal Superior Eleitoral. Percentuais sobre votos válidos do cargo.</span></footer>
</div>
<script>{JS}</script>
"""


# =========================================================================== exportações

def _md_tabela(df: pd.DataFrame, colunas: list[str], n: int = 10, rotulos: dict | None = None) -> str:
    if df is None or df.empty:
        return "_sem registros_\n"
    rot = {**ROTULOS, **(rotulos or {})}
    colunas = [c for c in colunas if c in df.columns]
    cab = "| " + " | ".join(rot.get(c, c) for c in colunas) + " |"
    sep = "|" + "|".join("---:" if tipo_coluna(c) != "txt" else "---" for c in colunas) + "|"
    linhas = ["| " + " | ".join(fmt(v, tipo_coluna(c)).replace("|", "/") for c, v in zip(colunas, row)) + " |"
              for row in df[colunas].head(n).itertuples(index=False)]
    return "\n".join([cab, sep, *linhas]) + "\n"


def gerar_resumo_md(cfg: Config, r: dict, sintetico: bool) -> str:
    p = cfg.presidente_nome.split()[0]
    rot = {"renan_votos": f"Votos {p}", "renan_pct": f"% {p}", "renan_pct100": f"% {p}"}
    partes = [f"# Raio-X {cfg.partido_nome} {cfg.ano} — {cfg.turno}º turno\n"]
    if sintetico:
        partes.append("> **DADOS SINTÉTICOS** — gerados para testar o pipeline; nenhum número é real.\n")
    partes.append("## Destaques\n")
    partes += [f"- **{t}:** {f}" for t, f in r["fatos"][["tema", "fato"]].itertuples(index=False)]
    partes.append("\n## Resumo\n")
    partes.append(_md_tabela(r["resumo"], ["indicador", "valor"], n=100))
    partes.append("\n## Estados (ordenado pelo % do presidenciável)\n")
    partes.append(_md_tabela(r["por_uf"], ["sg_uf", "renan_votos", "renan_pct", "df_total", "df_pct", "razao_df_renan"], 28, rot))
    partes.append(f"\n## Maiores percentuais (≥ {n0(cfg.min_eleitores_ranking)} eleitores)\n")
    partes.append(_md_tabela(r["top_pct"], ["nm_municipio", "sg_uf", "aptos", "renan_votos", "renan_pct100"], 20, rot))
    partes.append("\n## Guarda-chuva — comparação entre presidenciáveis\n")
    partes.append(_md_tabela(r["guarda_chuva_partidos"], ["candidato", "partido", "votos_presidente", "df_votos_partido",
                                                          "razao_df", "corr_mun_pres_df"], 15))
    partes.append(f"\n## Municípios onde a chapa de Dep. Federal superou {p}\n")
    partes.append(_md_tabela(r["df_maior_que_pres"], ["nm_municipio", "sg_uf", "renan_votos", "df_total", "razao_df",
                                                      "top_df_nome"], 20, rot))
    partes.append("\n## Quociente eleitoral — Dep. Federal\n")
    partes.append(_md_tabela(r["quociente"][r["quociente"]["cargo"] == "Dep. Federal"],
                             ["sg_uf", "votos_partido", "qe", "pct_do_qe", "eleitos", "faltaram_para_qe",
                              "conversao_necessaria_pct", "conversao_obtida_pct"], 27))
    return "\n".join(partes)


def gerar_relatorio(cfg: Config, r: dict, sintetico: bool = False) -> dict[str, Path]:
    saida = cfg.dir_saida
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "tabelas").mkdir(exist_ok=True)
    caminhos = {}

    caminhos["html"] = saida / "relatorio.html"
    caminhos["html"].write_text(montar_html(cfg, r, sintetico), encoding="utf-8")

    caminhos["xlsx"] = saida / "analise_completa.xlsx"
    with pd.ExcelWriter(caminhos["xlsx"], engine="openpyxl") as xw:
        for nome, df in r.items():
            if isinstance(df, pd.DataFrame) and len(df.columns):
                d = df.copy()
                for c in d.columns:
                    if isinstance(d[c].dtype, pd.CategoricalDtype):
                        d[c] = d[c].astype(str)
                d.to_excel(xw, sheet_name=nome[:31], index=False)
    for nome, df in r.items():
        if isinstance(df, pd.DataFrame) and len(df):
            df.to_csv(saida / "tabelas" / f"{nome}.csv", index=False, encoding="utf-8-sig", sep=";", decimal=",")

    caminhos["md"] = saida / "RESUMO.md"
    caminhos["md"].write_text(gerar_resumo_md(cfg, r, sintetico), encoding="utf-8")
    for k, v in caminhos.items():
        print(f"[relatório] {k}: {v}")
    return caminhos


# =========================================================================== reprocessar a partir da planilha

def carregar_planilha(cfg: Config, caminho: Path) -> dict[str, pd.DataFrame]:
    """Lê analise_completa.xlsx de volta para o dicionário de resultados (um DataFrame por aba)."""
    from .metricas import _rotulo_faixa
    r = pd.read_excel(caminho, sheet_name=None)
    b = r["base_municipal"]
    fx = cfg.faixas_eleitorado
    b["faixa_eleitorado"] = pd.cut(b["aptos"], bins=fx, right=False,
                                   labels=[_rotulo_faixa(fx[i], fx[i + 1]) for i in range(len(fx) - 1)])
    for nome in ("resumo", "guarda_chuva_resumo"):
        if nome in r:
            r[nome]["valor"] = r[nome]["valor"].astype(object)
    return r


def reprocessar_planilha(cfg: Config, sintetico: bool = False) -> dict[str, Path]:
    """Refaz modelo, destaques e saídas a partir de saida/analise_completa.xlsx (sem precisar dos dados brutos)."""
    from .metricas import fatos, modelo_esperado
    r = carregar_planilha(cfg, cfg.dir_saida / "analise_completa.xlsx")
    base = r["base_municipal"].drop(columns=["pct_esperado", "residuo_pp", "votos_acima_esperado"], errors="ignore")
    novo = modelo_esperado(cfg, base)
    residuos = novo.pop("_residuos")
    r.update(novo)
    r["base_municipal"] = base.merge(residuos, on=["sg_uf", "cd_municipio"], how="left")
    q = r["quociente"]
    q["faltaram_proximo_qe"] = (q["votos_partido"] // q["qe"] + 1) * q["qe"] - q["votos_partido"]
    r["fatos"] = fatos(cfg, base, r)
    return gerar_relatorio(cfg, r, sintetico=sintetico)


def markdown_simples(texto: str) -> str:
    """Converte o Markdown da leitura (títulos ###, listas -, **negrito**, parágrafos) em HTML."""
    def inline(t: str) -> str:
        t = html.escape(t)
        return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    saida, lista, paragrafo = [], [], []

    def fechar():
        if paragrafo:
            saida.append(f"<p>{inline(' '.join(paragrafo))}</p>")
            paragrafo.clear()
        if lista:
            saida.append("<ul>" + "".join(f"<li>{inline(i)}</li>" for i in lista) + "</ul>")
            lista.clear()
    for linha in texto.splitlines():
        l = linha.strip()
        if not l:
            fechar()
        elif l.startswith("#"):
            fechar()
            saida.append(f"<h3>{inline(l.lstrip('#').strip())}</h3>")
        elif l.startswith("- "):
            if paragrafo:
                fechar()
            lista.append(l[2:])
        else:
            if lista:
                fechar()
            paragrafo.append(l)
    fechar()
    return "\n".join(saida)
