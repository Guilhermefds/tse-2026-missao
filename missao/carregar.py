"""Leitura dos arquivos brutos do TSE e normalização em parquet.

Saídas (em dados/processados/):
    cand_zona.parquet        votos por candidato x município x zona (Presidente + candidatos do partido)
    cand_mun.parquet         votos por candidato x município (Pres/Gov/Sen: todos; Deputados: só o partido)
    cand_uf.parquet          votos totais por candidato x UF (todos os cargos e partidos) + situação
    partido_mun.parquet      votos nominais/legenda por partido x município x cargo (todos os partidos)
    detalhe_mun.parquet      aptos, comparecimento, abstenção, brancos, nulos, válidos por município x cargo
    detalhe_zona.parquet     idem por zona (só Presidente)
    candidatos.parquet       cadastro (consulta_cand) — perfil dos candidatos
    perfil_mun.parquet       perfil do eleitorado agregado por município (% mulheres, jovens, ensino superior...)
    comparacao_pres_mun.parquet  votos para Presidente no ano de comparação (ex.: 2022) por município
    municipios.parquet       dimensão de municípios (UF, região, capital, eleitorado)
"""
from __future__ import annotations

import json
import re
import unicodedata
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from .config import CAPITAIS, DEP_DISTRITAL, DEP_ESTADUAL, DEP_FEDERAL, PRESIDENTE, REGIAO, Config

NULOS = ["#NULO#", "#NULO", "#NE#", "#NE"]


def sem_acento(texto: str) -> str:
    if not isinstance(texto, str):
        return texto
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().upper().strip()


def _primeira(df: pd.DataFrame, *nomes: str, padrao=0) -> pd.Series:
    """Primeira coluna existente entre `nomes` (os nomes mudam entre anos no TSE)."""
    for nome in nomes:
        if nome in df.columns:
            return df[nome]
    return pd.Series(padrao, index=df.index)


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0).astype("int64")


def _membros_csv(zf: zipfile.ZipFile) -> tuple[list[str], str | None]:
    """Escolhe quais CSVs ler dentro do zip. Retorna (membros, membro_BR)."""
    csvs = [m for m in zf.namelist() if m.lower().endswith(".csv")]
    brasil = [m for m in csvs if m.upper().endswith("_BRASIL.CSV")]
    if brasil:
        return brasil, None
    br = next((m for m in csvs if m.upper().endswith("_BR.CSV")), None)
    return csvs, br


def ler_zip_tse(caminho: Path, colunas: set[str], filtro=None, chunksize: int = 400_000,
                apenas_br: bool = False) -> pd.DataFrame:
    """Lê os CSVs (latin-1, ';') de um zip do TSE mantendo só `colunas` e aplicando `filtro(df)->df`.

    Quando há arquivo *_BR.csv (abrangência nacional, ex.: Presidente) junto com os arquivos por UF,
    as linhas de Presidente vêm só do _BR para não haver dupla contagem.
    """
    partes = []
    with zipfile.ZipFile(caminho) as zf:
        membros, membro_br = _membros_csv(zf)
        if apenas_br and membro_br:
            membros = [membro_br]
        for membro in membros:
            with zf.open(membro) as f:
                leitor = pd.read_csv(f, sep=";", encoding="latin-1", dtype=str, quotechar='"',
                                     usecols=lambda c: c in colunas, chunksize=chunksize,
                                     na_values=NULOS, keep_default_na=False)
                for bloco in leitor:
                    if filtro is not None:
                        bloco = filtro(bloco)
                    if len(bloco):
                        bloco = bloco.copy()
                        bloco["_br"] = membro == membro_br
                        partes.append(bloco)
    if not partes:
        return pd.DataFrame(columns=sorted(colunas) + ["_br"])
    df = pd.concat(partes, ignore_index=True)
    if {"SG_UF", "CD_MUNICIPIO"} <= set(df.columns) and (df["SG_UF"] == "BR").any():
        # arquivos de abrangência nacional podem trazer SG_UF="BR"; recupera a UF pelo código do município
        nao_br = df["SG_UF"] != "BR"
        mapa = df.loc[nao_br].drop_duplicates("CD_MUNICIPIO").set_index("CD_MUNICIPIO")["SG_UF"]
        df.loc[~nao_br, "SG_UF"] = df.loc[~nao_br, "CD_MUNICIPIO"].map(mapa).fillna("BR")
    if membro_br is not None and not apenas_br and "CD_CARGO" in df.columns:
        tem_pres_br = (df["_br"] & (df["CD_CARGO"] == str(PRESIDENTE))).any()
        if tem_pres_br:
            df = df[~((df["CD_CARGO"] == str(PRESIDENTE)) & ~df["_br"])]
    return df.drop(columns="_br")


def _filtro_eleicao(cfg: Config, ano: int | None = None, cargos: set[int] | None = None):
    ano = ano or cfg.ano

    def f(df: pd.DataFrame) -> pd.DataFrame:
        m = pd.Series(True, index=df.index)
        if "ANO_ELEICAO" in df:
            m &= df["ANO_ELEICAO"] == str(ano)
        if "NR_TURNO" in df:
            m &= df["NR_TURNO"] == str(cfg.turno)
        if "CD_TIPO_ELEICAO" in df:  # 2 = eleição ordinária
            m &= df["CD_TIPO_ELEICAO"].isin(["2", None]) | df["CD_TIPO_ELEICAO"].isna()
        if cargos and "CD_CARGO" in df:
            m &= df["CD_CARGO"].isin({str(c) for c in cargos})
        return df[m]
    return f


# --------------------------------------------------------------------------- votação por candidato

COLS_CAND = {
    "ANO_ELEICAO", "NR_TURNO", "CD_TIPO_ELEICAO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA",
    "CD_CARGO", "SQ_CANDIDATO", "NR_CANDIDATO", "NM_URNA_CANDIDATO", "NM_CANDIDATO", "NR_PARTIDO",
    "SG_PARTIDO", "NR_FEDERACAO", "SG_FEDERACAO", "DS_SIT_TOT_TURNO", "QT_VOTOS_NOMINAIS",
    "QT_VOTOS_NOMINAIS_VALIDOS", "DS_SITUACAO_CANDIDATURA", "DS_DETALHE_SITUACAO_CAND",
}


def normalizar_cand(df: pd.DataFrame) -> pd.DataFrame:
    votos_validos = _primeira(df, "QT_VOTOS_NOMINAIS_VALIDOS", "QT_VOTOS_NOMINAIS")
    out = pd.DataFrame({
        "cd_cargo": _num(df["CD_CARGO"]).astype("int16"),
        "sg_uf": df["SG_UF"].astype(str),
        "cd_municipio": _num(df["CD_MUNICIPIO"]).astype("int32"),
        "nm_municipio": df["NM_MUNICIPIO"],
        "nr_zona": _num(_primeira(df, "NR_ZONA")).astype("int32"),
        "sq_candidato": df["SQ_CANDIDATO"].astype(str),
        "nr_candidato": _num(df["NR_CANDIDATO"]).astype("int32"),
        "nm_urna": _primeira(df, "NM_URNA_CANDIDATO", "NM_CANDIDATO", padrao=""),
        "nr_partido": _num(df["NR_PARTIDO"]).astype("int16"),
        "sg_partido": df["SG_PARTIDO"],
        "sg_federacao": _primeira(df, "SG_FEDERACAO", padrao=None),
        "situacao": _primeira(df, "DS_SIT_TOT_TURNO", padrao=""),
        "votos": _num(votos_validos),
        "votos_brutos": _num(_primeira(df, "QT_VOTOS_NOMINAIS", "QT_VOTOS_NOMINAIS_VALIDOS")),
    })
    return out


def processar_votacao_candidato(cfg: Config, caminho: Path) -> dict[str, pd.DataFrame]:
    bruto = ler_zip_tse(caminho, COLS_CAND, _filtro_eleicao(cfg))
    df = normalizar_cand(bruto)
    chaves = ["cd_cargo", "sg_uf", "sq_candidato", "nr_candidato", "nm_urna", "nr_partido",
              "sg_partido", "sg_federacao", "situacao"]
    df["sg_federacao"] = df["sg_federacao"].fillna("")
    df["situacao"] = df["situacao"].fillna("")

    cand_uf = df.groupby(chaves, as_index=False, dropna=False)[["votos", "votos_brutos"]].sum()

    do_partido = df["nr_partido"] == cfg.partido_numero
    majoritarios = df["cd_cargo"].isin([1, 3, 5])
    mun = df[majoritarios | do_partido]
    cand_mun = (mun.groupby(chaves + ["cd_municipio", "nm_municipio"], as_index=False, dropna=False)
                [["votos", "votos_brutos"]].sum())

    zona = df[(df["cd_cargo"] == PRESIDENTE) | do_partido]
    cand_zona = (zona.groupby(chaves + ["cd_municipio", "nm_municipio", "nr_zona"], as_index=False,
                              dropna=False)[["votos"]].sum())
    return {"cand_uf": cand_uf, "cand_mun": cand_mun, "cand_zona": cand_zona}


# --------------------------------------------------------------------------- votação por partido

COLS_PART = {
    "ANO_ELEICAO", "NR_TURNO", "CD_TIPO_ELEICAO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA",
    "CD_CARGO", "NR_PARTIDO", "SG_PARTIDO", "NR_FEDERACAO", "SG_FEDERACAO", "QT_VOTOS_NOMINAIS",
    "QT_VOTOS_NOMINAIS_VALIDOS", "QT_VOTOS_LEGENDA", "QT_VOTOS_LEGENDA_VALIDOS",
    "QT_TOTAL_VOTOS_LEG_VALIDOS", "QT_VOTOS_NOMINAIS_CONVR_LEGENDA",
}


def processar_votacao_partido(cfg: Config, caminho: Path) -> pd.DataFrame:
    df = ler_zip_tse(caminho, COLS_PART, _filtro_eleicao(cfg))
    leg_puro = _num(_primeira(df, "QT_VOTOS_LEGENDA_VALIDOS", "QT_VOTOS_LEGENDA"))
    leg_total = _num(_primeira(df, "QT_TOTAL_VOTOS_LEG_VALIDOS", "QT_VOTOS_LEGENDA_VALIDOS", "QT_VOTOS_LEGENDA"))
    out = pd.DataFrame({
        "cd_cargo": _num(df["CD_CARGO"]).astype("int16"),
        "sg_uf": df["SG_UF"].astype(str),
        "cd_municipio": _num(df["CD_MUNICIPIO"]).astype("int32"),
        "nm_municipio": df["NM_MUNICIPIO"],
        "nr_partido": _num(df["NR_PARTIDO"]).astype("int16"),
        "sg_partido": df["SG_PARTIDO"],
        "sg_federacao": _primeira(df, "SG_FEDERACAO", padrao="").fillna(""),
        "votos_nominais": _num(_primeira(df, "QT_VOTOS_NOMINAIS_VALIDOS", "QT_VOTOS_NOMINAIS")),
        "votos_legenda": leg_puro,
        "votos_legenda_total": leg_total,
    })
    out["votos_total"] = out["votos_nominais"] + out["votos_legenda_total"]
    chaves = ["cd_cargo", "sg_uf", "cd_municipio", "nm_municipio", "nr_partido", "sg_partido", "sg_federacao"]
    return out.groupby(chaves, as_index=False)[["votos_nominais", "votos_legenda", "votos_legenda_total",
                                                "votos_total"]].sum()


# --------------------------------------------------------------------------- detalhe (comparecimento etc.)

COLS_DET = {
    "ANO_ELEICAO", "NR_TURNO", "CD_TIPO_ELEICAO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA",
    "CD_CARGO", "QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES", "QT_VOTOS_BRANCOS", "QT_TOTAL_VOTOS_NULOS",
    "QT_VOTOS_NULOS", "QT_VOTOS_NOMINAIS", "QT_VOTOS_NOMINAIS_VALIDOS", "QT_VOTOS_LEGENDA",
    "QT_VOTOS_LEG_VALIDOS", "QT_TOTAL_VOTOS_LEG_VALIDOS", "QT_TOTAL_VOTOS_VALIDOS",
}


def processar_detalhe(cfg: Config, caminho: Path) -> dict[str, pd.DataFrame]:
    df = ler_zip_tse(caminho, COLS_DET, _filtro_eleicao(cfg))
    nominais = _num(_primeira(df, "QT_VOTOS_NOMINAIS_VALIDOS", "QT_VOTOS_NOMINAIS"))
    legenda = _num(_primeira(df, "QT_TOTAL_VOTOS_LEG_VALIDOS", "QT_VOTOS_LEG_VALIDOS", "QT_VOTOS_LEGENDA"))
    validos = _num(_primeira(df, "QT_TOTAL_VOTOS_VALIDOS")) if "QT_TOTAL_VOTOS_VALIDOS" in df else nominais + legenda
    out = pd.DataFrame({
        "cd_cargo": _num(df["CD_CARGO"]).astype("int16"),
        "sg_uf": df["SG_UF"].astype(str),
        "cd_municipio": _num(df["CD_MUNICIPIO"]).astype("int32"),
        "nm_municipio": df["NM_MUNICIPIO"],
        "nr_zona": _num(_primeira(df, "NR_ZONA")).astype("int32"),
        "aptos": _num(df["QT_APTOS"]),
        "comparecimento": _num(df["QT_COMPARECIMENTO"]),
        "abstencoes": _num(df["QT_ABSTENCOES"]),
        "brancos": _num(_primeira(df, "QT_VOTOS_BRANCOS")),
        "nulos": _num(_primeira(df, "QT_TOTAL_VOTOS_NULOS", "QT_VOTOS_NULOS")),
        "validos": validos,
    })
    medidas = ["aptos", "comparecimento", "abstencoes", "brancos", "nulos", "validos"]
    mun = out.groupby(["cd_cargo", "sg_uf", "cd_municipio", "nm_municipio"], as_index=False)[medidas].sum()
    zona = (out[out["cd_cargo"] == PRESIDENTE]
            .groupby(["cd_cargo", "sg_uf", "cd_municipio", "nm_municipio", "nr_zona"], as_index=False)[medidas].sum())
    return {"detalhe_mun": mun, "detalhe_zona": zona}


# --------------------------------------------------------------------------- cadastro de candidatos

COLS_CONSULTA = {
    "ANO_ELEICAO", "NR_TURNO", "CD_TIPO_ELEICAO", "SG_UF", "CD_CARGO", "SQ_CANDIDATO", "NR_CANDIDATO",
    "NM_CANDIDATO", "NM_URNA_CANDIDATO", "NR_PARTIDO", "SG_PARTIDO", "SG_FEDERACAO", "DS_GENERO",
    "DS_GRAU_INSTRUCAO", "DS_OCUPACAO", "NR_IDADE_DATA_POSSE", "DS_COR_RACA", "DS_SIT_TOT_TURNO",
    "DS_SITUACAO_CANDIDATURA", "DS_DETALHE_SITUACAO_CAND", "ST_REELEICAO", "NM_MUNICIPIO_NASCIMENTO",
    "SG_UF_NASCIMENTO",
}


def processar_consulta_cand(cfg: Config, caminho: Path) -> pd.DataFrame:
    df = ler_zip_tse(caminho, COLS_CONSULTA, _filtro_eleicao(cfg))
    ren = {c: c.lower() for c in df.columns}
    df = df.rename(columns=ren)
    for c in ["cd_cargo", "nr_candidato", "nr_partido", "nr_idade_data_posse"]:
        if c in df:
            df[c] = _num(df[c])
    df["sq_candidato"] = df["sq_candidato"].astype(str)
    return df.drop_duplicates("sq_candidato")


# --------------------------------------------------------------------------- perfil do eleitorado

COLS_PERFIL = {"SG_UF", "CD_MUNICIPIO", "DS_GENERO", "DS_FAIXA_ETARIA", "DS_GRAU_ESCOLARIDADE",
               "QT_ELEITORES_PERFIL", "ANO_ELEICAO", "DT_GERACAO"}


def processar_perfil(cfg: Config, caminho: Path) -> pd.DataFrame:
    df = ler_zip_tse(caminho, COLS_PERFIL)
    qt = _num(df["QT_ELEITORES_PERFIL"])
    idade = pd.to_numeric(df["DS_FAIXA_ETARIA"].str.extract(r"(\d+)")[0], errors="coerce")
    esc = df["DS_GRAU_ESCOLARIDADE"].map(sem_acento).fillna("")
    gen = df["DS_GENERO"].map(sem_acento).fillna("")
    base = pd.DataFrame({
        "sg_uf": df["SG_UF"], "cd_municipio": _num(df["CD_MUNICIPIO"]).astype("int32"), "qt": qt,
        "q_fem": qt * (gen == "FEMININO"),
        "q_16_24": qt * (idade < 25), "q_25_34": qt * idade.between(25, 34),
        "q_35_59": qt * idade.between(35, 59), "q_60m": qt * (idade >= 60),
        "q_superior": qt * (esc == "SUPERIOR COMPLETO"),
        "q_sup_inc": qt * (esc == "SUPERIOR INCOMPLETO"),
        "q_medio": qt * (esc == "ENSINO MEDIO COMPLETO"),
        "q_fund_inc": qt * esc.isin(["ANALFABETO", "LE E ESCREVE", "ENSINO FUNDAMENTAL INCOMPLETO"]),
    })
    g = base.groupby(["sg_uf", "cd_municipio"], as_index=False).sum(numeric_only=True)
    out = g[["sg_uf", "cd_municipio"]].copy()
    out["eleitorado_perfil"] = g["qt"]
    for c in [c for c in g.columns if c.startswith("q_")]:
        out["pct_" + c[2:]] = g[c] / g["qt"].where(g["qt"] > 0)
    return out


# --------------------------------------------------------------------------- comparação (ex.: 2022)

def processar_comparacao(cfg: Config, caminho: Path) -> pd.DataFrame:
    filtro = _filtro_eleicao(cfg, ano=cfg.ano_comparacao, cargos={PRESIDENTE})
    bruto = ler_zip_tse(caminho, COLS_CAND, filtro, apenas_br=True)
    if bruto.empty:
        bruto = ler_zip_tse(caminho, COLS_CAND, filtro)
    df = normalizar_cand(bruto)
    return df.groupby(["sg_uf", "cd_municipio", "nr_candidato", "nm_urna"], as_index=False)["votos"].sum()


# --------------------------------------------------------------------------- API de divulgação (fallback)

def _iter_dicts(no, pais=()):
    if isinstance(no, dict):
        yield no, pais
        for v in no.values():
            yield from _iter_dicts(v, pais + (no,))
    elif isinstance(no, list):
        for v in no:
            yield from _iter_dicts(v, pais)


def _int(v) -> int:
    try:
        return int(str(v).replace(".", "").strip() or 0)
    except ValueError:
        return 0


PADRAO_ARQ = re.compile(r"(?P<uf>[a-z]{2})(?P<mun>\d+)-c(?P<cargo>\d{4})-e(?P<ele>\d{6})-r\.json$")


def processar_api(cfg: Config, base: Path) -> dict[str, pd.DataFrame]:
    """Converte os JSON 'dados-simplificados' por município no mesmo esquema do CDN.

    O formato da divulgação muda entre ciclos; o parser procura, de forma tolerante, listas de
    candidatos (dicts com 'n' e 'vap') e os totais do município (chaves 'e'/'c'/'a'/'vb'/'tvn'/'vv').
    Valide com `python -m missao conferir` quando rodar com dados reais.
    """
    linhas_cand, linhas_det, linhas_leg = [], [], []
    nomes_mun = {}
    for cfg_mun in base.glob("*/mun-e*-cm.json"):
        for uf in json.loads(cfg_mun.read_text()).get("abr", []):
            for mu in uf.get("mu", []):
                nomes_mun[(uf["cd"].upper(), int(mu["cd"]))] = mu.get("nm", "")
    for arq in base.glob("*/*/*-r.json"):
        m = PADRAO_ARQ.search(arq.name)
        if not m:
            continue
        uf, mun, cargo = m["uf"].upper(), int(m["mun"]), int(m["cargo"])
        dados = json.loads(arq.read_text())
        nm = nomes_mun.get((uf, mun), "")
        vistos = set()
        for d, pais in _iter_dicts(dados):
            if "vap" in d and "n" in d:
                n = _int(d["n"])
                if n in vistos:
                    continue
                vistos.add(n)
                par = next((p for p in reversed(pais) if "sg" in p), {})
                linhas_cand.append({
                    "cd_cargo": cargo, "sg_uf": uf, "cd_municipio": mun, "nm_municipio": nm,
                    "sq_candidato": str(d.get("sqcand", f"{uf}{cargo}{n}")), "nr_candidato": n,
                    "nm_urna": d.get("nm", ""), "nr_partido": int(str(n)[:2]),
                    "sg_partido": par.get("sg", ""), "sg_federacao": "",
                    "situacao": d.get("st", ""), "votos": _int(d["vap"]), "votos_brutos": _int(d["vap"]),
                })
            if "sg" in d and any(k in d for k in ("vl", "tvl", "vlg")):
                linhas_leg.append({"cd_cargo": cargo, "sg_uf": uf, "cd_municipio": mun,
                                   "nr_partido": _int(d.get("n", 0)),
                                   "votos_legenda": _int(d.get("vl", d.get("tvl", d.get("vlg", 0))))})
        linhas_det.append({
            "cd_cargo": cargo, "sg_uf": uf, "cd_municipio": mun, "nm_municipio": nm,
            "aptos": _int(dados.get("e", 0)), "comparecimento": _int(dados.get("c", 0)),
            "abstencoes": _int(dados.get("a", 0)), "brancos": _int(dados.get("vb", 0)),
            "nulos": _int(dados.get("tvn", dados.get("vn", 0))), "validos": _int(dados.get("vv", 0)),
        })
    cand_mun = pd.DataFrame(linhas_cand)
    det = pd.DataFrame(linhas_det)
    chaves = ["cd_cargo", "sg_uf", "sq_candidato", "nr_candidato", "nm_urna", "nr_partido", "sg_partido",
              "sg_federacao", "situacao"]
    cand_uf = cand_mun.groupby(chaves, as_index=False)[["votos", "votos_brutos"]].sum()
    part = (cand_mun.groupby(["cd_cargo", "sg_uf", "cd_municipio", "nm_municipio", "nr_partido", "sg_partido",
                              "sg_federacao"], as_index=False)["votos"].sum()
            .rename(columns={"votos": "votos_nominais"}))
    leg = pd.DataFrame(linhas_leg, columns=["cd_cargo", "sg_uf", "cd_municipio", "nr_partido", "votos_legenda"])
    part = part.merge(leg.groupby(["cd_cargo", "sg_uf", "cd_municipio", "nr_partido"], as_index=False).sum(),
                      how="left", on=["cd_cargo", "sg_uf", "cd_municipio", "nr_partido"])
    part["votos_legenda"] = part["votos_legenda"].fillna(0).astype("int64")
    part["votos_legenda_total"] = part["votos_legenda"]
    part["votos_total"] = part["votos_nominais"] + part["votos_legenda"]
    so_partido = cand_mun[cand_mun["cd_cargo"].isin([1, 3, 5]) | (cand_mun["nr_partido"] == cfg.partido_numero)]
    return {"cand_mun": so_partido, "cand_uf": cand_uf, "partido_mun": part, "detalhe_mun": det}


# --------------------------------------------------------------------------- dimensão de municípios

def montar_municipios(detalhe_mun: pd.DataFrame) -> pd.DataFrame:
    pres = detalhe_mun[detalhe_mun["cd_cargo"] == PRESIDENTE]
    base = pres if len(pres) else detalhe_mun.drop_duplicates(["sg_uf", "cd_municipio"])
    m = base[["sg_uf", "cd_municipio", "nm_municipio", "aptos", "comparecimento", "abstencoes"]].copy()
    m["regiao"] = m["sg_uf"].map(REGIAO).fillna("Exterior")
    m["exterior"] = m["sg_uf"] == "ZZ"
    nome = m["nm_municipio"].map(sem_acento)
    m["capital"] = [CAPITAIS.get(uf) == n for uf, n in zip(m["sg_uf"], nome)]
    return m.reset_index(drop=True)


def salvar(tabelas: dict[str, pd.DataFrame], destino: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    for nome, df in tabelas.items():
        df.to_parquet(destino / f"{nome}.parquet", index=False)
        print(f"[processar] {nome}: {len(df):,} linhas")


def processar(cfg: Config) -> dict[str, pd.DataFrame]:
    """Processa o que estiver disponível em dados/brutos (CDN tem prioridade sobre API)."""
    cdn = cfg.dir_brutos / "cdn"
    tabelas: dict[str, pd.DataFrame] = {}
    arq = lambda nome: cdn / f"{nome}.zip"  # noqa: E731

    if arq(f"votacao_candidato_munzona_{cfg.ano}").exists():
        tabelas.update(processar_votacao_candidato(cfg, arq(f"votacao_candidato_munzona_{cfg.ano}")))
        if arq(f"votacao_partido_munzona_{cfg.ano}").exists():
            tabelas["partido_mun"] = processar_votacao_partido(cfg, arq(f"votacao_partido_munzona_{cfg.ano}"))
        if arq(f"detalhe_votacao_munzona_{cfg.ano}").exists():
            tabelas.update(processar_detalhe(cfg, arq(f"detalhe_votacao_munzona_{cfg.ano}")))
    elif (cfg.dir_brutos / "api").exists():
        print("[processar] CDN indisponível — usando JSON da API de divulgação")
        tabelas.update(processar_api(cfg, cfg.dir_brutos / "api"))
    else:
        raise FileNotFoundError("Nenhum dado bruto encontrado. Rode `python -m missao baixar` primeiro.")

    if "partido_mun" not in tabelas:  # sem arquivo de partido: reconstrói só com votos nominais
        cm = tabelas["cand_mun"]
        tabelas["partido_mun"] = (cm.groupby(["cd_cargo", "sg_uf", "cd_municipio", "nm_municipio", "nr_partido",
                                              "sg_partido", "sg_federacao"], as_index=False)["votos"].sum()
                                  .rename(columns={"votos": "votos_nominais"})
                                  .assign(votos_legenda=0, votos_legenda_total=0))
        tabelas["partido_mun"]["votos_total"] = tabelas["partido_mun"]["votos_nominais"]

    if arq(f"consulta_cand_{cfg.ano}").exists():
        tabelas["candidatos"] = processar_consulta_cand(cfg, arq(f"consulta_cand_{cfg.ano}"))
    for nome in (f"perfil_eleitorado_{cfg.ano}", "perfil_eleitorado_ATUAL"):
        if arq(nome).exists():
            tabelas["perfil_mun"] = processar_perfil(cfg, arq(nome))
            break
    if arq(f"votacao_candidato_munzona_{cfg.ano_comparacao}").exists():
        tabelas["comparacao_pres_mun"] = processar_comparacao(
            cfg, arq(f"votacao_candidato_munzona_{cfg.ano_comparacao}"))

    tabelas["municipios"] = montar_municipios(tabelas["detalhe_mun"])
    salvar(tabelas, cfg.dir_processados)
    return tabelas


def carregar(cfg: Config) -> dict[str, pd.DataFrame]:
    return {p.stem: pd.read_parquet(p) for p in sorted(cfg.dir_processados.glob("*.parquet"))}
