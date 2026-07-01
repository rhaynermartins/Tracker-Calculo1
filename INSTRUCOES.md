# Programa de Análise da Velocidade do Carrinho

Este programa em Python lê arquivos CSV exportados pelo Tracker e calcula a velocidade do carrinho ao passar pelo ponto de referência P.

## Objetivo

O objetivo do programa é estimar a velocidade instantânea do carrinho usando os dados experimentais de posição e tempo extraídos do vídeo.

O programa realiza três etapas principais:

1. Lê os dados do arquivo CSV.
2. Calcula velocidades médias próximas ao ponto P.
3. Estima a velocidade instantânea usando a ideia de limite.

## Como usar

Coloque o arquivo Python na mesma pasta dos arquivos CSV exportados pelo Tracker.

Depois, execute no terminal:

```bash
python3 programa_carrinho_tracker.py dados.csv --ponto-p 1.10 --unidade-pos m