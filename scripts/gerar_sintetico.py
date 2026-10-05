"""Gera dados SINTÉTICOS no formato exato do Portal de Dados Abertos do TSE.

Serve para testar o pipeline ponta a ponta sem acesso à rede. Nada aqui é resultado real.
Os arquivos imitam os .zip do CDN (CSV latin-1, separador ';', tudo entre aspas, um CSV por UF + _BR).

Fatos plantados (verificados em tests/):
  - "VILA DO RENAN" (PR): o presidenciável do partido fica em 1º lugar.
  - "REDUTO DO DEPUTADO" (MG): um deputado federal do partido tem muito mais votos que o presidenciável.
  - "CIDADE SEM VOTO" (PI): zero votos para o presidenciável.

Uso: python scripts/gerar_sintetico.py [destino] [--api]   (padrão: dados/sintetico/brutos/cdn)
     --api também grava os resultados no formato JSON da API de divulgação em <destino>/../api
"""
from __future__ import annotations

import csv
import io
import math
import sys
import zipfile
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from missao.metricas import VAGAS_CAMARA, vagas_assembleia  # noqa: E402

rng = np.random.default_rng(2026)
ANO, ANO_ANT = 2026, 2022
PARTIDO = 14

CAPITAIS = {
    "AC": "RIO BRANCO", "AL": "MACEIÓ", "AP": "MACAPÁ", "AM": "MANAUS", "BA": "SALVADOR", "CE": "FORTALEZA",
    "DF": "BRASÍLIA", "ES": "VITÓRIA", "GO": "GOIÂNIA", "MA": "SÃO LUÍS", "MT": "CUIABÁ", "MS": "CAMPO GRANDE",
    "MG": "BELO HORIZONTE", "PA": "BELÉM", "PB": "JOÃO PESSOA", "PR": "CURITIBA", "PE": "RECIFE", "PI": "TERESINA",
    "RJ": "RIO DE JANEIRO", "RN": "NATAL", "RS": "PORTO ALEGRE", "RO": "PORTO VELHO", "RR": "BOA VISTA",
    "SC": "FLORIANÓPOLIS", "SP": "SÃO PAULO", "SE": "ARACAJU", "TO": "PALMAS",
}
TAM_CAPITAL = {"SP": 9.3e6, "RJ": 5.0e6, "DF": 2.2e6, "BA": 2.0e6, "CE": 1.8e6, "MG": 1.9e6, "AM": 1.4e6,
               "PR": 1.4e6, "PE": 1.2e6, "RS": 1.1e6, "GO": 1.0e6, "PA": 1.0e6}
DIREITA = {"Norte": 0.55, "Nordeste": 0.32, "Centro-Oeste": 0.62, "Sudeste": 0.52, "Sul": 0.62}
REGIAO = {"AC": "Norte", "AP": "Norte", "AM": "Norte", "PA": "Norte", "RO": "Norte", "RR": "Norte", "TO": "Norte",
          "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste", "PB": "Nordeste",
          "PE": "Nordeste", "PI": "Nordeste", "RN": "Nordeste", "SE": "Nordeste", "DF": "Centro-Oeste",
          "GO": "Centro-Oeste", "MT": "Centro-Oeste", "MS": "Centro-Oeste", "ES": "Sudeste", "MG": "Sudeste",
          "RJ": "Sudeste", "SP": "Sudeste", "PR": "Sul", "RS": "Sul", "SC": "Sul"}
EXTERIOR = ["MIAMI", "LISBOA", "BOSTON", "TÓQUIO", "LONDRES", "NOVA YORK", "PORTO", "MADRI", "DUBLIN", "ORLANDO"]

# Partidos: número -> (sigla, federação)
PARTIDOS = {13: ("PT", "FE BRASIL"), 22: ("PL", None), 55: ("PSD", None), 15: ("MDB", None),
            44: ("UNIÃO", None), 10: ("REPUBLICANOS", None), 11: ("PP", None), 30: ("NOVO", None),
            40: ("PSB", None), 50: ("PSOL", "FE PSOL REDE"), 65: ("PC do B", "FE BRASIL"), 14: ("MISSÃO", None)}
# Presidenciáveis 2026 (nomes genéricos — dados sintéticos)
PRES26 = {13: "CANDIDATO PT", 22: "CANDIDATO PL", 14: "RENAN SANTOS", 30: "CANDIDATO NOVO", 55: "CANDIDATO PSD",
          44: "CANDIDATO UNIÃO", 16: "CANDIDATO PSTU", 80: "CANDIDATO UP"}
PRES22 = {13: "REF A", 22: "REF B", 12: "REF C", 15: "REF D", 30: "REF E", 44: "REF F", 14: "REF G"}

COLS_VOT = ["DT_GERACAO", "HH_GERACAO", "ANO_ELEICAO", "CD_TIPO_ELEICAO", "NM_TIPO_ELEICAO", "NR_TURNO", "CD_ELEICAO",
            "DS_ELEICAO", "DT_ELEICAO", "TP_ABRANGENCIA", "SG_UF", "SG_UE", "NM_UE", "CD_MUNICIPIO", "NM_MUNICIPIO",
            "NR_ZONA", "CD_CARGO", "DS_CARGO", "SQ_CANDIDATO", "NR_CANDIDATO", "NM_CANDIDATO", "NM_URNA_CANDIDATO",
            "NM_SOCIAL_CANDIDATO", "DS_SITUACAO_CANDIDATURA", "DS_DETALHE_SITUACAO_CAND", "TP_AGREMIACAO",
            "NR_PARTIDO", "SG_PARTIDO", "NM_PARTIDO", "NR_FEDERACAO", "NM_FEDERACAO", "SG_FEDERACAO",
            "ST_VOTO_EM_TRANSITO", "QT_VOTOS_NOMINAIS", "NM_TIPO_DESTINACAO_VOTOS", "QT_VOTOS_NOMINAIS_VALIDOS",
            "CD_SIT_TOT_TURNO", "DS_SIT_TOT_TURNO"]
COLS_PART = ["DT_GERACAO", "ANO_ELEICAO", "CD_TIPO_ELEICAO", "NR_TURNO", "CD_ELEICAO", "SG_UF", "SG_UE",
             "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "CD_CARGO", "DS_CARGO", "TP_AGREMIACAO", "NR_PARTIDO",
             "SG_PARTIDO", "NM_PARTIDO", "NR_FEDERACAO", "SG_FEDERACAO", "ST_VOTO_EM_TRANSITO",
             "QT_VOTOS_LEGENDA_VALIDOS", "QT_VOTOS_NOMINAIS_CONVR_LEGENDA", "QT_TOTAL_VOTOS_LEG_VALIDOS",
             "QT_VOTOS_NOMINAIS_VALIDOS", "QT_VOTOS_LEGENDA_ANULADOS", "QT_VOTOS_NOMINAIS_ANULADOS"]
COLS_DET = ["DT_GERACAO", "ANO_ELEICAO", "CD_TIPO_ELEICAO", "NR_TURNO", "CD_ELEICAO", "SG_UF", "SG_UE",
            "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "CD_CARGO", "DS_CARGO", "ST_VOTO_EM_TRANSITO", "QT_APTOS",
            "QT_SECOES", "QT_COMPARECIMENTO", "QT_ABSTENCOES", "QT_VOTOS_NOMINAIS_VALIDOS", "QT_VOTOS_BRANCOS",
            "QT_TOTAL_VOTOS_NULOS", "QT_VOTOS_NULOS", "QT_TOTAL_VOTOS_LEG_VALIDOS", "QT_VOTOS_LEG_VALIDOS"]
COLS_CONS = ["DT_GERACAO", "ANO_ELEICAO", "CD_TIPO_ELEICAO", "NR_TURNO", "SG_UF", "CD_CARGO", "DS_CARGO",
             "SQ_CANDIDATO", "NR_CANDIDATO", "NM_CANDIDATO", "NM_URNA_CANDIDATO", "NR_PARTIDO", "SG_PARTIDO",
             "SG_FEDERACAO", "DS_GENERO", "DS_GRAU_INSTRUCAO", "DS_OCUPACAO", "NR_IDADE_DATA_POSSE", "DS_COR_RACA",
             "DS_SITUACAO_CANDIDATURA", "DS_SIT_TOT_TURNO", "ST_REELEICAO"]
COLS_PERFIL = ["DT_GERACAO", "ANO_ELEICAO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "DS_GENERO",
               "DS_FAIXA_ETARIA", "DS_GRAU_ESCOLARIDADE", "QT_ELEITORES_PERFIL"]
NOME_CARGO = {1: "PRESIDENTE", 3: "GOVERNADOR", 5: "SENADOR", 6: "DEPUTADO FEDERAL", 7: "DEPUTADO ESTADUAL",
              8: "DEPUTADO DISTRITAL"}


# =========================================================================== geografia

def gerar_municipios():
    muns, cod = [], 10000
    for uf, reg in REGIAO.items():
        n = {"SP": 70, "MG": 70, "RS": 45, "PR": 45, "BA": 45, "SC": 35, "GO": 35, "DF": 1}.get(uf, 18)
        for i in range(n):
            cod += 7
            if i == 0:
                nome, aptos = CAPITAIS[uf], int(TAM_CAPITAL.get(uf, rng.uniform(2.5e5, 7e5)))
            else:
                nome, aptos = f"MUNICÍPIO {uf} {i:03d}", int(np.clip(rng.lognormal(9.4, 1.0), 1200, 1.2e6))
            muns.append(dict(uf=uf, cd=cod, nome=nome, aptos=aptos, capital=i == 0, regiao=reg))
    # fatos plantados
    especiais = {("PR", 5): "VILA DO RENAN", ("MG", 7): "REDUTO DO DEPUTADO", ("PI", 3): "CIDADE SEM VOTO"}
    for m in muns:
        idx = int(m["nome"].split()[-1]) if m["nome"].startswith("MUNICÍPIO") else -1
        if (m["uf"], idx) in especiais:
            m["nome"] = especiais[(m["uf"], idx)]
            m["aptos"] = {"VILA DO RENAN": 6200, "REDUTO DO DEPUTADO": 21000, "CIDADE SEM VOTO": 2400}[m["nome"]]
    for nome in EXTERIOR:
        cod += 7
        muns.append(dict(uf="ZZ", cd=cod, nome=nome, aptos=int(rng.uniform(3e3, 4e4)), capital=False, regiao="Exterior"))

    for m in muns:
        base = DIREITA.get(m["regiao"], 0.55)
        m["direita"] = float(np.clip(rng.normal(base, 0.10), 0.05, 0.92))
        m["superior"] = float(np.clip(rng.normal(0.30 if m["capital"] else 0.12, 0.05), 0.02, 0.6))
        m["jovem"] = float(np.clip(rng.normal(0.16, 0.03), 0.05, 0.35))
        m["abst"] = float(np.clip(rng.normal(0.21, 0.04), 0.08, 0.45))
        if m["uf"] == "ZZ":
            m["direita"], m["superior"], m["abst"] = 0.6, 0.5, 0.55
        # afinidade com o presidenciável do partido
        m["afin"] = -4.6 + 2.8 * m["direita"] + 4.0 * m["superior"] + 3.0 * m["jovem"] + rng.normal(0, 0.35)
        if m["nome"] == "VILA DO RENAN":
            m["afin"] = 3.5
        if m["nome"] == "CIDADE SEM VOTO":
            m["afin"] = -30
        nz = 1 if m["aptos"] < 60000 else min(30, math.ceil(m["aptos"] / 160000))
        pesos = rng.dirichlet(np.full(nz, 8.0))
        m["zonas"] = [(z + 1, int(m["aptos"] * p)) for z, p in enumerate(pesos)]
    return muns


def softmax(u):
    e = np.exp(u - np.max(u))
    return e / e.sum()


# =========================================================================== votação

def comparecimento(aptos, abst):
    comp = rng.binomial(aptos, 1 - abst)
    brancos = rng.binomial(comp, 0.025)
    nulos = rng.binomial(comp - brancos, 0.035)
    return comp, brancos, nulos, comp - brancos - nulos


def votos_presidente(m, validos, ano=ANO, ruido=0.08):
    d, s = m["direita"], m["superior"]
    if ano == ANO:
        nrs = list(PRES26)
        u = np.array([2.2 * (1 - d) * 2, 2.2 * d * 2, m["afin"] + 0.9, -3.6 + 3 * s, -3.0 + d, -3.4 + d, -6.0, -6.2])
    else:
        nrs = list(PRES22)
        u = np.array([2.2 * (1 - d) * 2, 2.2 * d * 2, -2.0 + 0.5 * (1 - d), -2.2 + 2.5 * s, -4.2 + 4 * s + d, -4.0 + d,
                      -6.0])
    u = u + rng.normal(0, ruido, len(u))
    return nrs, rng.multinomial(validos, softmax(u))


def shares_partidos(m, pres_share_renan):
    d = m["direita"]
    nrs = list(PARTIDOS)
    u = np.array([1.6 * (1 - d) * 2, 1.4 * d * 2, 0.8, 0.8, 0.6, 0.5, 0.5, -1.5 + 2 * m["superior"], 0.2,
                  -1.0 + m["superior"], -1.6, 0.0]) + rng.normal(0, 0.35, len(nrs))
    sh = softmax(u)
    # Missão proporcional ~ 70% do % do presidenciável, com ruído
    alvo = float(np.clip(pres_share_renan * rng.lognormal(np.log(0.7), 0.35), 0, 0.6))
    sh = sh * (1 - alvo) / (1 - sh[-1])
    sh[-1] = alvo
    return nrs, sh / sh.sum()


def escrever_api(destino_api: Path, muns, linhas_cand, linhas_det, linhas_part):
    """Grava os mesmos resultados no formato JSON 'dados-simplificados' da API de divulgação do TSE."""
    import json
    eleicoes = {1: "620", 3: "621", 5: "621", 6: "621", 7: "621", 8: "621"}
    agg_c: dict = {}
    for c, m, zona, q, cargo in linhas_cand:
        chave = (m["cd"], cargo, c["sq"])
        agg_c[chave] = agg_c.get(chave, (c, 0))[0], agg_c.get(chave, (c, 0))[1] + q
    agg_d: dict = {}
    for x in linhas_det:
        d = agg_d.setdefault((x["m"]["cd"], x["cargo"]), dict(e=0, c=0, a=0, vb=0, tvn=0, vv=0))
        d["e"] += x["aptos"]; d["c"] += x["comp"]; d["a"] += x["abst"]
        d["vb"] += x["br"]; d["tvn"] += x["nu"]; d["vv"] += x["nom"] + x["leg"]
    agg_l: dict = {}
    for x in linhas_part:
        agg_l[(x["m"]["cd"], x["cargo"], x["p"])] = agg_l.get((x["m"]["cd"], x["cargo"], x["p"]), 0) + x["leg"]
    por_mun = {m["cd"]: m for m in muns}
    cands_por: dict = {}
    for (cd, cargo, _), (c, q) in agg_c.items():
        cands_por.setdefault((cd, cargo), []).append((c, q))
    for ele in sorted(set(eleicoes.values())):
        abr = {}
        for m in muns:
            if ele == "621" and m["uf"] == "ZZ":
                continue
            abr.setdefault(m["uf"], []).append({"cd": f"{m['cd']:05d}", "nm": m["nome"], "c": "S" if m["capital"] else "N",
                                                "z": [f"{z:04d}" for z, _ in m["zonas"]]})
        cfg_mun = {"abr": [{"cd": uf, "ds": uf, "mu": mu} for uf, mu in abr.items()]}
        (destino_api / ele).mkdir(parents=True, exist_ok=True)
        (destino_api / ele / f"mun-e{int(ele):06d}-cm.json").write_text(json.dumps(cfg_mun, ensure_ascii=False))
    for (cd, cargo), lista in cands_por.items():
        m, ele = por_mun[cd], eleicoes[cargo]
        d = agg_d.get((cd, cargo), {})
        lista = sorted(lista, key=lambda t: -t[1])
        dados = {"ele": ele, "tpabr": "MU", "cdabr": f"{cd:05d}", **{k: str(v) for k, v in d.items()},
                 "cand": [{"seq": str(i + 1), "sqcand": c["sq"], "n": str(c["nr"]), "nm": c["nome"], "cc": "",
                           "e": "s" if c["situacao"].startswith("ELEITO") else "n", "st": c["situacao"].capitalize(),
                           "dvt": "Válido", "vap": str(q)} for i, (c, q) in enumerate(lista)]}
        if cargo in (6, 7, 8):
            dados["agr"] = [{"n": str(p), "sg": PARTIDOS[p][0], "vl": str(agg_l.get((cd, cargo, p), 0))} for p in PARTIDOS]
        pasta = destino_api / ele / m["uf"].lower()
        pasta.mkdir(parents=True, exist_ok=True)
        nome = f"{m['uf'].lower()}{cd:05d}-c{cargo:04d}-e{int(ele):06d}-r.json"
        (pasta / nome).write_text(json.dumps(dados, ensure_ascii=False))
    print(f"[sintético] API: {sum(1 for _ in destino_api.glob('*/*/*-r.json'))} arquivos JSON em {destino_api}")


def main(destino: Path, api: Path | None = None):
    destino.mkdir(parents=True, exist_ok=True)
    muns = gerar_municipios()
    sq = iter(range(250000000001, 250000999999))

    # ---------- candidatos proporcionais e majoritários estaduais
    cands = []  # dict(sq, nr, nome, cargo, uf, partido, forca, casa)

    def novo(cargo, uf, nr, nome, partido, forca=1.0, casa=None):
        c = dict(sq=str(next(sq)), nr=nr, nome=nome, cargo=cargo, uf=uf, partido=partido, forca=forca, casa=casa,
                 situacao="NÃO ELEITO")
        cands.append(c)
        return c

    for nr, nome in PRES26.items():
        novo(1, "BR", nr, nome, nr if nr in PARTIDOS else nr)
    ufs = sorted(REGIAO)
    for uf in ufs:
        vc = VAGAS_CAMARA[uf]
        cidades_uf = [m for m in muns if m["uf"] == uf]
        for cargo, vagas in ((6, vc), (7 if uf != "DF" else 8, 24 if uf == "DF" else vagas_assembleia(vc))):
            for p in PARTIDOS:
                n = max(3, math.ceil(vagas * 0.35)) if p != PARTIDO else max(3, math.ceil(vagas * 0.25))
                for k in range(n):
                    digitos = 2 if cargo == 6 else 3
                    nr = int(f"{p}{k + 1:0{digitos}d}")
                    casa = cidades_uf[rng.integers(0, len(cidades_uf))]["cd"] if rng.random() < 0.8 else None
                    nome = f"{PARTIDOS[p][0][:3]} {NOME_CARGO[cargo][:3]} {uf} {k + 1}"
                    if p == PARTIDO and cargo == 6 and uf == "MG" and k == 0:
                        casa = next(m["cd"] for m in cidades_uf if m["nome"] == "REDUTO DO DEPUTADO")
                        nome = "DEPUTADO DO REDUTO"
                    novo(cargo, uf, nr, nome, p, forca=float(rng.lognormal(0, 0.9)), casa=casa)
        for p in (13, 22, 55) + ((PARTIDO,) if uf in ("SP", "PR", "SC", "MG", "RS", "GO") else ()):
            novo(3, uf, p, f"GOV {PARTIDOS[p][0][:3]} {uf}", p)
        for p in (13, 22, 44) + ((PARTIDO,) if uf in ("SP", "PR", "SC", "RJ", "DF") else ()):
            novo(5, uf, p * 10 + 1, f"SEN {PARTIDOS[p][0][:3]} {uf}", p)

    por_cargo_uf: dict[tuple, list] = {}
    for c in cands:
        por_cargo_uf.setdefault((c["cargo"], c["uf"]), []).append(c)

    # ---------- votação por zona
    linhas_cand, linhas_part, linhas_det, linhas_cand_ant, linhas_perfil = [], [], [], [], []
    tot_cand: dict[str, int] = {}
    tot_part: dict[tuple, int] = {}

    for m in muns:
        uf = m["uf"]
        for zona, aptos_z in m["zonas"]:
            comp, br, nu, val = comparecimento(aptos_z, m["abst"])
            det_base = dict(uf=uf, m=m, zona=zona, aptos=aptos_z, comp=comp, abst=aptos_z - comp)
            # Presidente
            nrs, v = votos_presidente(m, val)
            share_renan = v[nrs.index(PARTIDO)] / max(val, 1)
            for nr, q in zip(nrs, v):
                c = next(c for c in por_cargo_uf[(1, "BR")] if c["nr"] == nr)
                linhas_cand.append((c, m, zona, int(q), 1))
                tot_cand[c["sq"]] = tot_cand.get(c["sq"], 0) + int(q)
            linhas_det.append({**det_base, "cargo": 1, "br": br, "nu": nu, "nom": val, "leg": 0})
            # 2022
            comp22, br22, nu22, val22 = comparecimento(aptos_z, m["abst"])
            nrs22, v22 = votos_presidente(m, val22, ano=ANO_ANT)
            for nr, q in zip(nrs22, v22):
                linhas_cand_ant.append((nr, m, zona, int(q)))
            if uf == "ZZ":
                continue
            # Perfil do eleitorado
            for gen, pg in (("FEMININO", 0.53), ("MASCULINO", 0.47)):
                for faixa, pf in (("16 anos", m["jovem"] * 0.2), ("21 a 24 anos", m["jovem"] * 0.8),
                                  ("30 a 34 anos", 0.25), ("45 a 49 anos", 0.35 - m["jovem"] / 2),
                                  ("65 a 69 anos", 0.40 - m["jovem"] / 2)):
                    for esc, pe in (("ENSINO FUNDAMENTAL INCOMPLETO", 0.55 - m["superior"]),
                                    ("ENSINO MÉDIO COMPLETO", 0.35), ("SUPERIOR INCOMPLETO", 0.10),
                                    ("SUPERIOR COMPLETO", m["superior"])):
                        linhas_perfil.append((m, zona, gen, faixa, esc, int(aptos_z * pg * pf * pe)))
            # Proporcionais
            for cargo in (6, 7 if uf != "DF" else 8):
                nrs_p, sh = shares_partidos(m, share_renan)
                v = rng.multinomial(val, sh)
                leg_tot = 0
                for p, q in zip(nrs_p, v):
                    leg = rng.binomial(q, 0.12 if p == PARTIDO else 0.06)
                    nom = q - leg
                    lista = [c for c in por_cargo_uf[(cargo, uf)] if c["partido"] == p]
                    pesos = np.array([c["forca"] * (25 if c["casa"] == m["cd"] else 1) for c in lista])
                    vc_ = rng.multinomial(nom, pesos / pesos.sum())
                    if p == PARTIDO and m["nome"] == "REDUTO DO DEPUTADO" and cargo == 6:
                        extra = int(val * 0.30)
                        vc_[0] += extra
                        nom += extra
                    for c, qq in zip(lista, vc_):
                        linhas_cand.append((c, m, zona, int(qq), cargo))
                        tot_cand[c["sq"]] = tot_cand.get(c["sq"], 0) + int(qq)
                    linhas_part.append(dict(m=m, zona=zona, cargo=cargo, p=p, nom=int(nom), leg=int(leg)))
                    tot_part[(cargo, uf, p)] = tot_part.get((cargo, uf, p), 0) + int(nom + leg)
                    leg_tot += leg
                linhas_det.append({**det_base, "cargo": cargo, "br": br, "nu": nu, "nom": val - leg_tot, "leg": leg_tot})
            # Governador e Senador (2 votos)
            for cargo, mult in ((3, 1), (5, 2)):
                lista = por_cargo_uf[(cargo, uf)]
                u = np.array([(m["direita"] * 3 if c["partido"] in (22, 44) else (1 - m["direita"]) * 3 if c["partido"] == 13
                               else (m["afin"] + 3.2 if c["partido"] == PARTIDO else 0.8)) for c in lista])
                v = rng.multinomial(val * mult, softmax(u + rng.normal(0, 0.2, len(u))))
                for c, q in zip(lista, v):
                    linhas_cand.append((c, m, zona, int(q), cargo))
                    tot_cand[c["sq"]] = tot_cand.get(c["sq"], 0) + int(q)
                linhas_det.append({**det_base, "cargo": cargo, "br": br * mult, "nu": nu * mult, "nom": val * mult, "leg": 0})

    # ---------- eleitos (D'Hondt simplificado + QE)
    for uf in ufs:
        vc = VAGAS_CAMARA[uf]
        for cargo, vagas in ((6, vc), (7 if uf != "DF" else 8, 24 if uf == "DF" else vagas_assembleia(vc))):
            votos_p = {p: tot_part.get((cargo, uf, p), 0) for p in PARTIDOS}
            qe = sum(votos_p.values()) / vagas
            n_cand = {p: sum(1 for c in por_cargo_uf[(cargo, uf)] if c["partido"] == p) for p in PARTIDOS}
            cadeiras = {p: min(int(v // qe), n_cand[p]) for p, v in votos_p.items()}

            def _media(k):  # maiores médias; partido sem candidato sobrando não recebe vaga
                if cadeiras[k] >= n_cand[k]:
                    return -1
                return votos_p[k] / (cadeiras[k] + 1) * (1 if votos_p[k] >= 0.8 * qe else 1e-6)
            while sum(cadeiras.values()) < vagas:
                cadeiras[max(votos_p, key=_media)] += 1
            for p in PARTIDOS:
                lista = sorted([c for c in por_cargo_uf[(cargo, uf)] if c["partido"] == p],
                               key=lambda c: -tot_cand.get(c["sq"], 0))
                qp = int(votos_p[p] // qe)
                for i, c in enumerate(lista):
                    if i < min(qp, cadeiras[p]):
                        c["situacao"] = "ELEITO POR QP"
                    elif i < cadeiras[p]:
                        c["situacao"] = "ELEITO POR MÉDIA"
                    elif cadeiras[p] > 0:
                        c["situacao"] = "SUPLENTE"
        for cargo in (3, 5):
            lista = sorted(por_cargo_uf[(cargo, uf)], key=lambda c: -tot_cand.get(c["sq"], 0))
            lista[0]["situacao"] = "ELEITO"
            if cargo == 5:
                lista[1]["situacao"] = "ELEITO"
    pres = sorted(por_cargo_uf[(1, "BR")], key=lambda c: -tot_cand.get(c["sq"], 0))
    pres[0]["situacao"] = pres[1]["situacao"] = "2º TURNO"

    # ---------- escrita
    comum = dict(DT_GERACAO="05/10/2026", HH_GERACAO="08:00:00", ANO_ELEICAO=str(ANO), CD_TIPO_ELEICAO="2",
                 NM_TIPO_ELEICAO="Eleição Ordinária", NR_TURNO="1", DT_ELEICAO="04/10/2026")

    def linha_cand(c, m, zona, q, cargo, ano=ANO, transito="N"):
        p = c["partido"]
        sg, fed = PARTIDOS.get(p, (f"P{p}", None))
        return {**comum, "ANO_ELEICAO": str(ano), "CD_ELEICAO": "620" if cargo == 1 else "621",
                "DS_ELEICAO": "Eleição Geral Federal 2026" if cargo == 1 else "Eleições Gerais Estaduais 2026",
                "TP_ABRANGENCIA": "F" if cargo == 1 else "E", "SG_UF": m["uf"], "SG_UE": "BR" if cargo == 1 else m["uf"],
                "NM_UE": "BRASIL" if cargo == 1 else m["uf"], "CD_MUNICIPIO": str(m["cd"]), "NM_MUNICIPIO": m["nome"],
                "NR_ZONA": str(zona), "CD_CARGO": str(cargo), "DS_CARGO": NOME_CARGO[cargo], "SQ_CANDIDATO": c["sq"],
                "NR_CANDIDATO": str(c["nr"]), "NM_CANDIDATO": c["nome"] + " DA SILVA", "NM_URNA_CANDIDATO": c["nome"],
                "NM_SOCIAL_CANDIDATO": "#NULO#", "DS_SITUACAO_CANDIDATURA": "APTO", "DS_DETALHE_SITUACAO_CAND": "DEFERIDO",
                "TP_AGREMIACAO": "FEDERAÇÃO" if fed else "PARTIDO ISOLADO", "NR_PARTIDO": str(p), "SG_PARTIDO": sg,
                "NM_PARTIDO": sg, "NR_FEDERACAO": "-1" if not fed else "999", "NM_FEDERACAO": fed or "#NULO#",
                "SG_FEDERACAO": fed or "#NULO#", "ST_VOTO_EM_TRANSITO": transito, "QT_VOTOS_NOMINAIS": str(q),
                "NM_TIPO_DESTINACAO_VOTOS": "Válido", "QT_VOTOS_NOMINAIS_VALIDOS": str(q), "CD_SIT_TOT_TURNO": "1",
                "DS_SIT_TOT_TURNO": c["situacao"]}

    def escrever_zip(nome_zip, colunas, linhas_por_uf: dict[str, list[dict]]):
        caminho = destino / nome_zip
        with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as zf:
            for uf, linhas in linhas_por_uf.items():
                buf = io.StringIO()
                w = csv.DictWriter(buf, fieldnames=colunas, delimiter=";", quoting=csv.QUOTE_ALL, extrasaction="ignore")
                w.writeheader()
                w.writerows(linhas)
                zf.writestr(f"{nome_zip[:-4]}_{uf}.csv", buf.getvalue().encode("latin-1"))
        print(f"[sintético] {caminho} ({caminho.stat().st_size / 1e6:.1f} MB)")

    vot: dict[str, list] = {}
    for c, m, zona, q, cargo in linhas_cand:
        if cargo == 1 and m["capital"] and zona == 1 and q > 10:  # parte do voto em trânsito
            t_ = q // 10
            vot.setdefault(m["uf"], []).append(linha_cand(c, m, zona, q - t_, cargo))
            vot.setdefault(m["uf"], []).append(linha_cand(c, m, zona, t_, cargo, transito="S"))
            vot.setdefault("BR", []).append(linha_cand(c, m, zona, q - t_, cargo))
            vot.setdefault("BR", []).append(linha_cand(c, m, zona, t_, cargo, transito="S"))
        else:
            vot.setdefault(m["uf"], []).append(linha_cand(c, m, zona, q, cargo))
            if cargo == 1:  # Presidente aparece no arquivo da UF e também no _BR (como no TSE)
                vot.setdefault("BR", []).append(linha_cand(c, m, zona, q, cargo))
    escrever_zip(f"votacao_candidato_munzona_{ANO}.zip", COLS_VOT, vot)

    part: dict[str, list] = {}
    for x in linhas_part:
        m, p = x["m"], x["p"]
        sg, fed = PARTIDOS[p]
        part.setdefault(m["uf"], []).append({
            **comum, "CD_ELEICAO": "621", "SG_UF": m["uf"], "SG_UE": m["uf"], "CD_MUNICIPIO": str(m["cd"]),
            "NM_MUNICIPIO": m["nome"], "NR_ZONA": str(x["zona"]), "CD_CARGO": str(x["cargo"]),
            "DS_CARGO": NOME_CARGO[x["cargo"]], "TP_AGREMIACAO": "FEDERAÇÃO" if fed else "PARTIDO ISOLADO",
            "NR_PARTIDO": str(p), "SG_PARTIDO": sg, "NM_PARTIDO": sg, "NR_FEDERACAO": "999" if fed else "-1",
            "SG_FEDERACAO": fed or "#NULO#", "ST_VOTO_EM_TRANSITO": "N", "QT_VOTOS_LEGENDA_VALIDOS": str(x["leg"]),
            "QT_VOTOS_NOMINAIS_CONVR_LEGENDA": "0", "QT_TOTAL_VOTOS_LEG_VALIDOS": str(x["leg"]),
            "QT_VOTOS_NOMINAIS_VALIDOS": str(x["nom"]), "QT_VOTOS_LEGENDA_ANULADOS": "0",
            "QT_VOTOS_NOMINAIS_ANULADOS": "0"})
    escrever_zip(f"votacao_partido_munzona_{ANO}.zip", COLS_PART, part)

    det: dict[str, list] = {}
    for x in linhas_det:
        m = x["m"]
        det.setdefault(m["uf"], []).append({
            **comum, "CD_ELEICAO": "620" if x["cargo"] == 1 else "621", "SG_UF": m["uf"],
            "SG_UE": "BR" if x["cargo"] == 1 else m["uf"], "CD_MUNICIPIO": str(m["cd"]), "NM_MUNICIPIO": m["nome"],
            "NR_ZONA": str(x["zona"]), "CD_CARGO": str(x["cargo"]), "DS_CARGO": NOME_CARGO[x["cargo"]],
            "ST_VOTO_EM_TRANSITO": "N", "QT_APTOS": str(x["aptos"]), "QT_SECOES": "1", "QT_COMPARECIMENTO": str(x["comp"]),
            "QT_ABSTENCOES": str(x["abst"]), "QT_VOTOS_NOMINAIS_VALIDOS": str(x["nom"]), "QT_VOTOS_BRANCOS": str(x["br"]),
            "QT_TOTAL_VOTOS_NULOS": str(x["nu"]), "QT_VOTOS_NULOS": str(x["nu"]),
            "QT_TOTAL_VOTOS_LEG_VALIDOS": str(x["leg"]), "QT_VOTOS_LEG_VALIDOS": str(x["leg"])})
    escrever_zip(f"detalhe_votacao_munzona_{ANO}.zip", COLS_DET, det)

    cons: dict[str, list] = {}
    for c in cands:
        sg, fed = PARTIDOS.get(c["partido"], (f"P{c['partido']}", None))
        cons.setdefault(c["uf"], []).append({
            **comum, "SG_UF": c["uf"], "CD_CARGO": str(c["cargo"]), "DS_CARGO": NOME_CARGO[c["cargo"]],
            "SQ_CANDIDATO": c["sq"], "NR_CANDIDATO": str(c["nr"]), "NM_CANDIDATO": c["nome"] + " DA SILVA",
            "NM_URNA_CANDIDATO": c["nome"], "NR_PARTIDO": str(c["partido"]), "SG_PARTIDO": sg,
            "SG_FEDERACAO": fed or "#NULO#", "DS_GENERO": rng.choice(["MASCULINO", "FEMININO"]),
            "DS_GRAU_INSTRUCAO": "SUPERIOR COMPLETO", "DS_OCUPACAO": "OUTROS",
            "NR_IDADE_DATA_POSSE": str(int(rng.integers(25, 70))), "DS_COR_RACA": "PARDA",
            "DS_SITUACAO_CANDIDATURA": "APTO", "DS_SIT_TOT_TURNO": c["situacao"], "ST_REELEICAO": "N"})
    escrever_zip(f"consulta_cand_{ANO}.zip", COLS_CONS, cons)

    perf: dict[str, list] = {}
    for m, zona, gen, faixa, esc, q in linhas_perfil:
        perf.setdefault(m["uf"], []).append({
            "DT_GERACAO": "05/10/2026", "ANO_ELEICAO": str(ANO), "SG_UF": m["uf"], "CD_MUNICIPIO": str(m["cd"]),
            "NM_MUNICIPIO": m["nome"], "NR_ZONA": str(zona), "DS_GENERO": gen, "DS_FAIXA_ETARIA": faixa,
            "DS_GRAU_ESCOLARIDADE": esc, "QT_ELEITORES_PERFIL": str(max(q, 0))})
    escrever_zip(f"perfil_eleitorado_{ANO}.zip", COLS_PERFIL, perf)

    ant: dict[str, list] = {}
    for nr, m, zona, q in linhas_cand_ant:
        c = dict(sq=f"2022{nr}", nr=nr, nome=PRES22[nr], partido=nr, situacao="NÃO ELEITO")
        ant.setdefault("BR", []).append(linha_cand(c, m, zona, q, 1, ano=ANO_ANT))
    escrever_zip(f"votacao_candidato_munzona_{ANO_ANT}.zip", COLS_VOT, ant)
    if api is not None:
        escrever_api(api, muns, linhas_cand, linhas_det, linhas_part)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cdn = Path(args[0]) if args else RAIZ / "dados" / "sintetico" / "brutos" / "cdn"
    main(cdn, api=cdn.parent / "api" if "--api" in sys.argv else None)
