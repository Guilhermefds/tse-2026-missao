"""Leitura de config.yaml e caminhos padrão do projeto."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent

# Códigos de cargo usados pelo TSE
PRESIDENTE, GOVERNADOR, SENADOR, DEP_FEDERAL, DEP_ESTADUAL, DEP_DISTRITAL = 1, 3, 5, 6, 7, 8
NOME_CARGO = {
    PRESIDENTE: "Presidente",
    GOVERNADOR: "Governador",
    SENADOR: "Senador",
    DEP_FEDERAL: "Deputado Federal",
    DEP_ESTADUAL: "Deputado Estadual",
    DEP_DISTRITAL: "Deputado Distrital",
}

REGIAO = {
    "AC": "Norte", "AP": "Norte", "AM": "Norte", "PA": "Norte", "RO": "Norte", "RR": "Norte", "TO": "Norte",
    "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste", "PB": "Nordeste",
    "PE": "Nordeste", "PI": "Nordeste", "RN": "Nordeste", "SE": "Nordeste",
    "DF": "Centro-Oeste", "GO": "Centro-Oeste", "MT": "Centro-Oeste", "MS": "Centro-Oeste",
    "ES": "Sudeste", "MG": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
    "PR": "Sul", "RS": "Sul", "SC": "Sul",
    "ZZ": "Exterior",
}

CAPITAIS = {
    "AC": "RIO BRANCO", "AL": "MACEIO", "AP": "MACAPA", "AM": "MANAUS", "BA": "SALVADOR",
    "CE": "FORTALEZA", "DF": "BRASILIA", "ES": "VITORIA", "GO": "GOIANIA", "MA": "SAO LUIS",
    "MT": "CUIABA", "MS": "CAMPO GRANDE", "MG": "BELO HORIZONTE", "PA": "BELEM",
    "PB": "JOAO PESSOA", "PR": "CURITIBA", "PE": "RECIFE", "PI": "TERESINA",
    "RJ": "RIO DE JANEIRO", "RN": "NATAL", "RS": "PORTO ALEGRE", "RO": "PORTO VELHO",
    "RR": "BOA VISTA", "SC": "FLORIANOPOLIS", "SP": "SAO PAULO", "SE": "ARACAJU", "TO": "PALMAS",
}


@dataclass
class Config:
    ano: int = 2026
    turno: int = 1
    ano_comparacao: int = 2022
    partido_sigla: str = "MISSAO"
    partido_numero: int = 14
    partido_nome: str = "Missão"
    presidente_numero: int = 14
    presidente_nome: str = "Renan Santos"
    referencia_2022: dict = field(default_factory=dict)
    min_eleitores_ranking: int = 5000
    clausula: dict = field(default_factory=lambda: {"pct_nacional": 2.5, "pct_uf": 1.5, "ufs_minimo": 9,
                                                    "deputados": 13})
    faixas_eleitorado: list = field(default_factory=lambda: [0, 5000, 10000, 20000, 50000, 100000,
                                                             200000, 500000, 1000000, 10**8])
    url_cdn: str = "https://cdn.tse.jus.br/estatistica/sead/odsele"
    url_divulgacao: str = "https://resultados.tse.jus.br/oficial"
    dir_dados: Path = RAIZ / "dados"
    dir_saida: Path = RAIZ / "saida"

    @property
    def dir_brutos(self) -> Path:
        return self.dir_dados / "brutos"

    @property
    def dir_processados(self) -> Path:
        return self.dir_dados / "processados"


def carregar_config(caminho: Path | str | None = None, **sobrescrever) -> Config:
    caminho = Path(caminho) if caminho else RAIZ / "config.yaml"
    bruto = yaml.safe_load(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}
    cfg = Config(
        ano=bruto.get("ano", 2026),
        turno=bruto.get("turno", 1),
        ano_comparacao=bruto.get("ano_comparacao", 2022),
        partido_sigla=bruto.get("partido", {}).get("sigla", "MISSAO"),
        partido_numero=int(bruto.get("partido", {}).get("numero", 14)),
        partido_nome=bruto.get("partido", {}).get("nome_exibicao", "Missão"),
        presidente_numero=int(bruto.get("presidente", {}).get("numero", 14)),
        presidente_nome=bruto.get("presidente", {}).get("nome_exibicao", "Renan Santos"),
        referencia_2022={int(k): v for k, v in (bruto.get("referencia_2022") or {}).items()},
        min_eleitores_ranking=int(bruto.get("min_eleitores_ranking", 5000)),
        clausula={**Config().clausula, **(bruto.get("clausula_barreira") or {})},
        faixas_eleitorado=bruto.get("faixas_eleitorado") or Config().faixas_eleitorado,
        url_cdn=bruto.get("fontes", {}).get("cdn", Config.url_cdn),
        url_divulgacao=bruto.get("fontes", {}).get("divulgacao", Config.url_divulgacao),
    )
    for chave, valor in sobrescrever.items():
        setattr(cfg, chave, Path(valor) if chave.startswith("dir_") else valor)
    return cfg
