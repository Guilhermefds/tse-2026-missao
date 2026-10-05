# Raio-X Missão 2026

Análise dos resultados do TSE para o partido **Missão (14)** nas Eleições Gerais de 2026, 1º turno: Renan Santos para Presidente e as chapas de Deputado Federal, Deputado Estadual/Distrital, Senado e Governo.

```bash
make instalar      # dependências (Python 3.10+)
make tudo          # baixa do TSE, processa, confere e gera saida/
make teste         # testes com dados sintéticos (não precisa de rede)
make exemplo       # relatório de demonstração com dados SINTÉTICOS em saida/exemplo_sintetico/
```

## Perguntas respondidas

| Pergunta | Onde está | Como é medido |
|---|---|---|
| Cidades com maiores distorções | Relatório §04, abas `distorcao_*` | % suavizado por encolhimento bayesiano (corrige o ruído de cidades pequenas) e z robusto (mediana/MAD) frente à própria UF; diferença entre o % do presidenciável e o da chapa federal |
| Maiores fatos discrepantes | Relatório "Destaques", aba `fatos` | Lista automática: maior %, maior votação, pódio, cidades sem voto, distorções extremas, capitais, UFs, exterior, zonas, deputados acima do presidente, QE por um triz |
| Maiores cidades em percentual | §03, abas `top_pct*`, `podio`, `por_porte` | Rankings com piso de eleitores (padrão 5 mil), top 10 por porte, top 5 por UF, municípios em 1º/2º, piores entre as grandes |
| Onde acertamos, onde erramos | §05 e §08, abas `acertos_*`, `erros_*`, `esperado_*`, `quociente` | Modelo GLM binomial com efeito fixo de UF, porte, capital, abstenção, votação de 2022 e perfil do eleitorado; resíduo em votos = acerto/erro. Quociente eleitoral: quanto faltou para eleger, e que fração do voto do presidenciável a chapa precisaria reter |
| Guarda-chuva do presidente frente aos demais | §06, abas `guarda_chuva_*` | Votos da chapa ÷ votos do presidenciável (DF, DE, legenda), retenção, correlação e elasticidade municipal, quintis; mesma métrica para todos os presidenciáveis (partido e federação) |
| Cidades onde deputados tiveram mais votos que Renan | §07, abas `df_maior_que_pres`, `de_maior_que_pres`, `candidato_maior_que_pres`, `candidatos_puxadores_locais` | Chapa (nominal + legenda) e candidatos individuais acima do presidenciável, por município, UF e porte |

Extras: desempenho individual de cada candidato (votos, % da UF, reduto, concentração HHI, correlação com o mapa do Renan, % do QE), zonas eleitorais (dentro das capitais), exterior e origem geográfica dos votos em relação a 2022.

## Saídas (`saida/`)

- `relatorio.html` — relatório autocontido com gráficos e tabelas ordenáveis/filtráveis.
- `analise_completa.xlsx` — todas as tabelas, uma por aba, incluindo `base_municipal` (uma linha por município, ~80 colunas).
- `tabelas/*.csv` — as mesmas tabelas em CSV (`;`, decimal `,`, UTF-8 com BOM para abrir no Excel).
- `RESUMO.md` — destaques e principais tabelas em texto.

## Dados

Fonte principal: [Portal de Dados Abertos do TSE](https://dadosabertos.tse.jus.br/) (`cdn.tse.jus.br/estatistica/sead/odsele/`):

| Arquivo | Uso |
|---|---|
| `votacao_candidato_munzona_2026` | votos por candidato × município × zona |
| `votacao_partido_munzona_2026` | votos nominais e de legenda por partido |
| `detalhe_votacao_munzona_2026` | aptos, comparecimento, abstenção, brancos, nulos |
| `consulta_cand_2026` | cadastro e situação dos candidatos |
| `perfil_eleitorado_2026` | sexo, idade e escolaridade do eleitorado por município |
| `votacao_candidato_munzona_2022` | base de comparação (voto esperado e origem dos votos) |

Logo após a eleição o TSE publica os consolidados de 2026 **só com os cabeçalhos** (zips de poucos KB) e os resultados ficam apenas na API de divulgação (`resultados.tse.jus.br`). O pipeline detecta zips sem dados e usa a API; a sigla do partido, que a API não traz, vem do `consulta_cand`. Nessa fonte não há votação por zona eleitoral. `python -m missao baixar` tenta o portal e, se o ano ainda não estiver publicado, cai para a API (`--fonte api` força). O parser da API é tolerante a mudanças de formato, mas confira o resultado com `make conferir`. Se algo não bater, `python -m missao diagnosticar` mostra o layout de cada zip (CSVs, colunas, linhas por cargo) e o que foi extraído.

**Ambiente na nuvem do Claude Code:** os domínios `cdn.tse.jus.br`, `resultados.tse.jus.br` e `dadosabertos.tse.jus.br` precisam estar liberados em *Network access* do ambiente. Localmente não há restrição.

## Metodologia

- **Válidos:** Presidente = votos nominais; proporcionais = nominal + legenda. Percentuais sempre sobre válidos do cargo.
- **Chapa:** todos os candidatos do partido no cargo + votos de legenda.
- **% suavizado:** beta-binomial por UF, prior estimado por método dos momentos: `(votos + α) / (válidos + α + β)`.
- **z robusto:** `(logit(% suavizado) − mediana_UF) / (1,4826 × MAD_UF)`; |z| ≥ 3 = distorção forte.
- **Esperado:** GLM binomial (logit) ponderado por válidos, covariáveis padronizadas, efeito fixo de UF; covariáveis quase colineares são descartadas automaticamente (a maior fatia de 2022 vira referência).
- **Quociente eleitoral:** válidos ÷ vagas, arredondamento do TSE (fração > 0,5 sobe). Vagas = eleitos encontrados nos dados (ou a distribuição oficial, se ainda não houver totalização).
- **Origem dos votos:** regressão ecológica com coeficientes em [0, 1]. Indica associação geográfica, não comportamento individual.
- **Correlações** são ponderadas pelos válidos do município. **Elasticidade** = inclinação de log(% chapa) em log(% presidente).

## Código

```
missao/
  config.py      parâmetros (config.yaml), códigos de cargo, regiões, capitais
  baixar.py      download (CDN de dados abertos + API de divulgação)
  carregar.py    leitura dos CSVs/JSON do TSE e normalização em parquet
  metricas.py    todas as análises
  relatorio.py   HTML, XLSX, CSVs e RESUMO.md
  diagnostico.py inspeção dos zips do TSE e das tabelas processadas
  __main__.py    CLI: python -m missao {baixar,processar,conferir,analisar,diagnosticar,tudo}
scripts/gerar_sintetico.py   dados sintéticos no formato exato do TSE (testes e demonstração)
tests/                       testes ponta a ponta
config.yaml                  partido, número do presidenciável, limiares
```

Para analisar outro partido ou candidato, altere `config.yaml` (`partido.numero`, `presidente.numero`).
