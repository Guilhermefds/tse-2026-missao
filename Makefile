PY ?= python3

.PHONY: instalar dados processar conferir analise tudo exemplo teste

instalar:            ## instala as dependências
	$(PY) -m pip install -r requirements.txt

dados:               ## baixa os arquivos do TSE (dados abertos; se indisponíveis, API de divulgação)
	$(PY) -m missao baixar

processar:           ## normaliza os brutos em parquet
	$(PY) -m missao processar

conferir:            ## checagens de sanidade dos dados processados
	$(PY) -m missao conferir

analise:             ## calcula as métricas e gera relatório, planilha, CSVs e RESUMO.md em saida/
	$(PY) -m missao analisar

tudo:                ## baixar + processar + conferir + analisar
	$(PY) -m missao tudo

exemplo:             ## roda o pipeline inteiro com dados SINTÉTICOS (sem rede) em saida/exemplo_sintetico/
	$(PY) scripts/gerar_sintetico.py
	$(PY) -m missao processar --dados dados/sintetico
	$(PY) -m missao analisar --dados dados/sintetico --saida saida/exemplo_sintetico --sintetico

teste:               ## testes automatizados (usam dados sintéticos)
	$(PY) -m pytest -q tests
