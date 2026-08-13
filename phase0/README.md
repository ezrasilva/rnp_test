# Fase 0 — gate do dataplane XFRM

Este gate cria dois containers em namespaces de rede distintos, instala duas SAs
ESP/AES-GCM em modo transporte e comprova que o tráfego ICMP cruza o enlace
protegido.

## Pré-requisitos

- Docker Engine com o plugin Compose;
- kernel do host com XFRM, ESP e AES-GCM;
- permissão para acessar o daemon Docker.

## Execução

```bash
./phase0/run.sh
```

O script falha imediatamente quando XFRM não está acessível. Quando o gate
passa, as evidências ficam em `results/phase0/<run-id>/`: captura PCAP, saída
dos contadores/policies XFRM, ping, log integral e resumo JSON.

Por padrão os containers são removidos ao final. Para mantê-los para inspeção:

```bash
PHASE0_KEEP_LAB=1 ./phase0/run.sh
docker compose -f phase0/compose.yml down
```

As chaves são constantes e públicas de propósito: estas SAs são efêmeras e
servem exclusivamente para validar o dataplane, não para proteger dados reais.

