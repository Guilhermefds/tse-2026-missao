"""Testes ponta a ponta com dados sintéticos no formato do TSE (sem rede)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from missao.carregar import carregar, processar, sem_acento
from missao.config import carregar_config
from missao.metricas import analisar, corr_ponderada, div, elasticidade, suavizar_eb, vagas_assembleia
from missao.relatorio import fmt, gerar_relatorio, tipo_coluna

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def ambiente(tmp_path_factory):
    base = tmp_path_factory.mktemp("sint")
    spec = importlib.util.spec_from_file_location("gerar_sintetico", RAIZ / "scripts" / "gerar_sintetico.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main(base / "brutos" / "cdn")
    cfg = carregar_config(dir_dados=base, dir_saida=base / "saida")
    processar(cfg)
    t = carregar(cfg)
    r = analisar(cfg, t)
    return cfg, t, r


def test_sem_dupla_contagem_presidente(ambiente):
    _, t, _ = ambiente
    cm, det = t["cand_mun"], t["detalhe_mun"]
    # Presidente vem no _BR e nos arquivos por UF; deve ser contado uma vez só
    assert cm[cm.cd_cargo == 1].votos.sum() == det[det.cd_cargo == 1].validos.sum()


def test_voto_em_transito_somado(ambiente):
    _, t, _ = ambiente
    cz = t["cand_zona"]
    sp = cz[(cz.cd_cargo == 1) & (cz.nm_municipio == "SÃO PAULO") & (cz.nr_zona == 1)]
    assert sp.groupby("nr_candidato").size().max() == 1  # linhas N e S agregadas


def test_capitais_e_exterior(ambiente):
    _, t, _ = ambiente
    m = t["municipios"]
    assert m.capital.sum() == 27
    assert (m.sg_uf == "ZZ").sum() == 10 and m.loc[m.sg_uf == "ZZ", "exterior"].all()


def test_fatos_plantados(ambiente):
    _, _, r = ambiente
    assert "VILA DO RENAN" in r["podio"].nm_municipio.tolist()
    assert r["podio"].set_index("nm_municipio").loc["VILA DO RENAN", "renan_pos"] == 1
    assert r["distorcao_positiva"].iloc[0].nm_municipio == "VILA DO RENAN"
    assert "CIDADE SEM VOTO" in r["sem_votos"].nm_municipio.tolist()
    assert r["df_maior_que_pres"].iloc[0].nm_municipio == "REDUTO DO DEPUTADO"
    assert "DEPUTADO DO REDUTO" in r["candidato_maior_que_pres"].nm_urna.tolist()


def test_guarda_chuva(ambiente):
    cfg, t, r = ambiente
    gc = r["guarda_chuva_partidos"]
    meu = gc[gc.destaque]
    assert len(meu) == 1 and meu.nr.iat[0] == cfg.presidente_numero
    base = r["base_municipal"]
    esperado = base.df_total.sum() / base.renan_votos.sum()
    assert meu.razao_df.iat[0] == pytest.approx(esperado, rel=1e-3)
    assert 0 < meu.corr_mun_pres_df.iat[0] <= 1


def test_quociente(ambiente):
    _, _, r = ambiente
    q = r["quociente"]
    df = q[q.cargo == "Dep. Federal"]
    assert set(df.sg_uf) == set(r["por_uf"].sg_uf) - {"ZZ"}
    assert (df.vagas.sum()) == 513
    assert ((df.quocientes_partidarios >= 1) == (df.votos_partido >= df.qe)).all()
    assert (df.faltaram_para_qe == np.maximum(0, df.qe - df.votos_partido)).all()


def test_modelo_e_origem(ambiente):
    _, _, r = ambiente
    meta = r["modelo_meta"].set_index("item")["valor"]
    assert float(meta["Pseudo-R² (deviance)"]) > 0.5
    ov = r["origem_votos"]
    assert ov.taxa_migracao_estimada.between(0, 1).all()
    assert ov.pct_dos_votos_do_candidato.sum() == pytest.approx(100, abs=0.01)


def test_relatorio(ambiente, tmp_path):
    cfg, _, r = ambiente
    cfg.dir_saida = tmp_path
    caminhos = gerar_relatorio(cfg, r, sintetico=True)
    html = caminhos["html"].read_text(encoding="utf-8")
    assert html.startswith("<title>") and "DADOS SINTÉTICOS" in html
    assert caminhos["xlsx"].stat().st_size > 10_000
    assert "REDUTO DO DEPUTADO" in caminhos["md"].read_text(encoding="utf-8")


# --------------------------------------------------------------------------- unidades

def test_utilitarios():
    assert np.isnan(div(1, 0)) and div(1, 4) == 0.25
    assert corr_ponderada([1, 2, 3, 4], [2, 4, 6, 8], [1, 1, 1, 1]) == pytest.approx(1)
    assert elasticidade([1, 2, 4, 8, 16], [2, 4, 8, 16, 32], [1] * 5) == pytest.approx(1)
    assert vagas_assembleia(8) == 24 and vagas_assembleia(70) == 94 and vagas_assembleia(12) == 36
    assert sem_acento("São Luís") == "SAO LUIS"


def test_formatacao_ptbr():
    assert fmt(1234567, "int") == "1.234.567"
    assert fmt(3.14159, "pct") == "3,14%"
    assert fmt(0.725, "razao") == "0,72×" or fmt(0.725, "razao") == "0,73×"
    assert tipo_coluna("renan_pct100") == "pct" and tipo_coluna("razao_df") == "razao"


def test_suavizacao_encolhe_pequenos():
    base = pd.DataFrame({
        "sg_uf": ["XX"] * 6, "cd_municipio": range(6), "exterior": False,
        "renan_votos": [1, 50, 100, 150, 200, 3], "validos_pres": [10, 5000, 5000, 5000, 5000, 10],
    })
    s = suavizar_eb(base).set_index("cd_municipio")
    # 1 voto em 10 (10%) e 3 em 10 (30%) devem ser puxados fortemente para a média da UF (~2,5%)
    assert s.loc[0, "pct_suav"] < 0.06 and s.loc[5, "pct_suav"] < 0.08
    assert s.loc[2, "pct_suav"] == pytest.approx(0.02, abs=0.002)


# --------------------------------------------------------------------------- variações de formato do TSE

def _zip_csv(caminho: Path, nome: str, texto: str) -> Path:
    import zipfile
    with zipfile.ZipFile(caminho, "w") as zf:
        zf.writestr(nome, texto.encode("latin-1"))
    return caminho


def test_perfil_com_bom_e_coluna_alternativa(tmp_path):
    from missao.carregar import processar_perfil
    cab = '"DT_GERACAO";"SG_UF";"CD_MUNICIPIO";"DS_GENERO";"DS_FAIXA_ETARIA";"DS_GRAU_ESCOLARIDADE";"QT_ELEITORES_BIOMETRIA";"QT_ELEITORES"\n'
    linhas = ('"05/10/2026";"SP";"71072";"FEMININO";"21 a 24 anos";"SUPERIOR COMPLETO";"5";"30"\n'
              '"05/10/2026";"SP";"71072";"MASCULINO";"65 a 69 anos";"ENSINO MÉDIO COMPLETO";"5";"70"\n')
    arq = tmp_path / "perfil.zip"
    with __import__("zipfile").ZipFile(arq, "w") as zf:
        # BOM UTF-8 + corpo latin-1: lido como latin-1, o BOM vira "ï»¿" no nome da 1ª coluna
        zf.writestr("perfil_eleitorado_2026.csv", b"\xef\xbb\xbf" + (cab + linhas).encode("latin-1"))
    p = processar_perfil(carregar_config(), arq).iloc[0]
    from missao.carregar import CABECALHOS
    assert CABECALHOS["perfil.zip"][0] == "DT_GERACAO"
    assert p.eleitorado_perfil == 100
    assert p.pct_fem == pytest.approx(0.3) and p.pct_superior == pytest.approx(0.3) and p.pct_60m == pytest.approx(0.7)


def test_perfil_sem_contagem_vira_aviso(ambiente, tmp_path, capsys):
    import shutil
    cfg, _, _ = ambiente
    cdn = tmp_path / "brutos" / "cdn"
    shutil.copytree(cfg.dir_brutos / "cdn", cdn)
    (cdn / "perfil_eleitorado_2026.zip").unlink()
    _zip_csv(cdn / "perfil_eleitorado_2026.zip", "perfil_eleitorado_2026.csv",
             '"SG_UF";"CD_MUNICIPIO";"DS_GENERO"\n"SP";"71072";"FEMININO"\n')
    cfg2 = carregar_config(dir_dados=tmp_path, dir_saida=tmp_path / "saida")
    t = processar(cfg2)
    assert "perfil_mun" not in t and "cand_mun" in t
    saida = capsys.readouterr().out
    assert "perfil_eleitorado_2026.zip ignorado" in saida and "Colunas do arquivo" in saida
