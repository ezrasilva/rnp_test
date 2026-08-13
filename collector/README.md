# PQC Metrics Collector

Serviço gRPC independente que recebe streams dos agentes RIC/DU, deduplica por
`run_id + node_id + sequence_number` e persiste dados legíveis em `runs/`.
O primeiro lote de cada Agent inclui `NODE_METADATA`, usado para completar o
manifesto central com modo, versões por nó, versão do strongSwan e intervalo de
amostragem.

```bash
pqc-collector serve --listen 0.0.0.0:50051 --data-dir ./runs --insecure
```

Sem `--insecure`, use `--cert`, `--key` e opcionalmente `--ca` para exigir
certificados de cliente (mTLS). Certificados nunca são incorporados ao código.
