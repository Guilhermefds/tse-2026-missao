"""Download dos dados do TSE.

Fonte principal: Portal de Dados Abertos (CDN) — arquivos .zip com CSVs por UF.
Fonte alternativa: API de divulgação (resultados.tse.jus.br), usada quando os
arquivos consolidados do ano ainda não foram publicados no portal (o que é comum
nos primeiros dias após a eleição).
"""
from __future__ import annotations

import gzip
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

from .carregar import zip_tem_dados
from .config import Config, DEP_DISTRITAL, DEP_ESTADUAL, DEP_FEDERAL, GOVERNADOR, PRESIDENTE, SENADOR

# (pasta no CDN, ano relativo) — "atual" = ano da eleição; "comparacao" = ano de referência
DATASETS_CDN = [
    ("votacao_candidato_munzona", "atual"),
    ("votacao_partido_munzona", "atual"),
    ("detalhe_votacao_munzona", "atual"),
    ("consulta_cand", "atual"),
    ("perfil_eleitorado", "atual"),
    ("votacao_candidato_munzona", "comparacao"),
]

CARGOS_API = [PRESIDENTE, GOVERNADOR, SENADOR, DEP_FEDERAL, DEP_ESTADUAL, DEP_DISTRITAL]

# O TSE permite até 100 requisições/s por IP na divulgação; acima disso bloqueia o IP por 10 minutos
# (e reinicia a contagem a cada nova tentativa). Ficamos bem abaixo e, se bloqueados, esperamos 11 min.
REQ_POR_SEGUNDO = 40
PAUSA_BLOQUEIO = 11 * 60


class Limitador:
    """Garante no máximo `taxa` inícios de requisição por segundo, somando todas as threads."""

    def __init__(self, taxa: float):
        self.intervalo = 1.0 / taxa
        self.proximo = time.monotonic()
        self.trava = threading.Lock()
        self.bloqueado_ate = 0.0
        self.pausas = 0

    def esperar(self) -> None:
        with self.trava:
            agora = time.monotonic()
            inicio = max(self.proximo, agora, self.bloqueado_ate)
            self.proximo = inicio + self.intervalo
        time.sleep(max(0.0, inicio - time.monotonic()))

    def bloquear(self, segundos: float, maximo: int = 3) -> bool | None:
        """Pausa todas as threads. True para a thread que iniciou a pausa (avisa uma vez), False se já havia
        pausa em curso, None se o limite de pausas acabou (aí o 403 não é por excesso de requisições)."""
        with self.trava:
            alvo = time.monotonic() + segundos
            if alvo - self.bloqueado_ate < 60:
                return False
            if self.pausas >= maximo:
                return None
            self.pausas += 1
            self.bloqueado_ate = alvo
            return True


def _cliente(timeout: float = 120.0) -> httpx.Client:
    # trust_env=True faz o httpx respeitar HTTPS_PROXY e SSL_CERT_FILE do ambiente
    return httpx.Client(timeout=timeout, follow_redirects=True, trust_env=True,
                        headers={"User-Agent": "analise-missao-2026/1.0"})


def _com_retentativas(func, tentativas: int = 4):
    espera = 2
    for i in range(tentativas):
        try:
            return func()
        except (httpx.TransportError, httpx.HTTPStatusError) as erro:
            if isinstance(erro, httpx.HTTPStatusError) and erro.response.status_code in (403, 404):
                raise
            if i == tentativas - 1:
                raise
            time.sleep(espera)
            espera *= 2


def baixar_arquivo(url: str, destino: Path, cliente: httpx.Client | None = None) -> Path:
    """Baixa `url` para `destino` (streaming). Pula se já existir."""
    if destino.exists() and destino.stat().st_size > 0:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(destino.suffix + ".parcial")
    proprio = cliente is None
    cliente = cliente or _cliente()
    try:
        def _baixar():
            with cliente.stream("GET", url) as resposta:
                resposta.raise_for_status()
                with open(temporario, "wb") as f:
                    for bloco in resposta.iter_bytes(1 << 20):
                        f.write(bloco)
        _com_retentativas(_baixar)
        temporario.rename(destino)
    finally:
        if proprio:
            cliente.close()
    return destino


def baixar_cdn(cfg: Config, apenas: list[str] | None = None) -> dict[str, Path | None]:
    """Baixa os .zip do Portal de Dados Abertos. Retorna {nome: caminho ou None se indisponível}."""
    resultado: dict[str, Path | None] = {}
    with _cliente(timeout=600) as cliente:
        for pasta, quando in DATASETS_CDN:
            ano = cfg.ano if quando == "atual" else cfg.ano_comparacao
            nome = f"{pasta}_{ano}"
            if apenas and nome not in apenas and pasta not in apenas:
                continue
            candidatos_url = [f"{cfg.url_cdn}/{pasta}/{nome}.zip"]
            if pasta == "perfil_eleitorado":
                candidatos_url.append(f"{cfg.url_cdn}/{pasta}/{pasta}_ATUAL.zip")
            resultado[nome] = None
            for url in candidatos_url:
                destino = cfg.dir_brutos / "cdn" / Path(url).name
                if destino.exists() and not zip_tem_dados(destino):
                    destino.unlink()  # versão antiga só com cabeçalhos: tenta de novo
                try:
                    print(f"[cdn] {url}")
                    baixar_arquivo(url, destino, cliente)
                    if not zip_tem_dados(destino):
                        print("      publicado sem dados (só cabeçalhos) — o TSE ainda não liberou este arquivo")
                        destino.unlink()
                        continue
                    resultado[nome] = destino
                    break
                except httpx.HTTPStatusError as erro:
                    print(f"      indisponível ({erro.response.status_code})")
                except httpx.TransportError as erro:
                    print(f"      falha de rede: {erro}")
    return resultado


# --------------------------------------------------------------------------- API de divulgação

def _get_json(cliente: httpx.Client, url: str):
    def _f():
        r = cliente.get(url)
        r.raise_for_status()
        return r.json()
    return _com_retentativas(_f)


# Modelos de endereço do resultado por município e cargo, em ordem de preferência (o TSE muda entre ciclos).
# 2026: o ele-c.json declara o arquivo "u" (resultado unificado) em <ciclo>/<eleição>/dados/<uf>/;
# 2022/2024 usavam "dados-simplificados/…-r.json". O download testa cada modelo num município e usa o que responder.
MODELOS_MUN = [
    ("u", "{ele}/dados/{uf}/{uf}{mun}-c{c4}-e{e6}-u.json"),
    ("r", "{ele}/dados-simplificados/{uf}/{uf}{mun}-c{c4}-e{e6}-r.json"),
    ("v", "{ele}/dados/{uf}/{uf}{mun}-c{c4}-e{e6}-v.json"),
]


def descobrir_eleicoes(cfg: Config, cliente: httpx.Client) -> list[dict]:
    """Lê comum/config/ele-c.json e devolve as eleições do ciclo `ele{ano}` com seus cargos.

    Formato (2024–2026): {"pl": [{"c": "ele2026", "e": [{"cd": "6257", "t": "1", "nm": …,
    "abr": [{"cd": "br", "cp": [{"cd": "1", "ds": "Presidente"}]}]}]}]}. Se mudar, cai numa varredura tolerante.
    """
    dados = _get_json(cliente, f"{cfg.url_divulgacao}/comum/config/ele-c.json")
    ciclo = f"ele{cfg.ano}"
    achadas: list[dict] = []
    for pl in dados.get("pl", []) if isinstance(dados, dict) else []:
        if pl.get("c") != ciclo:
            continue
        for el in pl.get("e", []):
            cargos = sorted({int(cp["cd"]) for a in el.get("abr", []) for cp in a.get("cp", [])
                             if str(cp.get("cd", "")).isdigit()})
            achadas.append({"cd": str(el.get("cd")), "nm": el.get("nm", ""), "t": str(el.get("t", "")),
                            "tp": str(el.get("tp", "")), "cargos": cargos, "ciclo": ciclo})
    if achadas:
        return achadas

    def _varrer(no, ciclo_atual=None):
        if isinstance(no, dict):
            c = no.get("c") or ciclo_atual
            texto = json.dumps({k: v for k, v in no.items() if not isinstance(v, (list, dict))})
            if "cd" in no and ("nm" in no or "t" in no) and (str(cfg.ano) in texto or str(cfg.ano) in str(c)):
                achadas.append({**{k: v for k, v in no.items() if not isinstance(v, (list, dict))},
                                "ciclo": c, "cargos": []})
            for v in no.values():
                _varrer(v, c)
        elif isinstance(no, list):
            for v in no:
                _varrer(v, ciclo_atual)

    _varrer(dados)
    return achadas


def _amostra(mun_cfg: dict) -> tuple[str, str]:
    """UF e município de amostra para testar endereços: São Paulo/SP, ou o primeiro disponível."""
    ufs = {u["cd"].lower(): u for u in mun_cfg.get("abr", []) if u.get("mu")}
    uf = ufs.get("sp") or next((u for k, u in ufs.items() if k != "zz"), None) or next(iter(ufs.values()))
    mun = next((m["cd"] for m in uf["mu"] if m.get("cd") == "71072"), uf["mu"][0]["cd"])
    return uf["cd"].lower(), mun


def _url_mun(cfg: Config, modelo: str, ele: str, uf: str, mun: str, cargo: int) -> str:
    rel = modelo.format(ele=ele, uf=uf, mun=mun, c4=f"{cargo:04d}", e6=f"{int(ele):06d}")
    return f"{cfg.url_divulgacao}/ele{cfg.ano}/{rel}"


def baixar_api(cfg: Config, eleicoes: list[str] | None = None, max_workers: int = 16) -> Path:
    """Baixa o resultado de cada município × cargo da API de divulgação.

    Salva em dados/brutos/api/{eleição}/{uf}/<nome do arquivo do TSE>.gz (JSON compactado, ~10× menor).
    `eleicoes`: códigos (ex.: ["6257", "6259"]). Se omitido, descobre pelo ele-c.json.
    """
    base = cfg.dir_brutos / "api"
    base.mkdir(parents=True, exist_ok=True)
    with _cliente(timeout=60) as cliente:
        try:
            achadas = descobrir_eleicoes(cfg, cliente)
        except httpx.HTTPError as erro:
            print(f"[api] não consegui ler o ele-c.json: {erro}")
            achadas = []
        (base / "eleicoes_descobertas.json").write_text(json.dumps(achadas, ensure_ascii=False, indent=1),
                                                        encoding="utf-8")
        por_cd = {e["cd"]: e for e in achadas}
        if eleicoes:
            selecionadas = [por_cd.get(str(e), {"cd": str(e), "cargos": []}) for e in eleicoes]
        else:
            selecionadas = [e for e in achadas if e.get("t", "1") == str(cfg.turno)
                            and (not e.get("cargos") or set(e["cargos"]) & set(CARGOS_API))]
        print(f"[api] eleições: {[(e['cd'], e.get('nm', ''), e.get('cargos')) for e in selecionadas]}")
        if not selecionadas:
            print("[api] nenhuma eleição encontrada no ele-c.json — rode `python -m missao sondar` e envie a pasta "
                  "amostras_api/ (veja o README)")
        tarefas = []
        for el in selecionadas:
            ele = el["cd"]
            e6 = f"{int(ele):06d}"
            try:
                mun_cfg = _get_json(cliente, f"{cfg.url_divulgacao}/ele{cfg.ano}/{ele}/config/mun-e{e6}-cm.json")
            except httpx.HTTPError:
                print(f"[api] sem config de municípios para a eleição {ele}")
                continue
            (base / ele).mkdir(parents=True, exist_ok=True)
            (base / ele / f"mun-e{e6}-cm.json").write_text(json.dumps(mun_cfg, ensure_ascii=False), encoding="utf-8")
            cargos = [c for c in (el.get("cargos") or CARGOS_API) if c in CARGOS_API]
            uf_a, mun_a = _amostra(mun_cfg)
            cargo_a = next((c for c in cargos if c != DEP_DISTRITAL), cargos[0])
            modelo = None
            for tp, m in MODELOS_MUN:
                url = _url_mun(cfg, m, ele, uf_a, mun_a, cargo_a)
                st = cliente.get(url).status_code
                print(f"[api] eleição {ele}: modelo '{tp}' → HTTP {st} ({url})")
                if st == 200:
                    modelo = m
                    break
            if modelo is None:
                print(f"[api] eleição {ele}: nenhum modelo de endereço respondeu — rode `python -m missao sondar`")
                continue
            print(f"[api] eleição {ele}: cargos {cargos}")
            for uf in mun_cfg.get("abr", []):
                sg = uf["cd"].lower()
                for mun in uf.get("mu", []):
                    for cargo in cargos:
                        if cargo == DEP_DISTRITAL and sg != "df":
                            continue
                        if cargo == DEP_ESTADUAL and sg == "df":
                            continue
                        if cargo != PRESIDENTE and sg == "zz":
                            continue
                        url = _url_mun(cfg, modelo, ele, sg, mun["cd"], cargo)
                        tarefas.append((url, base / ele / sg / (url.rsplit("/", 1)[1] + ".gz")))
            for cargo in cargos:  # lista oficial de eleitos por UF (Governador, Senador, Deputados)
                if cargo != PRESIDENTE:
                    nome = f"br-c{cargo:04d}-e{e6}-e.json"
                    tarefas.append((f"{cfg.url_divulgacao}/ele{cfg.ano}/{ele}/dados/br/{nome}",
                                    base / ele / "br" / (nome + ".gz")))

        print(f"[api] {len(tarefas)} arquivos candidatos")
        faltando = [(u, d) for u, d in tarefas if not d.exists()]

        limitador = Limitador(REQ_POR_SEGUNDO)

        def _um(par):
            url, destino = par
            for tentativa in range(4):
                try:
                    limitador.esperar()
                    r = cliente.get(url)
                    if r.status_code == 404:
                        return "404"
                    if r.status_code in (403, 429):  # bloqueio por excesso de requisições
                        pausa = limitador.bloquear(PAUSA_BLOQUEIO)
                        if pausa is None:
                            return f"erro: HTTP {r.status_code}"
                        if pausa:
                            print(f"[api] o TSE bloqueou temporariamente o acesso (HTTP {r.status_code}); "
                                  f"pausando {PAUSA_BLOQUEIO // 60} minutos e continuando…")
                        continue
                    if r.status_code in (500, 502, 503, 504):
                        time.sleep(2 ** (tentativa + 1))
                        continue
                    r.raise_for_status()
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    temporario = destino.with_name(destino.name + ".parcial")
                    temporario.write_bytes(gzip.compress(r.content) if destino.suffix == ".gz" else r.content)
                    temporario.replace(destino)
                    return "ok"
                except httpx.TransportError:
                    time.sleep(2 ** (tentativa + 1))
                except Exception as erro:  # noqa: BLE001 — registra e segue
                    return f"erro: {erro}"
            return "erro: esgotou tentativas"

        contagem: dict[str, int] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for i, st in enumerate(as_completed(pool.submit(_um, t) for t in faltando)):
                chave = st.result().split(":")[0]
                contagem[chave] = contagem.get(chave, 0) + 1
                if i % 2000 == 0:
                    print(f"[api] {i}/{len(faltando)} {contagem}")
        print(f"[api] concluído: {contagem}. Se houver erros, rode o mesmo comando de novo: só o que falta é baixado.")
    return base


# --------------------------------------------------------------------------- sonda da API (diagnóstico)

def _padroes_url(cfg: Config, ele: str, uf: str, mun: str, cargo: int) -> dict[str, str]:
    """Endereços candidatos (por município, por UF e Brasil) — o layout muda entre ciclos."""
    e6, c4, b = f"{int(ele):06d}", f"{cargo:04d}", f"{cfg.url_divulgacao}/ele{cfg.ano}/{ele}"
    urls = {f"mun_{tp}_c{c4}": _url_mun(cfg, m, ele, uf, mun, cargo) for tp, m in MODELOS_MUN}
    urls.update({
        f"uf_u_c{c4}": f"{b}/dados/{uf}/{uf}-c{c4}-e{e6}-u.json",
        f"uf_e_c{c4}": f"{b}/dados/{uf}/{uf}-c{c4}-e{e6}-e.json",
        f"br_u_c{c4}": f"{b}/dados/br/br-c{c4}-e{e6}-u.json",
        f"br_e_c{c4}": f"{b}/dados/br/br-c{c4}-e{e6}-e.json",
    })
    return urls


def sondar_api(cfg: Config, destino: Path, eleicoes_extra: list[str] | None = None) -> None:
    """Testa os endereços da API de divulgação num município de amostra e grava as respostas reais em `destino`.

    Serve para ajustar o leitor quando o formato do ciclo muda. Poucas dezenas de requisições, em sequência.
    """
    destino.mkdir(parents=True, exist_ok=True)
    ciclo = f"ele{cfg.ano}"
    base = f"{cfg.url_divulgacao}/{ciclo}"
    log: list[str] = []

    def reg(msg: str) -> None:
        print(msg)
        log.append(msg)

    def pegar(nome: str, url: str) -> bytes | None:
        time.sleep(0.15)
        try:
            r = cliente.get(url)
        except httpx.HTTPError as erro:
            reg(f"ERRO  {nome}: {url} — {erro}")
            return None
        reg(f"{r.status_code}   {nome}: {url} ({len(r.content):,} bytes)")
        if r.status_code == 200:
            (destino / f"{nome}.json").write_bytes(r.content)
            return r.content
        return None

    with _cliente(timeout=60) as cliente:
        bruto = pegar("ele-c", f"{cfg.url_divulgacao}/comum/config/ele-c.json")
        eleicoes: list[str] = []
        cargos_de: dict[str, list[int]] = {}
        if bruto:
            achadas = descobrir_eleicoes(cfg, cliente)
            reg(f"eleições encontradas no ele-c.json: {[(e.get('cd'), e.get('nm'), e.get('cargos')) for e in achadas]}")
            cargos_de = {e["cd"]: [c for c in e.get("cargos", []) if c in CARGOS_API] for e in achadas}
            eleicoes = [e["cd"] for e in achadas if str(e.get("cd", "")).isdigit()
                        and (not e.get("cargos") or cargos_de[e["cd"]])]
        eleicoes = list(dict.fromkeys([*(eleicoes_extra or []), *eleicoes]))
        if not eleicoes:
            reg("nenhum código de eleição — abra o site de resultados do TSE, escolha Presidente e veja no endereço "
                "o trecho e=eNNN; rode de novo com `python -m missao sondar --eleicoes NNN`")
        for ele in eleicoes[:6]:
            e6 = f"{int(ele):06d}"
            cfg_b = pegar(f"e{ele}_mun-cm", f"{base}/{ele}/config/mun-e{e6}-cm.json")
            uf, mun = "sp", "71072"
            if cfg_b:
                try:
                    abr = {u["cd"].lower(): u for u in json.loads(cfg_b).get("abr", [])}
                    u = abr.get("sp") or next(iter(abr.values()))
                    uf = u["cd"].lower()
                    mun = next((m["cd"] for m in u.get("mu", []) if "SÃO PAULO" in m.get("nm", "").upper()),
                               u["mu"][0]["cd"])
                except Exception as erro:  # noqa: BLE001
                    reg(f"      não consegui ler a config de municípios: {erro}")
            reg(f"      amostra: uf={uf} município={mun}")
            for cargo in (cargos_de.get(ele) or CARGOS_API) if bruto else CARGOS_API:
                for nome, url in _padroes_url(cfg, ele, uf, mun, cargo).items():
                    pegar(f"e{ele}_{nome}", url)
            pegar(f"e{ele}_uf_ab", f"{base}/{ele}/dados/{uf}/{uf}-e{e6}-ab.json")
            pegar(f"e{ele}_mun_ab", f"{base}/{ele}/dados/{uf}/{uf}{mun}-e{e6}-ab.json")
        _sondar_app(cfg, cliente, destino, reg)
    (destino / "LEIAME.txt").write_text(
        "Respostas reais da API de divulgação do TSE, gravadas por `python -m missao sondar`.\n"
        "Status HTTP de cada endereço testado:\n\n" + "\n".join(log) + "\n", encoding="utf-8")
    print(f"\n[sondar] {sum(1 for _ in destino.glob('*.json'))} respostas salvas em {destino}. Envie a pasta pelo git:")
    print(f"  git add {destino.name} && git commit -m \"Amostras da API do TSE\" && git push")


def _sondar_app(cfg: Config, cliente: httpx.Client, destino: Path, reg) -> None:
    """Lê o JavaScript do site oficial de resultados e extrai os modelos de URL de arquivos .json.

    O site do TSE monta os endereços dos resultados no navegador; os modelos ficam no código do app.
    Grava os trechos relevantes em app_urls.txt (sem baixar dados de resultado).
    """
    import re
    from urllib.parse import urljoin

    r = None
    raiz = cfg.url_divulgacao.rsplit("/oficial", 1)[0]
    for app in (f"{cfg.url_divulgacao}/app/index.html", f"{cfg.url_divulgacao}/app/", f"{raiz}/", f"{raiz}/index.html"):
        try:
            r = cliente.get(app)
        except httpx.HTTPError as erro:
            reg(f"ERRO  app: {app} — {erro}")
            continue
        reg(f"{r.status_code}   app: {app} ({len(r.content):,} bytes)")
        if r.status_code == 200 and ".js" in r.text:
            app = str(r.url)
            break
    else:
        return
    (destino / "app_index.html").write_bytes(r.content)
    pendentes = list(dict.fromkeys(re.findall(r'(?:src|href)="([^"]+\.js)"', r.text)))
    vistos: set[str] = set()
    trechos: list[str] = []
    padrao = re.compile(r".{0,200}(?:\.json|dados-simplificados|/dados/|/config/|-cm\b|-r\b|-u\b|-v\b|-f\b).{0,200}")
    chave = re.compile(r"json|dados|config|abr|cargo|ele|mun", re.I)
    while pendentes and len(vistos) < 60:
        js = pendentes.pop(0)
        url = urljoin(app, js)
        if url in vistos:
            continue
        vistos.add(url)
        time.sleep(0.2)
        try:
            rj = cliente.get(url)
        except httpx.HTTPError:
            continue
        reg(f"{rj.status_code}   js: {url} ({len(rj.content):,} bytes)")
        if rj.status_code != 200:
            continue
        texto = rj.text
        for m in padrao.finditer(texto):
            t = m.group(0)
            if ".json" in t and chave.search(t):
                trechos.append(f"[{Path(url).name}] {t}")
        # chunks carregados sob demanda (webpack/angular): nomes como 123.abcdef0123.js ou chunk-XYZ.js
        for nome in re.findall(r'["\']([\w.-]+\.[0-9a-f]{8,}\.js|chunk-[\w-]+\.js)["\']', texto):
            pendentes.append(nome)
        for num, hsh in re.findall(r'(\d+):"([0-9a-f]{16,20})"', texto)[:200]:
            pendentes.append(f"{num}.{hsh}.js")
    unicos = list(dict.fromkeys(trechos))
    (destino / "app_urls.txt").write_text("\n".join(unicos) or "(nenhum trecho com .json encontrado)", encoding="utf-8")
    reg(f"      {len(vistos)} arquivos JS lidos; {len(unicos)} trechos com endereços .json em app_urls.txt")
