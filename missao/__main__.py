"""CLI: python -m missao {baixar,processar,conferir,analisar,relatorio,diagnosticar,sondar,tudo} [--dados DIR] [--saida DIR] [--fonte cdn|api|auto]"""
from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

from .config import carregar_config


def conferir(cfg, t) -> None:
    """Checagens de sanidade dos dados processados (rode sempre com dados reais)."""
    cm, det, pm = t["cand_mun"], t["detalhe_mun"], t["partido_mun"]
    pres = cm[cm.cd_cargo == 1]
    print(f"[conferir] municípios: {t['municipios'].shape[0]:,} (exterior: {int(t['municipios'].exterior.sum())})")
    sem_uf = int((t["municipios"].sg_uf == "BR").sum())
    if sem_uf:
        print(f"[conferir] ATENÇÃO: {sem_uf} municípios com UF='BR' (UF não recuperada do arquivo nacional)")
    soma, val = int(pres.votos.sum()), int(det[det.cd_cargo == 1].validos.sum())
    print(f"[conferir] Presidente: soma candidatos {soma:,} × válidos do detalhe {val:,} "
          f"{'OK' if soma == val else 'DIFERENTE — verifique dupla contagem/fonte'}")
    print(pres.groupby(["nr_candidato", "nm_urna"]).votos.sum().sort_values(ascending=False).head(12).to_string())
    for cargo in (6, 7, 8):
        a, b = int(pm[pm.cd_cargo == cargo].votos_total.sum()), int(det[det.cd_cargo == cargo].validos.sum())
        print(f"[conferir] cargo {cargo}: partidos {a:,} × detalhe {b:,}")
    meus = t["cand_uf"][t["cand_uf"].nr_partido == cfg.partido_numero]
    print(f"[conferir] candidatos do partido {cfg.partido_numero} por cargo:")
    print(meus.groupby("cd_cargo").agg(candidatos=("sq_candidato", "nunique"), votos=("votos", "sum")).to_string())
    print(meus.situacao.value_counts().to_string())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="missao", description=__doc__)
    ap.add_argument("comando", choices=["baixar", "processar", "conferir", "analisar", "relatorio", "diagnosticar", "sondar", "tudo"])
    ap.add_argument("--dados", help="diretório de dados (padrão: dados/)")
    ap.add_argument("--saida", help="diretório de saída (padrão: saida/)")
    ap.add_argument("--fonte", default="auto", choices=["auto", "cdn", "api"],
                    help="auto = CDN de dados abertos; se o ano não estiver publicado, usa a API de divulgação")
    ap.add_argument("--eleicoes", nargs="*", help="códigos de eleição da API (ex.: 620 621); padrão: descobrir")
    ap.add_argument("--sintetico", action="store_true", help="marca o relatório como DADOS SINTÉTICOS")
    a = ap.parse_args(argv)

    extra = {}
    if a.dados:
        extra["dir_dados"] = a.dados
    if a.saida:
        extra["dir_saida"] = a.saida
    cfg = carregar_config(**extra)

    if a.comando == "relatorio":  # refaz modelo, destaques e saídas a partir de saida/analise_completa.xlsx
        from .relatorio import reprocessar_planilha
        reprocessar_planilha(cfg, sintetico=a.sintetico)
        return 0
    if a.comando == "sondar":
        from .baixar import sondar_api
        from .config import RAIZ
        sondar_api(cfg, RAIZ / "amostras_api", a.eleicoes)
        return 0
    if a.comando == "diagnosticar":
        from .diagnostico import diagnosticar
        diagnosticar(cfg)
        return 0
    if a.comando in ("baixar", "tudo"):
        from .baixar import baixar_api, baixar_cdn
        obtidos = {}
        if a.fonte in ("auto", "cdn"):
            obtidos = baixar_cdn(cfg)
        if a.fonte == "api" or (a.fonte == "auto" and not obtidos.get(f"votacao_candidato_munzona_{cfg.ano}")):
            print("[baixar] votação consolidada do ano indisponível no CDN — usando a API de divulgação")
            baixar_api(cfg, a.eleicoes)
    if a.comando in ("processar", "tudo"):
        from .carregar import processar
        processar(cfg)
    if a.comando in ("conferir", "tudo"):
        from .carregar import carregar
        conferir(cfg, carregar(cfg))
    if a.comando in ("analisar", "tudo"):
        from .carregar import carregar
        from .metricas import analisar
        from .relatorio import gerar_relatorio
        tabelas = carregar(cfg)
        resultados = analisar(cfg, tabelas)
        cfg.dir_saida.mkdir(parents=True, exist_ok=True)
        with open(cfg.dir_saida / "resultados.pkl", "wb") as f:
            pickle.dump(resultados, f)
        gerar_relatorio(cfg, resultados, sintetico=a.sintetico)
    return 0


if __name__ == "__main__":
    sys.exit(main())
