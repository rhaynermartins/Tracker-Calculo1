# Programa de Análise da Velocidade do Carrinho

Este programa em Python lê arquivos CSV exportados pelo Tracker e calcula a velocidade do carrinho ao passar pelo ponto de referência P.

## Objetivo

O objetivo é estimar a velocidade instantânea do carrinho usando os dados experimentais de posição e tempo extraídos do vídeo.

O programa realiza três etapas principais:

1. Lê os dados do arquivo CSV.
2. Calcula velocidades médias próximas ao ponto P.
3. Estima a velocidade instantânea usando a ideia de limite.

## Como usar

Coloque o arquivo Python na mesma pasta dos arquivos CSV exportados pelo Tracker.

Depois, execute no terminal:

```bash
python3 programa_carrinho_tracker.py dados.csv --ponto-p 1.10 --unidade-pos m
```

Caso o arquivo CSV esteja com as posições em centímetros, o comando deve ser:

```bash
python3 programa_carrinho_tracker.py dados.csv --ponto-p 100 --unidade-pos cm
```

Se houver arquivos diferentes para baixa, média e alta velocidade, é possível executar o programa com vários CSVs ao mesmo tempo:

```bash
python3 programa_carrinho_tracker.py baixa.csv media.csv alta.csv --ponto-p 100 --unidade-pos cm
```

## Relação com o conteúdo de Cálculo

O programa aplica o conceito de velocidade média e velocidade instantânea.
A velocidade média é calculada em um intervalo de tempo:

```bash
v média = Δs / Δt
```

Já a velocidade instantânea é estimada quando esse intervalo fica cada vez menor, aproximando-se de zero. Essa ideia representa o conceito de limite estudado em Cálculo Diferencial.

Assim, o programa transforma os dados experimentais do Tracker em uma estimativa numérica da velocidade instantânea do carrinho.