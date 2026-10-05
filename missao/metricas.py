"""Métricas e análises do desempenho do partido e do seu candidato a Presidente.

Todas as funções recebem o dicionário de tabelas normalizadas (ver `carregar.py`) e devolvem
DataFrames prontos para o relatório. `analisar()` executa tudo e devolve um dict de resultados.

Convenções:
- "pct" = fração (0–1) dos votos válidos do cargo no município; nas tabelas finais vira % (×100).
- "Renan"/"presidente" = candidato a Presidente do partido (configurável em config.yaml).
- Deputado Estadual inclui Deputado Distrital (DF).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.optimize import lsq_linear

from .config import (DEP_DISTRITAL, DEP_ESTADUAL, DEP_FEDERAL, GOVERNADOR, NOME_CARGO, PRESIDENTE, SENADOR,
                     Config)

# Distribuição das 513 cadeiras da Câmara (usada só se os dados não trouxerem os eleitos)
VAGAS_CAMARA = {
    "SP": 70, "MG": 53, "RJ": 46, "BA": 39, "RS": 31, "PR": 30, "PE": 25, "CE": 22, "MA": 18, "GO": 17,
    "PA": 17, "SC": 16, "PB": 12, "ES": 10, "PI": 10, "AL": 9, "AC": 8, "AM": 8, "AP": 8, "DF": 8, "MS": 8,
    "MT": 8, "RN": 8, "RO": 8, "RR": 8, "SE": 8, "TO": 8,
}


def vagas_assembleia(vagas_camara: int) -> int:
    """CF art. 27: triplo da bancada federal até 12; acima disso, 36 + (bancada − 12)."""
    return vagas_camara * 3 if vagas_camara <= 12 else 36 + (vagas_camara - 12)


def div(a, b):
    """Divisão segura (NaN quando o denominador é 0)."""
    a = np.asarray(a, dtype="float64")
    b = np.asarray(b, dtype="float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(b != 0, a / np.where(b == 0, 1, b), np.nan)
    return r


def corr_ponderada(x, y, w) -> float:
    x, y, w = (np.asarray(v, dtype="float64") for v in (x, y, w))
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(w) & (w > 0)
    if ok.sum() < 3:
        return float("nan")
    x, y, w = x[ok], y[ok], w[ok]
    mx, my = np.average(x, weights=w), np.average(y, weights=w)
    cov = np.average((x - mx) * (y - my), weights=w)
    vx, vy = np.average((x - mx) ** 2, weights=w), np.average((y - my) ** 2, weights=w)
    return float(cov / math.sqrt(vx * vy)) if vx > 0 and vy > 0 else float("nan")


def elasticidade(x, y, w) -> float:
    """Inclinação da regressão ponderada log(y) ~ log(x): +1% em x ⇒ +β% em y."""
    x, y, w = (np.asarray(v, dtype="float64") for v in (x, y, w))
    ok = (x > 0) & (y > 0) & np.isfinite(x) & np.isfinite(y) & (w > 0)
    if ok.sum() < 5:
        return float("nan")
    X = sm.add_constant(np.log(x[ok]))
    return float(sm.WLS(np.log(y[ok]), X, weights=w[ok]).fit().params[1])


def hhi(votos: pd.Series) -> float:
    total = votos.sum()
    return float(((votos / total) ** 2).sum()) if total > 0 else float("nan")


def n0(v) -> str:
    return f"{v:,.0f}".replace(",", ".")


def n1(v) -> str:
    return f"{v:,.1f}".replace(",", "_").replace(".", ",").replace("_", ".")


def n2(v) -> str:
    return f"{v:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def logit(p):
    p = np.clip(np.asarray(p, dtype="float64"), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


# =========================================================================== base municipal

def _nomes_candidatos(cand: pd.DataFrame) -> dict[int, str]:
    return (cand.groupby("nr_candidato")["nm_urna"].agg(lambda s: s.mode().iat[0] if len(s.mode()) else "")
            .to_dict())


def _validos_cargo(t: dict, cargos: list[int]) -> pd.DataFrame:
    """Válidos por município para o(s) cargo(s): detalhe (preferência) ou soma dos partidos."""
    det = t.get("detalhe_mun")
    if det is not None and det["cd_cargo"].isin(cargos).any():
        d = det[det["cd_cargo"].isin(cargos)].groupby(["sg_uf", "cd_municipio"], as_index=False)["validos"].sum()
        if d["validos"].sum() > 0:
            return d
    p = t["partido_mun"]
    return (p[p["cd_cargo"].isin(cargos)].groupby(["sg_uf", "cd_municipio"], as_index=False)["votos_total"].sum()
            .rename(columns={"votos_total": "validos"}))


def montar_base(cfg: Config, t: dict) -> tuple[pd.DataFrame, dict[int, str]]:
    """Tabela municipal larga com tudo o que as análises usam (uma linha por município)."""
    chave = ["sg_uf", "cd_municipio"]
    mun = t["municipios"].copy()
    cm = t["cand_mun"]

    # ---------------- Presidente
    pres = cm[cm["cd_cargo"] == PRESIDENTE]
    nomes_pres = _nomes_candidatos(pres)
    larga = pres.pivot_table(index=chave, columns="nr_candidato", values="votos", aggfunc="sum", fill_value=0)
    validos_pres = larga.sum(axis=1).rename("validos_pres")
    ordem = larga.rank(axis=1, ascending=False, method="min")
    nr = cfg.presidente_numero
    b = pd.DataFrame(validos_pres)
    b["renan_votos"] = larga[nr] if nr in larga else 0
    b["renan_pos"] = ordem[nr] if nr in ordem else np.nan
    b["lider_pres_nr"] = larga.idxmax(axis=1)
    b["lider_pres"] = b["lider_pres_nr"].map(nomes_pres)
    b["lider_pres_pct"] = div(larga.max(axis=1), validos_pres)
    for c in larga.columns:
        b[f"pres_{c}_pct"] = div(larga[c], validos_pres)
    b = b.reset_index()
    base = mun.merge(b, on=chave, how="left")
    base["renan_votos"] = base["renan_votos"].fillna(0).astype("int64")
    base["validos_pres"] = base["validos_pres"].fillna(0).astype("int64")
    base["renan_pct"] = div(base["renan_votos"], base["validos_pres"])

    det = t.get("detalhe_mun")
    if det is not None:
        dp = det[det["cd_cargo"] == PRESIDENTE][chave + ["brancos", "nulos"]]
        base = base.merge(dp, on=chave, how="left")
        base["abstencao_pct"] = div(base["abstencoes"], base["aptos"])
        base["brancos_nulos_pct"] = div(base["brancos"] + base["nulos"], base["comparecimento"])

    # ---------------- Proporcionais (partido = soma nominal + legenda)
    pm = t["partido_mun"]
    for sufixo, cargos in (("df", [DEP_FEDERAL]), ("de", [DEP_ESTADUAL, DEP_DISTRITAL])):
        val = _validos_cargo(t, cargos).rename(columns={"validos": f"validos_{sufixo}"})
        meu = (pm[pm["cd_cargo"].isin(cargos) & (pm["nr_partido"] == cfg.partido_numero)]
               .groupby(chave, as_index=False)[["votos_nominais", "votos_legenda", "votos_total"]].sum()
               .rename(columns={"votos_nominais": f"{sufixo}_nominais", "votos_legenda": f"{sufixo}_legenda",
                                "votos_total": f"{sufixo}_total"}))
        base = base.merge(val, on=chave, how="left").merge(meu, on=chave, how="left")
        for c in (f"{sufixo}_nominais", f"{sufixo}_legenda", f"{sufixo}_total", f"validos_{sufixo}"):
            base[c] = base[c].fillna(0).astype("int64")
        base[f"{sufixo}_pct"] = div(base[f"{sufixo}_total"], base[f"validos_{sufixo}"])
        base[f"razao_{sufixo}"] = div(base[f"{sufixo}_total"], base["renan_votos"])

        # candidato do partido mais votado no município
        cands = cm[cm["cd_cargo"].isin(cargos) & (cm["nr_partido"] == cfg.partido_numero)]
        if len(cands):
            top = (cands.sort_values("votos", ascending=False).drop_duplicates(chave)
                   [chave + ["nm_urna", "nr_candidato", "votos"]]
                   .rename(columns={"nm_urna": f"top_{sufixo}_nome", "nr_candidato": f"top_{sufixo}_nr",
                                    "votos": f"top_{sufixo}_votos"}))
            base = base.merge(top, on=chave, how="left")
        else:
            base[f"top_{sufixo}_nome"], base[f"top_{sufixo}_nr"], base[f"top_{sufixo}_votos"] = None, np.nan, 0
        base[f"top_{sufixo}_votos"] = base[f"top_{sufixo}_votos"].fillna(0).astype("int64")

    # ---------------- Majoritários estaduais do partido
    for sufixo, cargo in (("gov", GOVERNADOR), ("sen", SENADOR)):
        todos = cm[cm["cd_cargo"] == cargo]
        val = todos.groupby(chave, as_index=False)["votos"].sum().rename(columns={"votos": f"validos_{sufixo}"})
        meu = (todos[todos["nr_partido"] == cfg.partido_numero].groupby(chave, as_index=False)["votos"].max()
               .rename(columns={"votos": f"{sufixo}_votos"}))
        base = base.merge(val, on=chave, how="left").merge(meu, on=chave, how="left")
        base[f"{sufixo}_votos"] = base[f"{sufixo}_votos"].fillna(0).astype("int64")
        base[f"{sufixo}_pct"] = div(base[f"{sufixo}_votos"], base[f"validos_{sufixo}"])

    # ---------------- Comparação (ex.: 2022) e perfil
    comp = t.get("comparacao_pres_mun")
    if comp is not None and len(comp):
        lc = comp.pivot_table(index=chave, columns="nr_candidato", values="votos", aggfunc="sum", fill_value=0)
        tot = lc.sum(axis=1)
        ref = cfg.referencia_2022 or {}
        cmp = pd.DataFrame(index=lc.index)
        for nrc in ref:
            if nrc in lc:
                cmp[f"ant_{nrc}_pct"] = div(lc[nrc], tot)
        cmp["ant_outros_pct"] = 1 - cmp.sum(axis=1)
        cmp["ant_validos"] = tot
        cmp = cmp.reset_index().drop(columns="sg_uf").groupby("cd_municipio").first()
        base = base.merge(cmp.reset_index(), on="cd_municipio", how="left")
    perfil = t.get("perfil_mun")
    if perfil is not None and len(perfil):
        base = base.merge(perfil, on=chave, how="left")

    faixas = cfg.faixas_eleitorado
    rotulos = [_rotulo_faixa(faixas[i], faixas[i + 1]) for i in range(len(faixas) - 1)]
    base["faixa_eleitorado"] = pd.cut(base["aptos"], bins=faixas, labels=rotulos, right=False)
    return base, nomes_pres


def _rotulo_faixa(a: int, b: int) -> str:
    fmt = lambda v: f"{v // 1000:,}k".replace(",", ".") if v < 10**6 else f"{v // 10**6}M"  # noqa: E731
    if a == 0:
        return f"até {fmt(b)}"
    if b >= 10**7:
        return f"{fmt(a)}+"
    return f"{fmt(a)}–{fmt(b)}"


# =========================================================================== análises

def resumo_geral(cfg: Config, t: dict, base: pd.DataFrame, nomes_pres: dict) -> pd.DataFrame:
    br = base
    nac = t["cand_mun"][t["cand_mun"]["cd_cargo"] == PRESIDENTE].groupby("nr_candidato")["votos"].sum()
    nac = nac.sort_values(ascending=False)
    pos = int((nac > nac.get(cfg.presidente_numero, 0)).sum() + 1)
    nacional = br[~br["exterior"]]
    linhas = [
        ("Votos do candidato a Presidente", int(br["renan_votos"].sum())),
        ("% dos válidos (Brasil + exterior)", 100 * br["renan_votos"].sum() / br["validos_pres"].sum()),
        ("Posição nacional", pos),
        ("Votos no exterior", int(br.loc[br["exterior"], "renan_votos"].sum())),
        ("Municípios com ao menos 1 voto", int((nacional["renan_votos"] > 0).sum())),
        ("Municípios sem nenhum voto", int((nacional["renan_votos"] == 0).sum())),
        ("Municípios com ≥ 5% dos válidos", int((nacional["renan_pct"] >= 0.05).sum())),
        ("Municípios com ≥ 10% dos válidos", int((nacional["renan_pct"] >= 0.10).sum())),
        ("Municípios em 1º lugar", int((nacional["renan_pos"] == 1).sum())),
        ("Municípios em 2º lugar", int((nacional["renan_pos"] == 2).sum())),
        ("Municípios em 3º lugar", int((nacional["renan_pos"] == 3).sum())),
    ]
    cu = t["cand_uf"]
    for sufixo, cargos, nome in (("df", [DEP_FEDERAL], "Deputado Federal"),
                                 ("de", [DEP_ESTADUAL, DEP_DISTRITAL], "Deputado Estadual/Distrital")):
        meus = cu[cu["cd_cargo"].isin(cargos) & (cu["nr_partido"] == cfg.partido_numero)]
        linhas += [
            (f"{nome}: votos do partido (nominal + legenda)", int(br[f"{sufixo}_total"].sum())),
            (f"{nome}: votos de legenda", int(br[f"{sufixo}_legenda"].sum())),
            (f"{nome}: % dos válidos", 100 * br[f"{sufixo}_total"].sum() / max(br[f"validos_{sufixo}"].sum(), 1)),
            (f"{nome}: candidatos com votos", int((meus["votos"] > 0).sum())),
            (f"{nome}: eleitos", int(meus["situacao"].fillna("").str.upper().str.startswith("ELEITO").sum())),
            (f"{nome}: votos do partido ÷ votos do presidente",
             br[f"{sufixo}_total"].sum() / max(br["renan_votos"].sum(), 1)),
        ]
    for cargo, nome in ((GOVERNADOR, "Governador"), (SENADOR, "Senador")):
        meus = cu[(cu["cd_cargo"] == cargo) & (cu["nr_partido"] == cfg.partido_numero)]
        linhas += [(f"{nome}: candidatos", len(meus)), (f"{nome}: votos somados", int(meus["votos"].sum())),
                   (f"{nome}: eleitos / 2º turno",
                    int((meus["situacao"].fillna("").str.upper().str.startswith("ELEITO")
                         | meus["situacao"].fillna("").str.upper().str.contains("2º TURNO|2O TURNO")).sum()))]
    return pd.DataFrame(linhas, columns=["indicador", "valor"], dtype=object)


def ranking_presidente(cfg: Config, base: pd.DataFrame, nomes_pres: dict) -> pd.DataFrame:
    cols = [c for c in base.columns if c.startswith("pres_") and c.endswith("_pct")]
    linhas = []
    for c in cols:
        nr = int(c.split("_")[1])
        votos = (base[c] * base["validos_pres"]).sum()
        linhas.append({"nr": nr, "candidato": nomes_pres.get(nr, str(nr)), "votos": round(votos),
                       "municipios_em_1o": int((base["lider_pres_nr"] == nr).sum())})
    df = pd.DataFrame(linhas).sort_values("votos", ascending=False)
    df["pct"] = 100 * df["votos"] / df["votos"].sum()
    return df.reset_index(drop=True)


def por_uf(cfg: Config, base: pd.DataFrame) -> pd.DataFrame:
    g = base.groupby("sg_uf")
    nac_pct = base["renan_votos"].sum() / base["validos_pres"].sum()
    df = pd.DataFrame({
        "regiao": g["regiao"].first(),
        "eleitorado": g["aptos"].sum(),
        "validos_pres": g["validos_pres"].sum(),
        "renan_votos": g["renan_votos"].sum(),
        "df_total": g["df_total"].sum(), "df_legenda": g["df_legenda"].sum(), "validos_df": g["validos_df"].sum(),
        "de_total": g["de_total"].sum(), "validos_de": g["validos_de"].sum(),
        "gov_votos": g["gov_votos"].sum(), "sen_votos": g["sen_votos"].sum(),
        "municipios": g.size(),
        "mun_renan_1o_3o": g["renan_pos"].apply(lambda s: int((s <= 3).sum())),
    })
    df["renan_pct"] = 100 * div(df["renan_votos"], df["validos_pres"])
    df["idr"] = df["renan_pct"] / (100 * nac_pct)
    df["participacao_no_total"] = 100 * df["renan_votos"] / df["renan_votos"].sum()
    df["df_pct"] = 100 * div(df["df_total"], df["validos_df"])
    df["de_pct"] = 100 * div(df["de_total"], df["validos_de"])
    df["razao_df_renan"] = div(df["df_total"], df["renan_votos"])
    df["razao_de_renan"] = div(df["de_total"], df["renan_votos"])
    df["legenda_por_renan"] = div(df["df_legenda"], df["renan_votos"])
    df["corr_renan_df_mun"] = [corr_ponderada(x["renan_pct"], x["df_pct"], x["validos_df"])
                               for _, x in base.groupby("sg_uf")]
    return df.sort_values("renan_pct", ascending=False).reset_index()


def por_grupo(base: pd.DataFrame, coluna: str) -> pd.DataFrame:
    g = base.groupby(coluna, observed=True)
    df = pd.DataFrame({
        "municipios": g.size(), "eleitorado": g["aptos"].sum(), "renan_votos": g["renan_votos"].sum(),
        "validos_pres": g["validos_pres"].sum(), "df_total": g["df_total"].sum(), "validos_df": g["validos_df"].sum(),
        "mediana_mun_pct": 100 * g["renan_pct"].median(),
    })
    df["renan_pct"] = 100 * div(df["renan_votos"], df["validos_pres"])
    df["df_pct"] = 100 * div(df["df_total"], df["validos_df"])
    df["participacao_no_total"] = 100 * df["renan_votos"] / df["renan_votos"].sum()
    df["razao_df_renan"] = div(df["df_total"], df["renan_votos"])
    return df.reset_index()


def capitais(base: pd.DataFrame) -> pd.DataFrame:
    c = base[base["capital"]].copy()
    c["renan_pct"] *= 100
    c["df_pct"] *= 100
    uf_pct = base.groupby("sg_uf").apply(lambda x: x["renan_votos"].sum() / max(x["validos_pres"].sum(), 1),
                                         include_groups=False)
    c["pct_uf"] = 100 * c["sg_uf"].map(uf_pct)
    c["capital_vs_uf"] = c["renan_pct"] / c["pct_uf"]
    cols = ["nm_municipio", "sg_uf", "aptos", "renan_votos", "renan_pct", "renan_pos", "pct_uf", "capital_vs_uf",
            "df_total", "df_pct", "razao_df", "lider_pres"]
    return c[cols].sort_values("renan_pct", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------- distorções

def suavizar_eb(base: pd.DataFrame) -> pd.DataFrame:
    """Encolhimento empírico-bayesiano (beta-binomial, método dos momentos) do % do candidato por UF.

    Municípios pequenos têm % muito ruidoso (3 votos em 300 eleitores = 1%, 10 votos = 3,3%). O % suavizado
    puxa cada município para a média da UF na proporção do seu tamanho, permitindo comparar distorções
    reais entre cidades de portes diferentes.
    """
    b = base[(~base["exterior"]) & (base["validos_pres"] > 0)].copy()

    def _prior(x, n):
        p = x.sum() / n.sum()
        k = len(n)
        s2 = np.sum(n * (x / n - p) ** 2) / n.sum()
        tau2 = s2 - p * (1 - p) * k / n.sum()
        if not np.isfinite(tau2) or tau2 <= 0 or k < 5:
            return p, np.nan
        return p, p * (1 - p) / tau2 - 1

    p_nac, m_nac = _prior(b["renan_votos"].to_numpy(float), b["validos_pres"].to_numpy(float))
    m_nac = m_nac if np.isfinite(m_nac) else 1000.0
    resultados = []
    for uf, x in b.groupby("sg_uf"):
        p, m = _prior(x["renan_votos"].to_numpy(float), x["validos_pres"].to_numpy(float))
        m = m if np.isfinite(m) else m_nac
        y = x[["sg_uf", "cd_municipio"]].copy()
        y["pct_uf"] = p
        y["pct_suav"] = (x["renan_votos"] + p * m) / (x["validos_pres"] + m)
        resultados.append(y)
    s = pd.concat(resultados)
    s["idr_suav"] = s["pct_suav"] / s["pct_uf"]
    lg = logit(s["pct_suav"])
    s["_lg"] = lg
    med = s.groupby("sg_uf")["_lg"].transform("median")
    mad = s.groupby("sg_uf")["_lg"].transform(lambda v: np.median(np.abs(v - np.median(v))))
    s["z_robusto"] = (s["_lg"] - med) / (1.4826 * mad.replace(0, np.nan))
    return s.drop(columns="_lg")


def distorcoes(cfg: Config, base: pd.DataFrame, suav: pd.DataFrame, n: int = 40) -> dict[str, pd.DataFrame]:
    b = base.merge(suav, on=["sg_uf", "cd_municipio"], how="inner")
    b["renan_pct100"] = 100 * b["renan_pct"]
    b["pct_uf100"] = 100 * b["pct_uf"]
    b["pct_suav100"] = 100 * b["pct_suav"]
    b["df_pct100"] = 100 * b["df_pct"]
    b["gap_pres_df_pp"] = b["renan_pct100"] - b["df_pct100"]
    cols = ["nm_municipio", "sg_uf", "aptos", "validos_pres", "renan_votos", "renan_pct100", "pct_uf100",
            "pct_suav100", "idr_suav", "z_robusto", "renan_pos", "df_total", "df_pct100", "razao_df", "top_df_nome"]
    filtro = b["aptos"] >= 1000
    out = {
        "distorcao_positiva": b[filtro].nlargest(n, "z_robusto")[cols],
        "distorcao_negativa": b[filtro & (b["aptos"] >= 20000)].nsmallest(n, "z_robusto")[cols],
        "gap_pres_maior_que_dep": b[filtro & (b["renan_votos"] >= 50)].nlargest(n, "gap_pres_df_pp")[cols + ["gap_pres_df_pp"]],
        "gap_dep_maior_que_pres": b[filtro & (b["df_total"] >= 50)].nsmallest(n, "gap_pres_df_pp")[cols + ["gap_pres_df_pp"]],
    }
    resumo = b.groupby("sg_uf").agg(municipios=("cd_municipio", "size"),
                                    distorcao_pos_z3=("z_robusto", lambda z: int((z >= 3).sum())),
                                    distorcao_neg_z3=("z_robusto", lambda z: int((z <= -3).sum())),
                                    amplitude_pct_suav=("pct_suav100", lambda v: v.max() - v.min()))
    out["distorcao_por_uf"] = resumo.reset_index().sort_values("distorcao_pos_z3", ascending=False)
    return {k: v.reset_index(drop=True) for k, v in out.items()}


# --------------------------------------------------------------------------- rankings

def rankings(cfg: Config, base: pd.DataFrame, n: int = 50) -> dict[str, pd.DataFrame]:
    b = base[~base["exterior"]].copy()
    b["renan_pct100"] = 100 * b["renan_pct"]
    b["df_pct100"] = 100 * b["df_pct"]
    cols = ["nm_municipio", "sg_uf", "aptos", "faixa_eleitorado", "renan_votos", "renan_pct100", "renan_pos",
            "lider_pres", "df_total", "df_pct100", "top_df_nome"]
    grandes = b[b["aptos"] >= cfg.min_eleitores_ranking]
    out = {
        "top_pct": grandes.nlargest(n, "renan_pct100")[cols],
        "top_pct_todos": b[b["validos_pres"] >= 100].nlargest(n, "renan_pct100")[cols],
        "bottom_pct_grandes": b[b["aptos"] >= 50000].nsmallest(n, "renan_pct100")[cols],
        "top_votos": b.nlargest(n, "renan_votos")[cols],
        "top_pct_por_faixa": (b[b["validos_pres"] >= 100].sort_values("renan_pct100", ascending=False)
                              .groupby("faixa_eleitorado", observed=True).head(10)
                              .sort_values(["faixa_eleitorado", "renan_pct100"], ascending=[True, False])[cols]),
        "top_pct_por_uf": (grandes.sort_values("renan_pct100", ascending=False).groupby("sg_uf").head(5)
                           .sort_values(["sg_uf", "renan_pct100"], ascending=[True, False])[cols]),
        "podio": b[b["renan_pos"] <= 2].sort_values(["renan_pos", "renan_pct100"], ascending=[True, False])[cols],
        "sem_votos": b[b["renan_votos"] == 0].nlargest(n, "aptos")[cols],
    }
    return {k: v.reset_index(drop=True) for k, v in out.items()}


def concentracao(base: pd.DataFrame) -> pd.DataFrame:
    """Quantos municípios concentram X% dos votos do candidato vs. X% dos válidos do país."""
    b = base[~base["exterior"]]
    linhas = []
    for alvo in (0.25, 0.5, 0.75, 0.9):
        r = b["renan_votos"].sort_values(ascending=False).cumsum() / b["renan_votos"].sum()
        v = b["validos_pres"].sort_values(ascending=False).cumsum() / b["validos_pres"].sum()
        linhas.append({"fatia_dos_votos": f"{int(alvo * 100)}%",
                       "municipios_candidato": int((r < alvo).sum() + 1),
                       "municipios_eleitorado_geral": int((v < alvo).sum() + 1)})
    return pd.DataFrame(linhas)


# --------------------------------------------------------------------------- acertos e erros (modelo)

def _sem_colinearidade(b: pd.DataFrame, colunas: list[str], r2_max: float = 0.9) -> list[str]:
    """Descarta covariáveis quase colineares às já escolhidas (ex.: fatias de votos que somam 100%).

    Entre as fatias do ano de comparação, a maior (em média) é a primeira a sair, virando a categoria de
    referência; as demais são lidas como "trocar 1 dp de votos do candidato de referência por este".
    """
    ant = sorted([c for c in colunas if c.startswith("ant_")], key=lambda c: -b[c].mean())
    ordem = [c for c in colunas if not c.startswith("ant_")] + ant[1:] + ant[:1]
    escolhidas: list[str] = []
    for c in ordem:
        if escolhidas:
            X = sm.add_constant(b[escolhidas].to_numpy(float))
            r2 = sm.OLS(b[c].to_numpy(float), X).fit().rsquared
            if r2 > r2_max:
                continue
        escolhidas.append(c)
    return escolhidas


def modelo_esperado(cfg: Config, base: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Modelo do % esperado do candidato em cada município a partir do perfil do município.

    GLM binomial (logit) ponderado pelos válidos. Covariáveis disponíveis entre: efeito fixo de UF, porte
    (log eleitorado), capital, abstenção, votação de referência no ano de comparação (ex.: Bolsonaro/Lula/
    Ciro/Tebet/d'Avila 2022) e perfil do eleitorado (sexo, idade, escolaridade). O resíduo mede o quanto o
    candidato foi melhor ("acerto") ou pior ("erro") do que municípios parecidos.
    """
    b = base[(~base["exterior"]) & (base["validos_pres"] >= 50)].copy()
    continuas = ["log_aptos", "abstencao_pct"]
    b["log_aptos"] = np.log(b["aptos"].clip(lower=1))
    continuas += [c for c in b.columns if c.startswith("ant_") and c.endswith("_pct") and c != "ant_outros_pct"]
    continuas += [c for c in ("pct_fem", "pct_16_24", "pct_25_34", "pct_60m", "pct_superior", "pct_fund_inc")
                  if c in b.columns]
    continuas = [c for c in continuas if c in b.columns and b[c].notna().mean() > 0.9 and b[c].std() > 0]
    b = b.dropna(subset=continuas)
    continuas = _sem_colinearidade(b, continuas)
    Z = (b[continuas] - b[continuas].mean()) / b[continuas].std()
    X = pd.concat([Z, b[["capital"]].astype(float),
                   pd.get_dummies(b["sg_uf"], prefix="uf", drop_first=True, dtype=float)], axis=1)
    X = sm.add_constant(X)
    y = b["renan_pct"].to_numpy()
    modelo = sm.GLM(y, X, family=sm.families.Binomial(), var_weights=b["validos_pres"].to_numpy()).fit(scale="X2")
    b["pct_esperado"] = modelo.predict(X)
    b["votos_esperados"] = b["pct_esperado"] * b["validos_pres"]
    b["votos_acima_esperado"] = b["renan_votos"] - b["votos_esperados"]
    b["razao_real_esperado"] = div(b["renan_pct"], b["pct_esperado"])
    b["residuo_pp"] = 100 * (b["renan_pct"] - b["pct_esperado"])

    pseudo_r2 = 1 - modelo.deviance / modelo.null_deviance
    coefs = pd.DataFrame({"variavel": modelo.params.index, "coef_logit_por_1dp": modelo.params.values,
                          "erro_padrao": modelo.bse.values, "p_valor": modelo.pvalues.values})
    coefs = coefs[~coefs["variavel"].str.startswith("uf_")]
    coefs["efeito_relativo_pct"] = 100 * (np.exp(coefs["coef_logit_por_1dp"]) - 1)
    coefs.loc[coefs["variavel"] == "const", "efeito_relativo_pct"] = np.nan

    cols = ["nm_municipio", "sg_uf", "aptos", "renan_votos", "renan_pct", "pct_esperado", "residuo_pp",
            "razao_real_esperado", "votos_esperados", "votos_acima_esperado", "df_total", "top_df_nome"]
    show = b[cols].copy()
    show["renan_pct"] *= 100
    show["pct_esperado"] *= 100
    grandes = show[show["aptos"] >= 20000]
    uf = b.groupby("sg_uf")[["renan_votos", "votos_esperados"]].sum()
    uf["votos_acima_esperado"] = uf["renan_votos"] - uf["votos_esperados"]
    uf["razao_real_esperado"] = uf["renan_votos"] / uf["votos_esperados"]
    faixa = b.groupby("faixa_eleitorado", observed=True)[["renan_votos", "votos_esperados"]].sum()
    faixa["razao_real_esperado"] = faixa["renan_votos"] / faixa["votos_esperados"]
    meta = pd.DataFrame([
        ("Municípios no modelo", len(b)), ("Pseudo-R² (deviance)", pseudo_r2),
        ("Covariáveis contínuas", ", ".join(continuas)), ("Efeito fixo de UF", "sim"),
        ("Dispersão (X²/gl)", modelo.scale),
    ], columns=["item", "valor"])
    return {
        "modelo_meta": meta,
        "modelo_coeficientes": coefs.sort_values("coef_logit_por_1dp", ascending=False).reset_index(drop=True),
        "acertos_absolutos": show.nlargest(40, "votos_acima_esperado").reset_index(drop=True),
        "erros_absolutos": show.nsmallest(40, "votos_acima_esperado").reset_index(drop=True),
        "acertos_relativos": grandes.nlargest(40, "razao_real_esperado").reset_index(drop=True),
        "erros_relativos": grandes.nsmallest(40, "razao_real_esperado").reset_index(drop=True),
        "esperado_por_uf": uf.sort_values("razao_real_esperado", ascending=False).reset_index(),
        "esperado_por_faixa": faixa.reset_index(),
        "_residuos": b[["sg_uf", "cd_municipio", "pct_esperado", "residuo_pp", "votos_acima_esperado"]],
    }


# --------------------------------------------------------------------------- quociente eleitoral

def quociente(cfg: Config, t: dict, base: pd.DataFrame) -> pd.DataFrame:
    """Distância do partido ao quociente eleitoral (QE) em cada UF — onde faltou pouco para eleger."""
    cu = t["cand_uf"]
    pm = t["partido_mun"]
    renan_uf = base.groupby("sg_uf")["renan_votos"].sum()
    linhas = []
    for sufixo, cargos, nome in (("df", [DEP_FEDERAL], "Dep. Federal"),
                                 ("de", [DEP_ESTADUAL, DEP_DISTRITAL], "Dep. Estadual/Distrital")):
        p = pm[pm["cd_cargo"].isin(cargos)]
        c = cu[cu["cd_cargo"].isin(cargos)]
        for uf, pu in p.groupby("sg_uf"):
            validos = pu["votos_total"].sum()
            eleitos = c[(c["sg_uf"] == uf) & c["situacao"].fillna("").str.upper().str.startswith("ELEITO")]
            vagas = len(eleitos)
            if vagas == 0:
                vc = VAGAS_CAMARA.get(uf, 8)
                vagas = vc if sufixo == "df" else (24 if uf == "DF" else vagas_assembleia(vc))
            qe = validos / vagas
            qe = math.floor(qe) + (1 if qe - math.floor(qe) > 0.5 else 0)
            meu = pu[pu["nr_partido"] == cfg.partido_numero]
            votos = int(meu["votos_total"].sum())
            meus_c = c[(c["sg_uf"] == uf) & (c["nr_partido"] == cfg.partido_numero)].sort_values("votos", ascending=False)
            top = meus_c.iloc[0] if len(meus_c) else None
            # votação do partido comparada com os demais na UF
            por_partido = pu.groupby("nr_partido")["votos_total"].sum().sort_values(ascending=False)
            linhas.append({
                "cargo": nome, "sg_uf": uf, "vagas": vagas, "validos": int(validos), "qe": qe,
                "votos_partido": votos, "pct_do_qe": 100 * votos / qe if qe else np.nan,
                "quocientes_partidarios": votos // qe if qe else 0,
                "faltaram_para_qe": max(0, qe - votos), "faltaram_para_80pct_qe": max(0, math.ceil(0.8 * qe) - votos),
                "eleitos": int(meus_c["situacao"].fillna("").str.upper().str.startswith("ELEITO").sum()),
                "candidatos": int(len(meus_c)),
                "mais_votado": top["nm_urna"] if top is not None else None,
                "votos_mais_votado": int(top["votos"]) if top is not None else 0,
                "mais_votado_pct_qe": 100 * top["votos"] / qe if top is not None and qe else np.nan,
                "posicao_partido_na_uf": int((por_partido > votos).sum() + 1) if votos else None,
                "votos_presidente_na_uf": int(renan_uf.get(uf, 0)),
                "conversao_necessaria_pct": 100 * qe / renan_uf.get(uf, np.nan) if renan_uf.get(uf, 0) else np.nan,
                "conversao_obtida_pct": 100 * votos / renan_uf.get(uf, np.nan) if renan_uf.get(uf, 0) else np.nan,
            })
    df = pd.DataFrame(linhas)
    return df.sort_values(["cargo", "pct_do_qe"], ascending=[True, False]).reset_index(drop=True)


# --------------------------------------------------------------------------- guarda-chuva

def guarda_chuva_partidos(cfg: Config, t: dict, base: pd.DataFrame, nomes_pres: dict) -> pd.DataFrame:
    """Compara o 'efeito guarda-chuva' do candidato do partido com o dos demais presidenciáveis.

    Para cada presidenciável (número = número do partido): votos do partido para Dep. Federal e Estadual
    (nominal + legenda) divididos pelos votos do presidenciável; legenda ÷ presidente; correlação e
    elasticidade município a município entre % do presidenciável e % do partido para Dep. Federal.
    """
    pm = t["partido_mun"]
    chave = ["sg_uf", "cd_municipio"]
    df_m = pm[pm["cd_cargo"] == DEP_FEDERAL]
    de_m = pm[pm["cd_cargo"].isin([DEP_ESTADUAL, DEP_DISTRITAL])]
    val_df = base.set_index(chave)["validos_df"]
    fed = df_m.drop_duplicates("nr_partido").set_index("nr_partido")["sg_federacao"].replace("", np.nan)
    linhas = []
    for c in [c for c in base.columns if c.startswith("pres_") and c.endswith("_pct")]:
        nr = int(c.split("_")[1])
        pres_votos = (base[c] * base["validos_pres"]).sum()
        if pres_votos <= 0:
            continue
        p_df = df_m[df_m["nr_partido"] == nr]
        p_de = de_m[de_m["nr_partido"] == nr]
        por_mun = p_df.groupby(chave)["votos_total"].sum().reindex(val_df.index).fillna(0)
        x = base.set_index(chave)[c].reindex(val_df.index)
        y = div(por_mun, val_df)
        sg_fed = fed.get(nr)
        fed_votos = df_m[df_m["sg_federacao"] == sg_fed]["votos_total"].sum() if isinstance(sg_fed, str) else np.nan
        linhas.append({
            "nr": nr, "candidato": nomes_pres.get(nr, str(nr)),
            "partido": p_df["sg_partido"].iat[0] if len(p_df) else "",
            "federacao": sg_fed if isinstance(sg_fed, str) else "",
            "votos_presidente": round(pres_votos),
            "df_votos_partido": int(p_df["votos_total"].sum()),
            "df_legenda": int(p_df["votos_legenda"].sum()),
            "de_votos_partido": int(p_de["votos_total"].sum()),
            "razao_df": p_df["votos_total"].sum() / pres_votos,
            "razao_df_federacao": fed_votos / pres_votos if np.isfinite(fed_votos) else np.nan,
            "razao_de": p_de["votos_total"].sum() / pres_votos,
            "legenda_por_voto_pres": p_df["votos_legenda"].sum() / pres_votos,
            "legenda_share_partido": div(p_df["votos_legenda"].sum(), p_df["votos_total"].sum()).item(),
            "ufs_com_chapa_df": int(p_df.groupby("sg_uf")["votos_total"].sum().gt(0).sum()),
            "corr_mun_pres_df": corr_ponderada(x, y, val_df),
            "elasticidade_df": elasticidade(x, y, val_df),
        })
    out = pd.DataFrame(linhas).sort_values("votos_presidente", ascending=False).reset_index(drop=True)
    out["destaque"] = out["nr"] == cfg.presidente_numero
    return out


def guarda_chuva_quintis(base: pd.DataFrame) -> pd.DataFrame:
    """Municípios agrupados pelo % do presidente (quintis ponderados por válidos): o partido acompanha?"""
    b = base[(~base["exterior"]) & (base["validos_pres"] > 0)].sort_values("renan_pct").copy()
    acum = b["validos_pres"].cumsum() / b["validos_pres"].sum()
    b["quintil"] = np.minimum((acum * 5).apply(np.ceil), 5).astype(int)
    g = b.groupby("quintil")
    out = pd.DataFrame({
        "municipios": g.size(), "pct_pres_min": 100 * g["renan_pct"].min(), "pct_pres_max": 100 * g["renan_pct"].max(),
        "renan_votos": g["renan_votos"].sum(), "validos_pres": g["validos_pres"].sum(),
        "df_total": g["df_total"].sum(), "validos_df": g["validos_df"].sum(),
        "df_legenda": g["df_legenda"].sum(), "de_total": g["de_total"].sum(), "validos_de": g["validos_de"].sum(),
    })
    out["renan_pct"] = 100 * out["renan_votos"] / out["validos_pres"]
    out["df_pct"] = 100 * div(out["df_total"], out["validos_df"])
    out["de_pct"] = 100 * div(out["de_total"], out["validos_de"])
    out["razao_df_renan"] = div(out["df_total"], out["renan_votos"])
    out["legenda_por_renan"] = div(out["df_legenda"], out["renan_votos"])
    return out.reset_index()


def guarda_chuva_resumo(base: pd.DataFrame) -> pd.DataFrame:
    """Indicadores nacionais do arrasto do presidente sobre a chapa."""
    b = base[~base["exterior"]]
    w = b["validos_df"]
    linhas = [
        ("Votos Dep. Federal ÷ votos do presidente", b["df_total"].sum() / max(b["renan_votos"].sum(), 1)),
        ("Votos Dep. Estadual ÷ votos do presidente", b["de_total"].sum() / max(b["renan_votos"].sum(), 1)),
        ("Votos de legenda (DF) ÷ votos do presidente", b["df_legenda"].sum() / max(b["renan_votos"].sum(), 1)),
        ("Legenda como % dos votos do partido (DF)", 100 * b["df_legenda"].sum() / max(b["df_total"].sum(), 1)),
        ("Retenção mínima (Σ min(DF, pres) ÷ Σ pres)",
         np.minimum(b["df_total"], b["renan_votos"]).sum() / max(b["renan_votos"].sum(), 1)),
        ("Correlação municipal % pres × % DF (ponderada)", corr_ponderada(b["renan_pct"], b["df_pct"], w)),
        ("Elasticidade % DF em relação ao % pres", elasticidade(b["renan_pct"], b["df_pct"], w)),
        ("Correlação municipal % pres × % DE (ponderada)", corr_ponderada(b["renan_pct"], b["de_pct"], b["validos_de"])),
        ("Municípios onde DF > presidente", int((b["df_total"] > b["renan_votos"]).sum())),
        ("Municípios onde DE > presidente", int((b["de_total"] > b["renan_votos"]).sum())),
        ("Municípios com presidente votado e sem nenhum voto em DF do partido",
         int(((b["renan_votos"] > 0) & (b["df_total"] == 0)).sum())),
    ]
    return pd.DataFrame(linhas, columns=["indicador", "valor"], dtype=object)


# --------------------------------------------------------------------------- deputados > presidente

def deputados_maior_que_presidente(cfg: Config, t: dict, base: pd.DataFrame) -> dict[str, pd.DataFrame]:
    b = base[~base["exterior"]].copy()
    cols = ["nm_municipio", "sg_uf", "aptos", "renan_votos", "renan_pct", "df_total", "df_nominais", "df_legenda",
            "razao_df", "top_df_nome", "top_df_votos", "de_total", "razao_de", "top_de_nome", "top_de_votos"]
    b["renan_pct"] = 100 * b["renan_pct"]
    df_maior = b[b["df_total"] > b["renan_votos"]].sort_values("razao_df", ascending=False)[cols]
    de_maior = b[b["de_total"] > b["renan_votos"]].sort_values("razao_de", ascending=False)[cols]

    cm = t["cand_mun"]
    chave = ["sg_uf", "cd_municipio"]
    meus = cm[(cm["nr_partido"] == cfg.partido_numero) & cm["cd_cargo"].isin([DEP_FEDERAL, DEP_ESTADUAL, DEP_DISTRITAL])]
    ind = meus.merge(b[chave + ["renan_votos", "aptos"]], on=chave, how="inner")
    ind = ind[ind["votos"] > ind["renan_votos"]].copy()
    ind["cargo"] = ind["cd_cargo"].map(NOME_CARGO)
    ind["razao_cand_renan"] = div(ind["votos"], ind["renan_votos"])
    individuais = ind.sort_values("votos", ascending=False)[
        ["nm_urna", "nr_candidato", "cargo", "sg_uf", "nm_municipio", "aptos", "votos", "renan_votos", "razao_cand_renan"]]

    por_cand = (ind.groupby(["nm_urna", "nr_candidato", "cargo", "sg_uf"], as_index=False)
                .agg(municipios_acima_do_presidente=("cd_municipio", "size"), votos_nesses_municipios=("votos", "sum"),
                     votos_presidente_nesses=("renan_votos", "sum"))
                .sort_values("municipios_acima_do_presidente", ascending=False))
    total_cand = meus.groupby(["nr_candidato", "sg_uf", "cd_cargo"])["votos"].sum().rename("votos_totais").reset_index()
    total_cand["cargo"] = total_cand["cd_cargo"].map(NOME_CARGO)
    por_cand = por_cand.merge(total_cand.drop(columns="cd_cargo"), on=["nr_candidato", "sg_uf", "cargo"], how="left")
    por_cand["pct_votos_do_cand_nesses"] = 100 * div(por_cand["votos_nesses_municipios"], por_cand["votos_totais"])

    por_uf = pd.DataFrame({
        "municipios": b.groupby("sg_uf").size(),
        "df_maior_que_pres": b[b["df_total"] > b["renan_votos"]].groupby("sg_uf").size(),
        "de_maior_que_pres": b[b["de_total"] > b["renan_votos"]].groupby("sg_uf").size(),
        "algum_candidato_maior": ind.groupby("sg_uf")["cd_municipio"].nunique(),
    }).fillna(0).astype(int)
    por_uf["pct_mun_df_maior"] = 100 * por_uf["df_maior_que_pres"] / por_uf["municipios"]
    perfil = pd.DataFrame({
        "todos_municipios": b.groupby("faixa_eleitorado", observed=True).size(),
        "df_maior_que_pres": b[b["df_total"] > b["renan_votos"]].groupby("faixa_eleitorado", observed=True).size(),
    }).fillna(0)
    perfil["pct"] = 100 * div(perfil["df_maior_que_pres"], perfil["todos_municipios"])
    return {
        "df_maior_que_pres": df_maior.reset_index(drop=True),
        "de_maior_que_pres": de_maior.reset_index(drop=True),
        "candidato_maior_que_pres": individuais.reset_index(drop=True),
        "candidatos_puxadores_locais": por_cand.reset_index(drop=True),
        "maior_que_pres_por_uf": por_uf.sort_values("df_maior_que_pres", ascending=False).reset_index(),
        "maior_que_pres_por_porte": perfil.reset_index(),
    }


# --------------------------------------------------------------------------- candidatos do partido

def candidatos_partido(cfg: Config, t: dict, base: pd.DataFrame, qe: pd.DataFrame) -> pd.DataFrame:
    cm, cu = t["cand_mun"], t["cand_uf"]
    meus = cu[cu["nr_partido"] == cfg.partido_numero].copy()
    meus = meus[meus["cd_cargo"] != PRESIDENTE]
    chave = ["sg_uf", "cd_municipio"]
    b = base.set_index(chave)
    por_cand = {sq: g.set_index(chave)["votos"] for sq, g in cm[cm["nr_partido"] == cfg.partido_numero].groupby("sq_candidato")}
    vazio = pd.Series(dtype="float64")
    linhas = []
    for _, c in meus.iterrows():
        vm = por_cand.get(c["sq_candidato"], vazio)
        cargo = c["cd_cargo"]
        val_col = {DEP_FEDERAL: "validos_df", DEP_ESTADUAL: "validos_de", DEP_DISTRITAL: "validos_de",
                   GOVERNADOR: "validos_gov", SENADOR: "validos_sen"}[cargo]
        bu = b[b.index.get_level_values(0) == c["sg_uf"]]
        vm = vm.reindex(bu.index).fillna(0)
        top_idx = vm.idxmax() if vm.sum() > 0 else None
        val_uf = bu[val_col].sum()
        nome_qe = "Dep. Federal" if cargo == DEP_FEDERAL else "Dep. Estadual/Distrital"
        q = qe[(qe["cargo"] == nome_qe) & (qe["sg_uf"] == c["sg_uf"])]
        linhas.append({
            "cargo": NOME_CARGO.get(cargo, cargo), "sg_uf": c["sg_uf"], "nr": c["nr_candidato"], "nome": c["nm_urna"],
            "situacao": c["situacao"], "votos": int(c["votos"]),
            "pct_uf": 100 * c["votos"] / val_uf if val_uf else np.nan,
            "municipios_com_voto": int((vm > 0).sum()),
            "hhi_concentracao": hhi(vm),
            "reduto": bu.loc[top_idx, "nm_municipio"] if top_idx is not None else None,
            "pct_votos_no_reduto": 100 * vm.max() / vm.sum() if vm.sum() else np.nan,
            "corr_com_presidente": corr_ponderada(div(vm, bu[val_col]), bu["renan_pct"], bu[val_col]),
            "votos_cand_por_voto_pres_uf": c["votos"] / max(bu["renan_votos"].sum(), 1),
            "pct_do_qe": 100 * c["votos"] / q["qe"].iat[0] if len(q) and cargo in (6, 7, 8) else np.nan,
        })
    df = pd.DataFrame(linhas)
    if df.empty:
        return df
    df["rank_no_partido_uf"] = df.groupby(["cargo", "sg_uf"])["votos"].rank(ascending=False, method="min")
    return df.sort_values(["cargo", "votos"], ascending=[True, False]).reset_index(drop=True)


# --------------------------------------------------------------------------- zonas, exterior, origem

def zonas(cfg: Config, t: dict, base: pd.DataFrame) -> dict[str, pd.DataFrame]:
    cz = t.get("cand_zona")
    if cz is None or cz.empty:
        return {}
    pres = cz[cz["cd_cargo"] == PRESIDENTE]
    chave = ["sg_uf", "cd_municipio", "nm_municipio", "nr_zona"]
    tot = pres.groupby(chave)["votos"].sum().rename("validos")
    ren = pres[pres["nr_candidato"] == cfg.presidente_numero].groupby(chave)["votos"].sum().rename("renan_votos")
    z = pd.concat([tot, ren], axis=1).fillna(0).reset_index()
    z["renan_pct"] = 100 * div(z["renan_votos"], z["validos"])
    z = z[z["sg_uf"] != "ZZ"]
    capitais_ = base.loc[base["capital"], ["sg_uf", "cd_municipio"]]
    zc = z.merge(capitais_, on=["sg_uf", "cd_municipio"])
    amplitude = (z.groupby(["sg_uf", "cd_municipio", "nm_municipio"])
                 .agg(zonas=("nr_zona", "size"), pct_min=("renan_pct", "min"), pct_max=("renan_pct", "max"),
                      renan_votos=("renan_votos", "sum"))
                 .reset_index())
    amplitude = amplitude[amplitude["zonas"] >= 3]
    amplitude["amplitude_pp"] = amplitude["pct_max"] - amplitude["pct_min"]
    return {
        "zonas_top": z[z["validos"] >= 5000].nlargest(40, "renan_pct").reset_index(drop=True),
        "zonas_capitais": zc.sort_values(["sg_uf", "renan_pct"], ascending=[True, False]).reset_index(drop=True),
        "zonas_amplitude": amplitude.sort_values("amplitude_pp", ascending=False).head(40).reset_index(drop=True),
    }


def exterior(base: pd.DataFrame) -> pd.DataFrame:
    e = base[base["exterior"]].copy()
    if e.empty:
        return e
    e["renan_pct"] *= 100
    return (e[["nm_municipio", "validos_pres", "renan_votos", "renan_pct", "renan_pos", "lider_pres"]]
            .sort_values("renan_votos", ascending=False).reset_index(drop=True))


def origem_votos(cfg: Config, base: pd.DataFrame) -> pd.DataFrame:
    """Regressão ecológica (mínimos quadrados com coeficientes entre 0 e 1, ponderada): % do candidato em cada município
    explicado pelas fatias dos candidatos do ano de comparação. Coeficiente ≈ fração do eleitorado de cada
    candidato de referência que migrou para o candidato do partido. Sujeita à falácia ecológica: indica
    associação geográfica, não comportamento individual."""
    cols = [c for c in base.columns if c.startswith("ant_") and c.endswith("_pct")]
    if not cols:
        return pd.DataFrame()
    b = base[(~base["exterior"]) & base[cols].notna().all(axis=1) & (base["validos_pres"] > 0)]
    w = np.sqrt(b["validos_pres"].to_numpy(float))
    A = b[cols].to_numpy(float) * w[:, None]
    y = b["renan_pct"].to_numpy(float) * w
    coef = lsq_linear(A, y, bounds=(0, 1)).x
    votos_ref = (b[cols].to_numpy(float) * b["ant_validos"].to_numpy(float)[:, None]).sum(axis=0)
    implicitos = coef * votos_ref
    nomes = {f"ant_{k}_pct": v for k, v in (cfg.referencia_2022 or {}).items()}
    nomes["ant_outros_pct"] = "Outros/demais"
    out = pd.DataFrame({"grupo_referencia": [nomes.get(c, c) for c in cols], "taxa_migracao_estimada": coef,
                        "votos_implicitos": implicitos})
    out["pct_dos_votos_do_candidato"] = 100 * out["votos_implicitos"] / max(out["votos_implicitos"].sum(), 1)
    return out.sort_values("pct_dos_votos_do_candidato", ascending=False).reset_index(drop=True)


def correlacao_presidenciaveis(base: pd.DataFrame, nomes_pres: dict, top: int = 8) -> pd.DataFrame:
    b = base[(~base["exterior"]) & (base["validos_pres"] > 0)]
    cols = [c for c in b.columns if c.startswith("pres_") and c.endswith("_pct")]
    votos = {c: (b[c] * b["validos_pres"]).sum() for c in cols}
    cols = sorted(cols, key=lambda c: -votos[c])[:top]
    w = b["validos_pres"]
    m = pd.DataFrame(index=[nomes_pres.get(int(c.split("_")[1]), c) for c in cols],
                     columns=[nomes_pres.get(int(c.split("_")[1]), c) for c in cols], dtype=float)
    for i, ci in enumerate(cols):
        for j, cj in enumerate(cols):
            m.iat[i, j] = corr_ponderada(b[ci], b[cj], w)
    return m.reset_index().rename(columns={"index": "candidato"})


# --------------------------------------------------------------------------- fatos discrepantes

def fatos(cfg: Config, base: pd.DataFrame, r: dict) -> pd.DataFrame:
    """Gera a lista de fatos discrepantes/destaques em linguagem natural a partir dos resultados."""
    nome = cfg.presidente_nome
    f: list[tuple[str, str]] = []
    b = base[~base["exterior"]]
    fmt, pc = n0, lambda v: n2(v) + "%"  # noqa: E731

    nac = 100 * base["renan_votos"].sum() / base["validos_pres"].sum()
    top = r["top_pct"]
    if len(top):
        x = top.iloc[0]
        f.append(("Maior %", f"Maior % entre municípios com ≥ {fmt(cfg.min_eleitores_ranking)} eleitores: "
                  f"{x.nm_municipio} ({x.sg_uf}) com {pc(x.renan_pct100)} — {n1(x.renan_pct100 / nac)}× a média "
                  f"nacional ({pc(nac)})."))
    x = b.loc[b["renan_votos"].idxmax()]
    f.append(("Maior votação", f"Maior votação absoluta: {x.nm_municipio} ({x.sg_uf}) com {fmt(x.renan_votos)} votos "
              f"({pc(100 * x.renan_pct)}), {n1(100 * x.renan_votos / base['renan_votos'].sum())}% de todos os votos de {nome}."))
    for pos, rot in ((1, "1º"), (2, "2º")):
        s = b[b["renan_pos"] == pos]
        if len(s):
            ex = ", ".join(f"{m} ({u})" for m, u in s.nlargest(5, "aptos")[["nm_municipio", "sg_uf"]].itertuples(index=False))
            f.append(("Pódio", f"{nome} terminou em {rot} lugar em {len(s)} município(s). Maiores: {ex}."))
    z = b[b["renan_votos"] == 0]
    if len(z):
        x = z.loc[z["aptos"].idxmax()]
        f.append(("Sem votos", f"{len(z)} município(s) sem nenhum voto para {nome}; o maior é {x.nm_municipio} "
                  f"({x.sg_uf}) com {fmt(x.aptos)} eleitores."))
    d = r["distorcao_positiva"]
    if len(d):
        x = d.iloc[0]
        f.append(("Distorção", f"Maior distorção positiva frente à própria UF: {x.nm_municipio} ({x.sg_uf}) — "
                  f"{pc(x.renan_pct100)} contra {pc(x.pct_uf100)} na UF (z robusto = {n1(x.z_robusto)})."))
    d = r["distorcao_negativa"]
    if len(d):
        x = d.iloc[0]
        f.append(("Distorção", f"Maior distorção negativa (≥ 20 mil eleitores): {x.nm_municipio} ({x.sg_uf}) — "
                  f"{pc(x.renan_pct100)} contra {pc(x.pct_uf100)} na UF."))
    u = r["por_uf"][r["por_uf"]["sg_uf"] != "ZZ"]
    if len(u):
        a, z_ = u.iloc[0], u.iloc[-1]
        f.append(("UF", f"Melhor UF: {a.sg_uf} ({pc(a.renan_pct)}); pior UF: {z_.sg_uf} ({pc(z_.renan_pct)}). "
                  f"Amplitude de {n1(a.renan_pct / max(z_.renan_pct, 1e-9))}×."))
    c = r["capitais"]
    if len(c):
        a, z_ = c.iloc[0], c.iloc[-1]
        f.append(("Capitais", f"Melhor capital: {a.nm_municipio} ({pc(a.renan_pct)}); pior: {z_.nm_municipio} "
                  f"({pc(z_.renan_pct)}). Em {int((c['capital_vs_uf'] > 1).sum())} de {len(c)} capitais o "
                  f"desempenho foi superior ao da própria UF."))
    dm = r["df_maior_que_pres"]
    f.append(("Deputados > presidente", f"Em {len(dm)} município(s) a chapa de Dep. Federal teve mais votos que "
              f"{nome}; em {len(r['de_maior_que_pres'])} a de Dep. Estadual/Distrital."))
    if len(dm):
        x = dm.iloc[0]
        f.append(("Deputados > presidente", f"Caso mais extremo: {x.nm_municipio} ({x.sg_uf}) — Dep. Federal "
                  f"{fmt(x.df_total)} votos vs. {fmt(x.renan_votos)} do presidente ({n1(x.razao_df)}×), puxado por "
                  f"{x.top_df_nome}."))
    pl = r["candidatos_puxadores_locais"]
    if len(pl):
        x = pl.iloc[0]
        f.append(("Puxador local", f"{x.nm_urna} ({x.cargo}, {x.sg_uf}) superou sozinho {nome} em "
                  f"{x.municipios_acima_do_presidente} município(s)."))
    gc = r["guarda_chuva_partidos"]
    if len(gc) and gc["destaque"].any():
        meu = gc[gc["destaque"]].iloc[0]
        ordem = gc.sort_values("razao_df", ascending=False).reset_index(drop=True)
        pos = int(ordem.index[ordem["destaque"]][0]) + 1
        f.append(("Guarda-chuva", f"Cada voto em {nome} rendeu {n2(meu.razao_df)} voto(s) para a chapa de Dep. Federal "
                  f"({pos}º de {len(gc)} presidenciáveis nessa razão); correlação município a município de "
                  f"{n2(meu.corr_mun_pres_df)}."))
    q = r["quociente"]
    qd = q[(q["cargo"] == "Dep. Federal") & (q["eleitos"] == 0)].sort_values("faltaram_para_qe")
    for _, x in qd[qd["faltaram_para_qe"] == 0].iterrows():
        f.append(("Quociente", f"{x.sg_uf}: a chapa atingiu {pc(x.pct_do_qe)} do QE e não elegeu Dep. Federal — o mais "
                  f"votado ({x.mais_votado}) teve {pc(x.mais_votado_pct_qe)} do QE (mínimo de 10% para ocupar a vaga)."))
    qd = qd[qd["faltaram_para_qe"] > 0]
    if len(qd):
        x = qd.iloc[0]
        f.append(("Quociente", f"Mais perto de eleger Dep. Federal sem conseguir: {x.sg_uf} — {pc(x.pct_do_qe)} do QE; "
                  f"faltaram {fmt(x.faltaram_para_qe)} votos. Bastaria converter {pc(x.conversao_necessaria_pct)} dos "
                  f"votos de {nome} na UF (obtido: {pc(x.conversao_obtida_pct)})."))
    if "acertos_absolutos" in r and len(r["acertos_absolutos"]):
        a, e = r["acertos_absolutos"].iloc[0], r["erros_absolutos"].iloc[0]
        f.append(("Acerto", f"Maior ganho sobre o esperado pelo perfil: {a.nm_municipio} ({a.sg_uf}) com "
                  f"{fmt(a.votos_acima_esperado)} votos acima do previsto ({pc(a.renan_pct)} vs. {pc(a.pct_esperado)})."))
        f.append(("Erro", f"Maior perda frente ao esperado: {e.nm_municipio} ({e.sg_uf}) com "
                  f"{fmt(-e.votos_acima_esperado)} votos abaixo do previsto ({pc(e.renan_pct)} vs. {pc(e.pct_esperado)})."))
    ex = r.get("exterior")
    if ex is not None and len(ex):
        tot = ex["renan_votos"].sum()
        pct_ex = 100 * tot / ex["validos_pres"].sum()
        f.append(("Exterior", f"No exterior: {fmt(tot)} votos ({pc(pct_ex)}), {n1(pct_ex / nac)}× o % nacional. "
                  f"Melhor cidade: {ex.iloc[0].nm_municipio} ({fmt(ex.iloc[0].renan_votos)} votos)."))
    za = r.get("zonas_amplitude")
    if za is not None and len(za):
        x = za.iloc[0]
        f.append(("Zonas", f"Maior desigualdade interna: {x.nm_municipio} ({x.sg_uf}) — de {pc(x.pct_min)} a "
                  f"{pc(x.pct_max)} entre as {x.zonas} zonas eleitorais."))
    return pd.DataFrame(f, columns=["tema", "fato"])


# =========================================================================== orquestração

def analisar(cfg: Config, t: dict) -> dict[str, pd.DataFrame]:
    pres = t["cand_mun"][t["cand_mun"]["cd_cargo"] == PRESIDENTE]
    if pres.empty or pres["votos"].sum() == 0:
        cargos = t["cand_mun"]["cd_cargo"].value_counts().to_dict()
        raise SystemExit(
            "Nenhum voto para Presidente nos dados processados (votos por cargo em cand_mun: "
            f"{cargos}). Rode `python -m missao diagnosticar` e envie a saída.")
    base, nomes_pres = montar_base(cfg, t)
    r: dict[str, pd.DataFrame] = {}
    r["resumo"] = resumo_geral(cfg, t, base, nomes_pres)
    r["presidenciaveis"] = ranking_presidente(cfg, base, nomes_pres)
    r["por_uf"] = por_uf(cfg, base)
    r["por_regiao"] = por_grupo(base[~base["exterior"]], "regiao")
    r["por_porte"] = por_grupo(base[~base["exterior"]], "faixa_eleitorado")
    r["capital_interior"] = por_grupo(base[~base["exterior"]].assign(
        tipo=np.where(base.loc[~base["exterior"], "capital"], "Capital", "Interior")), "tipo")
    r["capitais"] = capitais(base[~base["exterior"]])
    r["concentracao"] = concentracao(base)
    r.update(rankings(cfg, base))
    suav = suavizar_eb(base)
    r.update(distorcoes(cfg, base, suav))
    try:
        r.update(modelo_esperado(cfg, base))
    except Exception as erro:  # noqa: BLE001 — modelo é opcional; registra o motivo
        r["modelo_meta"] = pd.DataFrame([("erro", str(erro))], columns=["item", "valor"])
    r["quociente"] = quociente(cfg, t, base)
    r["guarda_chuva_partidos"] = guarda_chuva_partidos(cfg, t, base, nomes_pres)
    r["guarda_chuva_quintis"] = guarda_chuva_quintis(base)
    r["guarda_chuva_resumo"] = guarda_chuva_resumo(base)
    r.update(deputados_maior_que_presidente(cfg, t, base))
    r["candidatos_partido"] = candidatos_partido(cfg, t, base, r["quociente"])
    r.update(zonas(cfg, t, base))
    r["exterior"] = exterior(base)
    r["origem_votos"] = origem_votos(cfg, base)
    r["correlacao_presidenciaveis"] = correlacao_presidenciaveis(base, nomes_pres)
    r["fatos"] = fatos(cfg, base, r)

    # base municipal completa (para planilha e mapas)
    mb = base.merge(suav, on=["sg_uf", "cd_municipio"], how="left")
    if "_residuos" in r:
        mb = mb.merge(r.pop("_residuos"), on=["sg_uf", "cd_municipio"], how="left")
    r["base_municipal"] = mb
    return r
