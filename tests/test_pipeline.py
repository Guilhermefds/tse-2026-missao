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


def _rezipar_com_brasil(origem: Path, destino: Path, brasil_com_presidente: bool) -> None:
    """Reempacota o zip sintético no layout _BRASIL.csv + _BR.csv (sem os CSVs por UF)."""
    import io
    import zipfile
    with zipfile.ZipFile(origem) as zf:
        nomes = [n for n in zf.namelist() if n.endswith(".csv")]
        br = next(n for n in nomes if n.endswith("_BR.csv"))
        ufs = [n for n in nomes if n != br]
        partes = [pd.read_csv(zf.open(n), sep=";", encoding="latin-1", dtype=str) for n in ufs]
        texto_br = zf.read(br)
    brasil = pd.concat(partes)
    if not brasil_com_presidente:
        brasil = brasil[brasil["CD_CARGO"] != "1"]
    buf = io.StringIO()
    brasil.to_csv(buf, sep=";", index=False, quoting=1)
    with zipfile.ZipFile(destino, "w") as zf:
        zf.writestr("votacao_candidato_munzona_2026_BRASIL.csv", buf.getvalue().encode("latin-1"))
        zf.writestr("votacao_candidato_munzona_2026_BR.csv", texto_br)


@pytest.mark.parametrize("brasil_com_presidente", [False, True])
def test_layout_brasil_mais_br(ambiente, tmp_path, brasil_com_presidente):
    from missao.carregar import processar_votacao_candidato
    cfg, t, _ = ambiente
    destino = tmp_path / "votacao_candidato_munzona_2026.zip"
    _rezipar_com_brasil(cfg.dir_brutos / "cdn" / "votacao_candidato_munzona_2026.zip", destino, brasil_com_presidente)
    novo = processar_votacao_candidato(cfg, destino)
    pres = lambda d: d[d.cd_cargo == 1].votos.sum()  # noqa: E731
    assert pres(novo["cand_mun"]) == pres(t["cand_mun"]) > 0          # nem perde, nem duplica Presidente
    assert novo["cand_uf"].query("cd_cargo == 6").votos.sum() == t["cand_uf"].query("cd_cargo == 6").votos.sum()


def test_analisar_sem_presidente_explica(ambiente):
    from missao.metricas import analisar
    cfg, t, _ = ambiente
    t2 = dict(t, cand_mun=t["cand_mun"][t["cand_mun"].cd_cargo != 1])
    with pytest.raises(SystemExit, match="diagnosticar"):
        analisar(cfg, t2)


# --------------------------------------------------------------------------- consolidados vazios → API

def _so_cabecalhos(z: Path) -> None:
    import zipfile
    with zipfile.ZipFile(z) as zf:
        membros = [(n, zf.read(n).split(b"\n", 1)[0] + b"\n") for n in zf.namelist()]
    with zipfile.ZipFile(z, "w") as zf:
        for n, cab in membros:
            zf.writestr(n, cab)


@pytest.fixture(scope="session")
def ambiente_api(tmp_path_factory):
    """Mesmos dados sintéticos, com os consolidados de 2026 publicados vazios (como o TSE fez) + JSON da API."""
    import shutil
    base = tmp_path_factory.mktemp("api")
    spec = importlib.util.spec_from_file_location("gerar_sintetico_api", RAIZ / "scripts" / "gerar_sintetico.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main(base / "cdn_ok" / "brutos" / "cdn", api=base / "api_ok" / "brutos" / "api")
    shutil.copytree(base / "cdn_ok" / "brutos" / "cdn", base / "vazio" / "brutos" / "cdn")
    shutil.copytree(base / "api_ok" / "brutos" / "api", base / "vazio" / "brutos" / "api")
    for nome in ("votacao_candidato_munzona_2026", "votacao_partido_munzona_2026", "detalhe_votacao_munzona_2026"):
        _so_cabecalhos(base / "vazio" / "brutos" / "cdn" / f"{nome}.zip")
    return base


def test_zip_so_com_cabecalho(ambiente_api):
    from missao.carregar import zip_tem_dados
    assert zip_tem_dados(ambiente_api / "cdn_ok" / "brutos" / "cdn" / "votacao_candidato_munzona_2026.zip")
    assert not zip_tem_dados(ambiente_api / "vazio" / "brutos" / "cdn" / "votacao_candidato_munzona_2026.zip")


def test_consolidado_vazio_usa_api_com_mesmos_totais(ambiente_api):
    ok = processar(carregar_config(dir_dados=ambiente_api / "cdn_ok", dir_saida=ambiente_api / "s1"))
    api = processar(carregar_config(dir_dados=ambiente_api / "vazio", dir_saida=ambiente_api / "s2"))
    for cargo in (1, 3, 5):
        a = ok["cand_mun"].query("cd_cargo == @cargo").votos.sum()
        assert api["cand_mun"].query("cd_cargo == @cargo").votos.sum() == a > 0
    for cargo in (6, 7):
        assert (api["partido_mun"].query("cd_cargo == @cargo").votos_total.sum()
                == ok["partido_mun"].query("cd_cargo == @cargo").votos_total.sum())
    # partido completado pelo cadastro (a API não traz sigla)
    assert (api["cand_uf"].query("nr_partido == 14").sg_partido == "MISSÃO").all()
    cfg = carregar_config(dir_dados=ambiente_api / "vazio", dir_saida=ambiente_api / "s2")
    r = analisar(cfg, carregar(cfg))
    assert r["podio"].nm_municipio.iat[0] == "VILA DO RENAN"
    assert "REDUTO DO DEPUTADO" in r["df_maior_que_pres"].nm_municipio.tolist()


def test_consolidado_vazio_sem_api_explica(ambiente_api, tmp_path):
    import shutil
    shutil.copytree(ambiente_api / "vazio" / "brutos" / "cdn", tmp_path / "brutos" / "cdn")
    with pytest.raises(SystemExit, match="--fonte api"):
        processar(carregar_config(dir_dados=tmp_path, dir_saida=tmp_path / "s"))


def test_limitador_respeita_taxa():
    import time
    from concurrent.futures import ThreadPoolExecutor
    from missao.baixar import Limitador
    lim = Limitador(50)
    t0 = time.monotonic()
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda _: lim.esperar(), range(51)))
    assert time.monotonic() - t0 >= 0.95  # 51 inícios a 50/s levam ≥ 1 s, mesmo com 8 threads


# --------------------------------------------------------------------------- API de divulgação 2026 (arquivos reais)

def test_descoberta_e_plano_de_download_com_config_real_2026(tmp_path):
    """Usa o ele-c.json e as configs de municípios reais (amostras_api/) com respostas simuladas."""
    import httpx
    from collections import Counter
    from missao import baixar
    amostras = RAIZ / "amostras_api"
    if not (amostras / "ele-c.json").exists():
        pytest.skip("amostras_api/ ausente")
    cm = {e: (amostras / f"e{e}_mun-cm.json").read_bytes() for e in ("6257", "6259")}

    def handler(req):
        p = req.url.path
        if p.endswith("ele-c.json"):
            return httpx.Response(200, content=(amostras / "ele-c.json").read_bytes())
        for e, b in cm.items():
            if p.endswith(f"mun-e00{e}-cm.json"):
                return httpx.Response(200, content=b)
        return httpx.Response(200, json={}) if p.endswith("-u.json") else httpx.Response(404)

    original = baixar._cliente
    baixar._cliente = lambda timeout=60: httpx.Client(transport=httpx.MockTransport(handler))
    try:
        cfg = carregar_config(dir_dados=tmp_path)
        achadas = {a["cd"]: a["cargos"] for a in baixar.descobrir_eleicoes(cfg, baixar._cliente())}
        assert achadas["6257"] == [1] and achadas["6259"] == [3, 5, 6, 7, 8]
        taxa, baixar.REQ_POR_SEGUNDO = baixar.REQ_POR_SEGUNDO, 1e6
        baixar.baixar_api(cfg)
        baixar.REQ_POR_SEGUNDO = taxa
    finally:
        baixar._cliente = original
    por_cargo = Counter(a.name.split("-c")[1][:4] for a in (tmp_path / "brutos" / "api").glob("*/*/*-u.json.gz"))
    assert por_cargo == {"0001": 5757, "0003": 5571, "0005": 5571, "0006": 5571, "0007": 5570, "0008": 1}


def test_leitor_com_arquivos_reais_da_api_2026(tmp_path):
    """Arquivos reais do TSE (São Paulo/SP) gravados pela sonda em amostras_api/."""
    import shutil
    from missao.carregar import processar_api
    a = RAIZ / "amostras_api"
    if not (a / "e6259_mun_u_c0006.json").exists():
        pytest.skip("amostras_api/ sem arquivos de resultado")
    mapa = {"e6257_mun_u_c0001.json": "6257/sp/sp71072-c0001-e006257-u.json",
            "e6259_mun_u_c0006.json": "6259/sp/sp71072-c0006-e006259-u.json",
            "e6259_mun_u_c0007.json": "6259/sp/sp71072-c0007-e006259-u.json",
            "e6257_mun-cm.json": "6257/mun-e006257-cm.json", "e6259_mun-cm.json": "6259/mun-e006259-cm.json",
            "e6259_br_e_c0006.json": "6259/br/br-c0006-e006259-e.json"}
    for origem, destino in mapa.items():
        (tmp_path / destino).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(a / origem, tmp_path / destino)
    t = processar_api(carregar_config(), tmp_path)
    det = t["detalhe_mun"].set_index("cd_cargo")
    pres = t["cand_mun"].query("cd_cargo == 1")
    assert pres.votos.sum() == det.loc[1, "validos"] == 6_552_820          # nominais válidos = válidos
    assert det.loc[1, "nm_municipio"] == "SÃO PAULO" and det.loc[1, "aptos"] == 9_145_124
    missao = t["partido_mun"].query("cd_cargo == 6 and nr_partido == 14").iloc[0]
    assert (missao.votos_nominais, missao.votos_legenda) == (217_235, 6_481)
    assert t["partido_mun"].query("cd_cargo == 6").votos_total.sum() == det.loc[6, "validos"]  # inclui legenda
    cu = t["cand_uf"]
    assert cu.query("cd_cargo == 6 and nm_urna == 'KIM KATAGUIRI'").situacao.iat[0] == "ELEITO"
    assert (cu.query("cd_cargo == 6").situacao == "ELEITO").sum() == 70        # lista oficial de SP
    assert (cu.query("cd_cargo == 7").situacao.str.startswith("ELEITO")).sum() == 94  # estimado pelas vagas
    assert set(pres.sort_values("votos").tail(2).situacao) == {"2º TURNO"}


def test_relatorio_a_partir_da_planilha(ambiente, tmp_path):
    from missao.relatorio import reprocessar_planilha
    cfg, _, r = ambiente
    cfg.dir_saida = tmp_path
    gerar_relatorio(cfg, r, sintetico=True)
    (tmp_path / "LEITURA.md").write_text("### Título\n\nTexto com **negrito**.\n\n- item um\n- item dois\n", encoding="utf-8")
    caminhos = reprocessar_planilha(cfg, sintetico=True)
    html = caminhos["html"].read_text(encoding="utf-8")
    assert "Leitura do resultado" in html and "<strong>negrito</strong>" in html and "<li>item dois</li>" in html
    esp = pd.read_excel(caminhos["xlsx"], sheet_name="esperado_por_uf")
    assert esp["razao_real_esperado"].std() > 0          # modelo sem efeito de UF diferencia os estados
    q = pd.read_excel(caminhos["xlsx"], sheet_name="quociente")
    assert (q["faltaram_proximo_qe"] > 0).all()


def test_pagina_completa_para_hospedagem(ambiente, tmp_path):
    import json
    cfg, _, r = ambiente
    cfg.dir_saida = tmp_path
    caminhos = gerar_relatorio(cfg, r, sintetico=True)
    site = caminhos["site"].read_text(encoding="utf-8")
    assert site.startswith("<!doctype html>") and site.rstrip().endswith("</html>")
    cabeca, corpo = site.split("</head>")
    assert "<title>" in cabeca and "<style>" in cabeca and "<title>" not in corpo
    assert 'href="analise_completa.xlsx"' in corpo
    vercel = json.loads((RAIZ / "vercel.json").read_text(encoding="utf-8"))
    assert vercel["outputDirectory"] == "saida" and vercel["framework"] is None


def test_clausula_de_barreira(ambiente):
    cfg, t, r = ambiente
    res = dict(zip(r["clausula_resumo"].indicador, r["clausula_resumo"].valor))
    base = r["base_municipal"]
    b = base[~base.exterior]
    assert res["Votos do partido para Dep. Federal (nominal + legenda)"] == b.df_total.sum()
    pct = res["% dos válidos no país"]
    assert pct == pytest.approx(100 * b.df_total.sum() / b.validos_df.sum())
    por_uf = r["clausula_por_uf"]
    assert (por_uf.faltam == (por_uf.meta_votos - por_uf.df_total).clip(lower=0)).all()
    assert por_uf.faltam_acumulado.iloc[-1] == por_uf.faltam.sum()
    partidos = r["clausula_partidos"]                       # com dados completos: todos os partidos
    assert partidos.destaque.sum() == 1 and set(partidos.columns) >= {"criterio_votos", "criterio_eleitos", "atingiu"}
    fe = partidos.set_index("agremiacao").loc["FE BRASIL"]  # federação soma PT e PC do B
    assert fe.partidos == "PC do B / PT"
    assert any(r["fatos"].tema == "Cláusula de barreira")


def test_tabela_filtros_e_restaurar():
    from missao.relatorio import tabela
    df = pd.DataFrame({"nm_municipio": [f"CIDADE {i}" for i in range(20)], "sg_uf": ["SP", "RS"] * 10,
                       "renan_votos": range(20)})
    h = tabela(df, id_="x", visiveis=12)
    assert 'class="filtro-uf"' in h and '<option value="RS">' in h            # UF separada
    assert 'class="busca"' in h and 'data-col="0"' in h                       # busca só no nome (1ª coluna)
    assert 'class="restaurar"' in h and 'autocomplete="off"' in h
    assert h.count('data-i="') == 20
