# PQC Experiment Agent

O agente observa o experimento sem implementar criptografia. Ele usa `swanctl`
(VICI), `ip -s xfrm`, estatísticas do runtime e os eventos da aplicação para
produzir `manifest.json`, `events.jsonl`, `metrics.csv` e métricas derivadas no
`summary.json`.

O runner principal inicia o monitor automaticamente:

```bash
sudo ./experiments/run.sh m1
sudo ./experiments/run.sh m2
sudo ./experiments/run.sh m3
```

Para executar e validar formalmente uma execução autossuficiente (M3 por
padrão, ou `m1`/`m2` como argumento):

```bash
sudo ./tests/integration/run-agent.sh m3
```

Testes unitários, sem dependências externas:

```bash
python3 -m unittest discover -s agent/tests
```

## Agente distribuído

```bash
pqc-agent run --node-id ric --run-id run-001 --mode M3 \
  --collector collector.example:50051 --ca ca.pem --cert ric.pem --key ric.key
```

Use `--offline` no lugar de `--collector` para coleta sem rede. O spool padrão
é `/var/lib/pqc-agent/spool/<run_id>/<node_id>/spool.db` e pode ser alterado
com `--spool-dir`.

Eventos observáveis nesta versão:

- `IKE_SA_ESTABLISHED`, `CHILD_SA_INSTALLED` e `SA_DELETED`: derivados do
  estado VICI consultado por `swanctl` e emitidos imediatamente ao detectar
  uma transição;
- métricas XFRM e de sistema: polling periódico, por padrão a cada 1 segundo;
- a abstração também define `IKE_START`, fases `IKE_SA_INIT`, ML-KEM,
  `IKE_AUTH`, rekey e falhas para integração futura orientada a eventos.

Os timestamps internos de fases IKE não são inventados. Enquanto não houver
uma assinatura VICI/log confiável para eles no daemon, permanecem não
suportados pelo comando distribuído.
