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
A rede de gerenciamento permanece separada do enlace experimental `eth1`.

## Componentes

- `image/`: imagem Debian reproduzível com strongSwan 6.0.7, X25519,
  ML-KEM, VICI, `kernel-netlink`, SCTP, captura e ferramentas de desempenho;
- `lab/`: topologia Containerlab definitiva;
- `strongswan/`: configurações clássicas e híbridas para RIC e DU;
- `traffic/`: cliente e servidor SCTP com sequências e relógio monotônico;
- `agent/`: observador de VICI, XFRM, CPU, memória, eventos e artefatos;
- `experiments/`: perfis, execução individual e campanhas randomizadas;
- `tests/`: gates de smoke, integração e testes unitários;
- `phase0/`: gate inicial isolado para diagnosticar suporte XFRM do host.

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

