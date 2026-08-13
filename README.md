# PQC na interface E2/Open RAN

Laboratório reproduzível para avaliar IPsec clássico e híbrido pós-quântico na
interface E2. O projeto protege SCTP/E2AP com ESP em modo transporte, sem
alterar o protocolo E2, e compara três modos:

| Modo | IKE | Dataplane |
|---|---|---|
| M1 | desativado | SCTP em claro |
| M2 | AES-256-GCM, SHA-384 e X25519 | ESP/AES-256-GCM |
| M3 | M2 + ML-KEM-768 via `IKE_INTERMEDIATE` | ESP/AES-256-GCM |

## Arquitetura

```text
ric (10.10.0.1/30) ───── eth1 ───── du (10.10.0.2/30)
  Near-RT RIC / tráfego                    E2 Node / echo SCTP
  strongSwan 6.0.7                         strongSwan 6.0.7
  VICI + XFRM                              VICI + XFRM
```

A topologia usa dois containers Linux ligados diretamente pelo Containerlab.
No laboratório Containerlab, a rede de gerenciamento permanece separada do
enlace experimental `eth1`. Em um testbed, o caminho até o Collector é definido
pelo endereço informado ao Agent e pela tabela de roteamento do host.

## Componentes

- `image/`: imagem Debian reproduzível com strongSwan 6.0.7, X25519,
  ML-KEM, VICI, `kernel-netlink`, SCTP, captura e ferramentas de desempenho;
- `lab/`: topologia Containerlab definitiva;
- `strongswan/`: configurações clássicas e híbridas para RIC e DU;
- `traffic/`: cliente e servidor SCTP com sequências e relógio monotônico;
- `agent/`: observador de VICI, XFRM, CPU, memória, eventos e artefatos;
- `experiments/`: perfis, execução individual e campanhas randomizadas;
- `tests/`: gates de smoke, integração e testes unitários;

## Pré-requisitos

- Linux com XFRM, ESP e AES-GCM;
- Docker Engine e plugin Compose;
- Containerlab;
- Python 3.11 ou posterior;
- privilégios de root para criar a topologia Containerlab.

O laboratório foi validado com Docker 29.x, Containerlab 0.77.0 e host
x86-64. Em WSL2, execute primeiro o gate XFRM para confirmar que o kernel
expõe o dataplane necessário.

## Construção e validação da imagem

Os fluxos completos estão organizados no `Makefile`. Consulte e execute com:

```bash
make help
make setup
make build
make test
make image-validate
make all-modes
```

Os alvos `m1`, `m2`, `m3`, `all-modes` e `campaign` sempre usam o Collector e
os Agents gRPC. Variáveis como `RUN_ID` e `KIND` podem ser passadas diretamente
ao Make; os exemplos completos estão em `experiments/README.md`.

```bash
./image/build.sh
./image/validate.sh
```

A imagem-base é fixada por digest e o código-fonte do strongSwan por versão e
SHA-256. A validação exige X25519, ML-KEM-768, VICI e `kernel-netlink`, gera
inventário de componentes e SBOM CycloneDX e verifica o histórico contra
credenciais incorporadas.

## Execuções individuais

```bash
sudo ./experiments/run.sh m1
sudo ./tests/integration/run-m2.sh
sudo ./tests/integration/run-m3.sh
```

M2 valida IKE/CHILD SAs clássicas, ESP e rekeys. M3 também exige
`IKE_INTERMEDIATE`, ML-KEM-768 e executa um teste negativo contra peer clássico
que deve terminar com `NO_PROPOSAL_CHOSEN`, impedindo downgrade silencioso.

Para validar o agente e todos os artefatos de uma execução M3:

```bash
sudo ./tests/integration/run-agent.sh m3
```

## Campanha controlada

Piloto mínimo com dez repetições por tratamento:

```bash
sudo ./experiments/campaign.py \
  --repetitions 10 \
  --seed 20260813 \
  --campaign-id piloto-local-01
```

A campanha separa tráfego em regime (`M1/M2/M3`) de estabelecimento e rekey
(`M2/M3`), randomiza a ordem com seed registrada e pode ser retomada usando o
mesmo `campaign-id`. O relatório calcula média, mediana, percentis, dispersão,
intervalo de confiança e contrastes pareados M1→M2 e M2→M3.

## Artefatos

Cada execução produz em `results/experiments/<run-id>/`:

```text
manifest.json       modo, versões, imagem, host, topologia e relógios
events.jsonl        eventos UTC e monotônicos
metrics.csv         CPU, memória, VICI e contadores XFRM
summary.json        checks e métricas derivadas
capture.pcap        captura exclusiva da interface experimental
*-charon.log        logs IKE sem chaves
```

`results/` é ignorado pelo Git. PSKs são aleatórios e efêmeros, removidos antes
da coleta, e as chaves exibidas por `ip -s xfrm` são redigidas.

## Resultados locais

Uma campanha local de 20 repetições por tratamento completou 100/100
execuções. O custo mais consistente do modo híbrido foi a troca
`IKE_INTERMEDIATE` com ML-KEM-768, em aproximadamente 2,3 ms. Não houve
evidência clara de aumento do RTT SCTP em regime entre M2 e M3.

Esses números são preliminares: containers compartilham o kernel e o enlace
virtual não representa congestionamento, rádio ou transporte físico. A
validação final deve ser repetida no testbed OpenRAN@Brasil com recursos
reservados, MTU conhecida, retransmissões SCTP e métricas E2 reais.

## Testes locais

```bash
python3 -m unittest discover -s agent/tests -v
python3 -m unittest discover -s tests/unit -v
```

Para três ciclos completos do baseline M1:

```bash
sudo ./tests/smoke/run-cycles.sh
```

## Distributed Telemetry Architecture

Para operação em hosts ou VMs distintos, cada endpoint executa seu próprio
Agent e envia eventos e métricas ao endereço configurado em `--collector`:

```text
                       rede de gerenciamento
                    +-------------------------+
                    |  Metrics Collector      |
                    |  gRPC :50051            |
                    +-----------+-------------+
                           /           \
                     gRPC /             \ gRPC
                         /               \
              Agent RIC                   Agent DU
            VICI/XFRM/CPU              VICI/XFRM/CPU
                 |                          |
                 +---- eth1: E2/SCTP -------+
                       IPsec/ESP M2/M3
```

Cada mensagem contém `run_id`, `node_id`, timestamp e `sequence_number`.
Ao iniciar, cada Agent envia uma mensagem `NODE_METADATA` com modo, versões do
kernel, Agent e strongSwan, intervalo de amostragem e estado do Collector. O
Collector usa essa mensagem para preencher o `manifest.json` central.
Antes do envio ela é persistida em um spool SQLite local. O Agent abre streams
client-streaming em lotes; ao terminar cada lote, recebe um ACK cumulativo que
confirma o recebimento e informa gaps. O RPC não envia ACK por mensagem nem é
bidirecional. Quedas do Collector não
interrompem o experimento e os itens pendentes são reenviados após reconexão.
O Collector deduplica pela chave `run_id + node_id + sequence_number` e salva
dados em `runs/<run_id>/<node_id>/`.

Instale os comandos em um ambiente virtual:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

Inicie o Collector local sem TLS apenas para desenvolvimento:

```bash
.venv/bin/pqc-collector serve \
  --listen 0.0.0.0:50051 \
  --data-dir ./runs \
  --insecure
```

Em terminais separados, inicie os Agents com o mesmo `run_id`:

```bash
sudo .venv/bin/pqc-agent --node-id ric --run-id test-m3-001 --mode M3 \
  --collector 127.0.0.1:50051 --insecure --sample-interval 1.0

sudo .venv/bin/pqc-agent --node-id du --run-id test-m3-001 --mode M3 \
  --collector 127.0.0.1:50051 --insecure --sample-interval 1.0
```

O modo desconectado mantém tudo no spool:

```bash
sudo .venv/bin/pqc-agent --node-id ric --run-id test-m3-001 \
  --mode M3 --offline --sample-interval 1.0
```

Os dois Agents são obrigatórios durante uma execução/campanha Containerlab:

```bash
make m3
```

O nó `collector` participa apenas da rede de gerenciamento padrão do
Containerlab. O único enlace experimental declarado continua sendo
`ric:eth1 ↔ du:eth1`, portanto gRPC não atravessa o caminho SCTP/IPsec.
Como gate runtime, o PCAP capturado em `eth1` é filtrado por `tcp.port == 50051`;
qualquer pacote encontrado reprova a execução.

O Agent não contém nomes de interface, topologia ou endereçamento de
gerenciamento hardcoded. Ele recebe apenas o destino `host:porta`; o roteamento
do sistema operacional escolhe a interface de saída. Por exemplo, no testbed:

```bash
sudo .venv/bin/pqc-agent \
  --node-id ric \
  --run-id rnp-e2-m3-001 \
  --mode M3 \
  --collector 192.168.50.10:50051 \
  --insecure
```

No OpenRAN@Brasil deve ser utilizada a infraestrutura de gerenciamento
disponibilizada pela RNP. A implementação não pressupõe que essa infraestrutura
use `eth0`, `management0`, `ens5`, uma sub-rede específica ou a mesma topologia
do laboratório local.

Produção deve omitir `--insecure`: o Collector aceita `--cert`, `--key` e
`--ca` para mTLS, e o Agent aceita `--ca`, `--cert` e `--key`. Nenhum
certificado é hardcoded. PCAPs permanecem locais e nunca trafegam no stream.

O PQC Experiment Agent não implementa ML-KEM, não negocia chaves e não recebe
material secreto das SAs. Essas funções permanecem no strongSwan/IKEv2 e no
Linux XFRM.
