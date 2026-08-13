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
