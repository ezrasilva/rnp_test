# Experimentos e campanhas

## Execução com Make

Use `make help` para consultar todos os alvos. O fluxo recomendado é:

```bash
make setup
make build
make test
make image-validate
make all-modes
```

Os experimentos que implantam o Containerlab usam `sudo` automaticamente. Se
o Make já estiver sendo executado como root, passe `SUDO=`. Os principais alvos
são:

```bash
make m1
make m2
make m3
make cycles
make distributed-all
```

É possível controlar uma execução sem editar scripts:

```bash
make m3 RUN_ID=rnp-e2-m3-001 KIND=combined TELEMETRY=1
```

Em `all-modes` ou `distributed-all`, um `RUN_ID=ensaio-001` informado pelo
usuário gera `ensaio-001-m1`, `ensaio-001-m2` e `ensaio-001-m3`, evitando que
os artefatos dos modos compartilhem a mesma pasta.

`KIND` aceita `combined`, `steady` ou `establishment` (este último não se aplica
ao M1). Nos alvos Make, o Collector e os Agents distribuídos no RIC e DU são
habilitados por padrão. Use `TELEMETRY=0` somente para reproduzir o fluxo
centralizado legado.

Para planejar, executar ou retomar uma campanha:

```bash
make campaign-plan REPS=10 SEED=20260813 CAMPAIGN_ID=piloto-001
make campaign REPS=10 SEED=20260813 CAMPAIGN_ID=piloto-001
```

Reutilize o mesmo `CAMPAIGN_ID` para retomar uma campanha interrompida.

## Execução direta

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

Defina `DISTRIBUTED_TELEMETRY=1` para que cada repetição passe o mesmo
`RUN_ID` e `MODE` aos Agents locais de RIC e DU. Sem a variável, o monitor
centralizado existente continua sendo usado, preservando campanhas anteriores.

O resumo apresenta mediana, percentis, dispersão, intervalo de confiança
normal aproximado do piloto e o número recomendado de repetições para a
precisão relativa declarada. Esses resultados são preliminares e locais.
