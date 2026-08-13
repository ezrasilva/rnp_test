# Experimentos e campanhas

Execução individual:

```bash
sudo ./experiments/run.sh m1
sudo ./experiments/run.sh m2
sudo ./experiments/run.sh m3
```

Piloto controlado (10 repetições por tratamento, 50 execuções no total):

```bash
sudo ./experiments/campaign.py --repetitions 10 --seed 20260813
```

A agenda é gravada antes da primeira execução e randomizada pela seed. Os
tratamentos de tráfego (`M1/M2/M3`) são separados dos tratamentos de
estabelecimento/rekey (`M2/M3`). A campanha pode ser retomada com o mesmo
`--campaign-id`: execuções aprovadas são verificadas e ignoradas.

O resumo apresenta mediana, percentis, dispersão, intervalo de confiança
normal aproximado do piloto e o número recomendado de repetições para a
precisão relativa declarada. Esses resultados são preliminares e locais.

