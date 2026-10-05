"""Diagnóstico dos arquivos brutos e processados: o que veio do TSE e o que o pipeline extraiu.

Uso: python -m missao diagnosticar   (cole a saída inteira ao pedir ajuda)
"""
from __future__ import annotations

import json
import zipfile
from collections import Counter
from pathlib import Path

import pandas as pd

from .carregar import PADRAO_ARQ, _membros_csv, _norm_col, ler_json, zip_tem_dados
from .config import Config

CHAVES = ["ANO_ELEICAO", "NR_TURNO", "CD_TIPO_ELEICAO", "CD_CARGO"]


def _zip(caminho: Path, contar: bool) -> None:
    vazio = "" if zip_tem_dados(caminho) else "  ← SEM DADOS (só cabeçalhos)"
    print(f"\n== {caminho.name} ({caminho.stat().st_size / 1e6:,.1f} MB){vazio}")
    with zipfile.ZipFile(caminho) as zf:
        infos = [i for i in zf.infolist() if i.filename.lower().endswith(".csv")]
        escolhidos, br = _membros_csv(zf)
        especiais = [Path(i.filename).name for i in infos if i.filename.upper().endswith(("_BR.CSV", "_BRASIL.CSV"))]
        print(f"   {len(infos)} CSVs ({sum(i.file_size for i in infos) / 1e6:,.0f} MB descompactados); "
              f"nacionais: {especiais or 'nenhum'}; lidos pelo pipeline: {len(escolhidos)}")
        with zf.open(infos[0].filename) as f:
            cab = [_norm_col(c) for c in f.readline().decode("latin-1").split(";")]
        print(f"   colunas: {cab}")
        if not contar:
            return
        grupos: dict[str, Counter] = {}
        ufs: set = set()
        cols: list[str] = []
        for membro in escolhidos:
            nome = Path(membro).name.upper()
            grupo = "_BR" if nome.endswith("_BR.CSV") else "_BRASIL" if nome.endswith("_BRASIL.CSV") else "por UF"
            cont = grupos.setdefault(grupo, Counter())
            with zf.open(membro) as f:
                for bloco in pd.read_csv(f, sep=";", encoding="latin-1", dtype=str,
                                         usecols=lambda c: _norm_col(c) in CHAVES + ["SG_UF"], chunksize=500_000):
                    bloco.columns = [_norm_col(c) for c in bloco.columns]
                    cols = [c for c in CHAVES if c in bloco]
                    cont.update(map(tuple, bloco[cols].fillna("∅").to_numpy()))
                    if "SG_UF" in bloco:
                        ufs.update(bloco["SG_UF"].dropna().unique())
        for grupo, cont in grupos.items():
            print(f"   linhas em {grupo} por ({', '.join(cols)}): {dict(sorted(cont.items()))}")
        print(f"   SG_UF encontrados: {sorted(ufs)}")


def diagnosticar(cfg: Config) -> None:
    cdn = cfg.dir_brutos / "cdn"
    print(f"[diagnóstico] pasta de dados: {cfg.dir_dados.resolve()}")
    zips = sorted(cdn.glob("*.zip")) if cdn.exists() else []
    print(f"[diagnóstico] zips baixados do Portal de Dados Abertos: {[z.name for z in zips] or 'nenhum'}")
    for z in zips:
        try:
            _zip(z, contar=z.name.startswith(("votacao_candidato_munzona", "detalhe_votacao_munzona")))
        except Exception as erro:  # noqa: BLE001
            print(f"   ERRO ao ler: {type(erro).__name__}: {erro}")

    api = cfg.dir_brutos / "api"
    if api.exists():
        arquivos = [a for a in api.glob("*/*/*") if PADRAO_ARQ.search(a.name)]
        por = Counter((a.parent.parent.name, a.name.split("-c")[1][:4]) for a in arquivos)
        print(f"\n[diagnóstico] API de divulgação: {len(arquivos)} arquivos; por (eleição, cargo): {dict(por)}")
        desc = api / "eleicoes_descobertas.json"
        if desc.exists():
            print(f"   eleições descobertas: {desc.read_text(encoding='utf-8', errors='replace')[:1500]}")
        for cargo in ("0001", "0006"):
            ex = next((a for a in arquivos if f"-c{cargo}-" in a.name), None)
            if ex:
                print(f"   exemplo cargo {cargo} ({ex.name}): {json.dumps(ler_json(ex), ensure_ascii=False)[:1500]}")

    proc = cfg.dir_processados
    if proc.exists():
        print("\n[diagnóstico] tabelas processadas:")
        for p in sorted(proc.glob("*.parquet")):
            df = pd.read_parquet(p)
            extra = ""
            if "cd_cargo" in df:
                extra = f" | linhas por cargo: {df['cd_cargo'].value_counts().sort_index().to_dict()}"
            if p.stem == "municipios":
                extra = f" | UFs: {df['sg_uf'].value_counts().to_dict()}"
            print(f"   {p.stem}: {len(df):,} linhas{extra}")
