"""Download dos dados do TSE.

Fonte principal: Portal de Dados Abertos (CDN) — arquivos .zip com CSVs por UF.
Fonte alternativa: API de divulgação (resultados.tse.jus.br), usada quando os
arquivos consolidados do ano ainda não foram publicados no portal (o que é comum
nos primeiros dias após a eleição).
"""
from __future__ import annotations

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


def descobrir_eleicoes(cfg: Config, cliente: httpx.Client) -> list[dict]:
    """Lê comum/config/ele-c.json e devolve as eleições ordinárias do ciclo `ele{ano}`.

    O formato do arquivo varia levemente entre ciclos; por isso a busca é tolerante:
    procura qualquer dict com chave 'cd' cujo contexto mencione o ciclo/ano.
    """
    dados = _get_json(cliente, f"{cfg.url_divulgacao}/comum/config/ele-c.json")
    achadas: list[dict] = []

    def _varrer(no, ciclo_atual=None):
        if isinstance(no, dict):
            ciclo = no.get("c") or no.get("cdpr") or ciclo_atual
            texto = json.dumps({k: v for k, v in no.items() if not isinstance(v, (list, dict))})
            if "cd" in no and ("nm" in no or "t" in no) and (str(cfg.ano) in texto or str(cfg.ano) in str(ciclo)):
                achadas.append({**{k: v for k, v in no.items() if not isinstance(v, (list, dict))},
                                "ciclo": ciclo})
            for v in no.values():
                _varrer(v, ciclo)
        elif isinstance(no, list):
            for v in no:
                _varrer(v, ciclo_atual)

    _varrer(dados)
    return achadas


def _cargos_da_eleicao(cfg: Config, cliente: httpx.Client, ciclo: str, ele: str, e6: str, mun_cfg: dict) -> list[int]:
    """Sonda um município (a capital de SP, ou o primeiro disponível) para saber quais cargos a eleição tem."""
    ufs = {u["cd"].lower(): u for u in mun_cfg.get("abr", [])}
    uf = ufs.get("sp") or next((u for k, u in ufs.items() if k != "zz"), None)
    if not uf or not uf.get("mu"):
        return CARGOS_API
    sg, mun = uf["cd"].lower(), uf["mu"][0]["cd"]
    existentes = []
    for cargo in CARGOS_API:
        if cargo == DEP_DISTRITAL:
            existentes.append(cargo)  # só existe no DF; mantém se a eleição tiver dep. estadual
            continue
        url = f"{cfg.url_divulgacao}/{ciclo}/{ele}/dados-simplificados/{sg}/{sg}{mun}-c{cargo:04d}-e{e6}-r.json"
        if cliente.get(url).status_code == 200:
            existentes.append(cargo)
    if DEP_ESTADUAL not in existentes and DEP_DISTRITAL in existentes:
        existentes.remove(DEP_DISTRITAL)
    return existentes


def baixar_api(cfg: Config, eleicoes: list[str] | None = None, max_workers: int = 16) -> Path:
    """Baixa os resultados por município da API de divulgação (JSON 'dados-simplificados').

    Salva em dados/brutos/api/{eleicao}/{uf}/{uf}{mun}-c{cargo}-e{eleicao}-r.json
    `eleicoes`: códigos (ex.: ["620", "621"]). Se omitido, descobre pelo ele-c.json.
    """
    ciclo = f"ele{cfg.ano}"
    base = cfg.dir_brutos / "api"
    with _cliente(timeout=60) as cliente:
        if not eleicoes:
            achadas = descobrir_eleicoes(cfg, cliente)
            (base / "eleicoes_descobertas.json").parent.mkdir(parents=True, exist_ok=True)
            (base / "eleicoes_descobertas.json").write_text(json.dumps(achadas, ensure_ascii=False, indent=1))
            eleicoes = sorted({str(int(e["cd"])) for e in achadas
                               if str(e.get("t", e.get("tp", "1"))) in ("1", str(cfg.turno))})
            print(f"[api] eleições descobertas: {eleicoes}")
        tarefas = []
        for ele in eleicoes:
            e6 = f"{int(ele):06d}"
            url_cfg = f"{cfg.url_divulgacao}/{ciclo}/{ele}/config/mun-e{e6}-cm.json"
            try:
                mun_cfg = _get_json(cliente, url_cfg)
            except httpx.HTTPStatusError:
                print(f"[api] sem config de municípios para eleição {ele}")
                continue
            destino_cfg = base / ele / f"mun-e{e6}-cm.json"
            destino_cfg.parent.mkdir(parents=True, exist_ok=True)
            destino_cfg.write_text(json.dumps(mun_cfg, ensure_ascii=False))
            cargos = _cargos_da_eleicao(cfg, cliente, ciclo, ele, e6, mun_cfg)
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
                        nome = f"{sg}{mun['cd']}-c{cargo:04d}-e{e6}-r.json"
                        url = f"{cfg.url_divulgacao}/{ciclo}/{ele}/dados-simplificados/{sg}/{nome}"
                        tarefas.append((url, base / ele / sg / nome))

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
                    destino.write_bytes(r.content)
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
