# Plano de implementação local — PQC na interface E2/Open RAN

## 1. Decisões de arquitetura

O laboratório local será uma pré-validação funcional e uma caracterização preliminar. Os resultados de desempenho finais deverão ser obtidos no testbed OpenRAN@Brasil.

O MVP terá dois endpoints Linux ligados diretamente pelo Containerlab:

```text
ric (10.10.0.1/30) <---------- eth1 ----------> du (10.10.0.2/30)
  strongSwan/charon                                  strongSwan/charon
  cliente de tráfego/SCTP                           servidor de tráfego/SCTP
  agente experimental                               agente experimental
```

Não será usado um switch ou bridge no primeiro incremento. Um nó intermediário de rede será acrescentado somente na fase de emulação de atraso, perda e banda.

O IPsec usará modo transporte entre os endereços de `eth1`. Isso protege SCTP/IP sem alterar SCTP, E2AP ou E2SM e reproduz a decisão arquitetural do documento de proposta.

Os três modos devem manter constantes autenticação, cifra IKE, PRF, cifra ESP, topologia e carga. A única diferença entre M2 e M3 será a troca de chaves:

| Modo | IKE | ESP | Resultado esperado |
|---|---|---|---|
| M1 — baseline | desativado | desativado | tráfego IP/SCTP visível sem ESP |
| M2 — clássico | `aes256gcm16-prfsha384-x25519` | `aes256gcm16-noesn` | IKE SA e CHILD SA clássicas |
| M3 — híbrido | `aes256gcm16-prfsha384-x25519-ke1_mlkem768` | `aes256gcm16-noesn` | `IKE_INTERMEDIATE` com ML-KEM-768 e tráfego ESP |

No núcleo do experimento, a proposta ESP não terá PFS próprio. Assim, a comparação M2–M3 isola a troca adicional na IKE SA. Rekey da IKE SA e rekey da CHILD SA serão medidos separadamente; um perfil exploratório com PFS/PQC na CHILD SA só será incluído depois do experimento principal e identificado como M3-PFS.

Para o MVP local, a autenticação poderá usar PSK distinta por laboratório, montada como segredo em tempo de execução e nunca gravada nos resultados. Antes do testbed, será criado um perfil equivalente com certificados se essa for a política da RNP.

## 2. Ambiente verificado

Levantamento realizado em 12 de agosto de 2026:

- host WSL2, kernel `6.6.123.2-microsoft-standard-WSL2+`, arquitetura x86-64;
- 12 CPUs lógicas, 7,6 GiB de RAM e 2 GiB de swap;
- Docker `29.7.1`;
- Containerlab `0.77.0`;
- `iproute2 6.1.0`;
- mais de 900 GiB disponíveis no filesystem do projeto.

O WSL2 é o principal risco técnico. A consulta `ip xfrm state` feita na sessão atual não teve permissão para abrir o socket Netlink; isso não prova ausência de XFRM, pois a sessão de inspeção não possuía privilégios. O Gate 0 abaixo deverá ser executado com `sudo`/container privilegiado.

## 3. Estrutura prevista do repositório

```text
.
├── PLANO_IMPLEMENTACAO_LOCAL.md
├── lab/
│   ├── openran-pqc.clab.yml
│   └── configs/
│       ├── ric/
│       └── du/
├── image/
│   ├── Dockerfile
│   └── entrypoint.sh
├── strongswan/
│   ├── strongswan.conf
│   ├── swanctl-classical.conf
│   └── swanctl-pqc.conf
├── agent/
│   ├── pyproject.toml
│   ├── src/
│   └── tests/
├── experiments/
│   ├── profiles/
│   └── run.sh
├── traffic/
│   ├── sctp-client/
│   └── sctp-server/
├── tests/
│   ├── smoke/
│   └── integration/
├── results/                  # ignorado pelo controle de versão
└── docs/
    └── runbook.md
```

## 4. Fases e gates de implementação

### Fase 0 — provar o dataplane do host

Objetivo: eliminar cedo o risco de XFRM/IPsec no WSL2.

Entregas:

1. subir dois containers Linux mínimos em namespaces de rede diferentes, com `NET_ADMIN` e `NET_RAW`;
2. confirmar que cada container executa `ip xfrm state` e `ip xfrm policy`;
3. confirmar suporte a ESP/AES-GCM no kernel;
4. instalar manualmente uma SA XFRM efêmera ou subir um túnel clássico mínimo;
5. capturar no enlace um pacote ESP e comprovar conectividade entre os endpoints.

Critério de aceite: pacote protegido atravessa os namespaces, contadores XFRM aumentam e o tráfego em claro não aparece no enlace experimental.

Decisão de contingência: se o kernel WSL2/Docker não expuser XFRM funcional, parar a trilha de containers e executar o mesmo desenho em duas VMs Linux. `kernel-libipsec` não será usado nos ensaios principais, porque mudaria o dataplane em relação ao testbed; servirá, no máximo, para depuração funcional.

### Fase 1 — imagem reproduzível strongSwan 6.x

Objetivo: produzir uma imagem imutável, fixada por versão/digest, com as mesmas ferramentas nos dois endpoints.

Conteúdo mínimo:

- strongSwan 6.x, `charon`, `swanctl`, VICI, `kernel-netlink`, X25519 e ML-KEM;
- `iproute2`, `tcpdump`, `tshark`, `iperf3`, `ping`, ferramentas SCTP;
- Python para o agente experimental;
- `tc` para a fase de condições adversas.

Validações da imagem:

- `swanctl --version` informa a versão fixada;
- `swanctl --list-algs` contém X25519 e ML-KEM-768;
- os plugins VICI e `kernel-netlink` estão carregados;
- nenhum segredo é incorporado a uma camada da imagem;
- gerar SBOM e registrar versões/build flags em `results/<run-id>/manifest.json`.

Critério de aceite: a imagem é reconstruível e ambos os endpoints anunciam `x25519` e `mlkem768`.

### Fase 2 — topologia e M1 baseline

Objetivo: estabilizar rede, automação e tráfego sem IPsec.

Entregas:

- `openran-pqc.clab.yml` com `ric` e `du`, ligação direta em `eth1` e endereços estáticos;
- health checks independentes da rede de gerenciamento do Containerlab;
- tráfego ICMP e TCP/UDP para smoke tests;
- cliente e servidor SCTP com mensagens numeradas, timestamps monotônicos e taxa configurável;
- captura PCAP somente na interface experimental.

Critério de aceite: 100% dos smoke tests passam em três ciclos completos de deploy, execução e destroy; SCTP funciona; não há estados/policies XFRM; a captura mostra SCTP em claro.

### Fase 3 — M2 IPsec clássico

Objetivo: validar IKEv2/X25519 e ESP antes de introduzir PQC.

Entregas:

- configurações `swanctl` separadas para iniciador e respondedor;
- autenticação local constante;
- traffic selectors restritos a `10.10.0.1/32 <-> 10.10.0.2/32` e, quando estável, ao protocolo SCTP;
- comandos idempotentes para carregar credenciais, iniciar, rekey e encerrar a conexão;
- coleta de logs de `charon`, VICI e contadores XFRM.

Critério de aceite:

- proposta negociada contém X25519 e não contém ML-KEM;
- IKE SA e CHILD SA ficam `ESTABLISHED/INSTALLED`;
- SCTP continua funcional;
- a interface experimental mostra IKE e ESP, mas não o payload SCTP em claro;
- rekey controlado termina sem perda da sessão acima do limite a ser calibrado no piloto.

### Fase 4 — M3 IPsec híbrido PQC

Objetivo: alterar somente a proposta de troca de chaves e provar ML-KEM-768.

Entregas:

- proposta explícita `x25519-ke1_mlkem768` em ambos os peers;
- logs com nível suficiente para marcar início/fim de `IKE_SA_INIT`, `IKE_INTERMEDIATE`, `IKE_AUTH` e instalação da CHILD SA, sem exportar chaves;
- teste negativo em que um peer não oferece ML-KEM, para assegurar que o perfil estrito falha em vez de fazer downgrade silencioso;
- teste de rekey da IKE SA separado do rekey da CHILD SA.

Critério de aceite:

- a negociação registra X25519 como troca inicial e ML-KEM-768 como troca adicional;
- existe `IKE_INTERMEDIATE` no fluxo híbrido;
- não há fallback para M2 no perfil estrito;
- a CHILD SA protege SCTP e os contadores ESP aumentam;
- nenhum material secreto aparece nos artefatos coletados.

### Fase 5 — PQC Experiment Agent e protocolo experimental

Objetivo: tornar os resultados repetíveis e correlacionáveis.

O agente será um observador/orquestrador, não uma implementação criptográfica. Interfaces:

- VICI: estados e eventos de IKE SA/CHILD SA, início de conexão e rekey;
- Netlink/comandos `ip -s xfrm`: policies, bytes, pacotes, erros e lifetimes;
- `/proc`, cgroups ou API do runtime: CPU, RSS, carga e throttling;
- aplicação SCTP: timestamps request/response e perdas;
- rede: PCAP, RTT, jitter e throughput.

Formato de cada execução:

```text
results/<run-id>/
├── manifest.json       # modo, versões, CPU/kernel, topologia, seed e parâmetros
├── events.jsonl        # eventos monotônicos normalizados
├── metrics.csv         # séries temporais
├── summary.json        # métricas derivadas e resultado dos checks
├── ric-charon.log
├── du-charon.log
└── capture.pcapng
```

Todos os eventos terão relógio monotônico para durações e UTC para correlação externa. O manifesto registrará a resolução do relógio e o desvio observado entre endpoints.

Métricas derivadas mínimas:

- `T_IKE = t(CHILD_SA_installed) - t(IKE_start)`;
- `T_MLKEM = t(IKE_INTERMEDIATE_end) - t(IKE_INTERMEDIATE_start)`;
- duração de `IKE_SA_INIT`, `IKE_AUTH`, IKE rekey e CHILD rekey;
- CPU e memória de `charon` durante estabelecimento e rekey;
- bytes/pacotes ESP, overhead, RTT e throughput;
- latência e sucesso das operações SCTP/E2.

Critério de aceite: uma única ordem de execução gera M1, M2 ou M3, valida o modo realmente negociado e produz um diretório autossuficiente sem segredos.

### Fase 6 — campanha local controlada

Objetivo: obter caracterização preliminar sem confundir efeitos de ordem ou aquecimento.

Procedimento:

1. executar um piloto de pelo menos 10 repetições por modo para estimar variância e calibrar timeouts;
2. definir o número final de repetições a partir da precisão desejada para o intervalo de confiança, registrando a regra antes da campanha;
3. randomizar a ordem M1/M2/M3 com seed registrada;
4. separar ensaios de estabelecimento/rekey dos ensaios de tráfego em regime;
5. recriar SAs entre repetições e verificar que o estado anterior foi removido;
6. manter CPU allocation, carga, MTU, imagem, topologia e carga de tráfego constantes;
7. relatar mediana, percentis, dispersão e intervalo de confiança, além da média;
8. comparar M1–M2 para custo do IPsec e M2–M3 para custo incremental PQC.

Critério de aceite: todas as execuções têm manifesto válido, checks de integridade, modo confirmado por evidência e taxa de falha explicada. A campanha local será rotulada como preliminar.

### Fase 7 — SCTP/E2 e condições adversas

Esta fase tem dois incrementos independentes:

1. substituir o gerador SCTP sintético por Near-RT RIC/E2 Node reais, mantendo o mesmo IPsec e o mesmo agente;
2. inserir um nó `netem` entre `ric` e `du` para perfis de atraso, jitter, perda e limitação de banda.

Perfis de rede deverão ser arquivos versionados, aplicados simetricamente ou assimetricamente de forma explícita. Cada perfil será validado sem IPsec antes de repetir M1/M2/M3. Os valores concretos serão definidos após o baseline e, idealmente, alinhados com as capacidades do domínio P4 da RNP.

Critério de aceite: operações E2/SCTP permanecem observáveis e cada condição de rede medida corresponde ao perfil solicitado dentro de uma tolerância declarada.

## 5. Ordem de execução recomendada

| Marco | Resultado | Dependência |
|---|---|---|
| G0 | XFRM/ESP provado no WSL2 ou decisão por VMs | nenhuma |
| G1 | imagem strongSwan com X25519 e ML-KEM-768 | G0 |
| G2 | M1/SCTP reproduzível | G1 |
| G3 | M2/X25519 protegido por ESP | G2 |
| G4 | M3/X25519+ML-KEM-768 sem downgrade | G3 |
| G5 | agente e artefatos automatizados | G4 |
| G6 | campanha preliminar M1/M2/M3 | G5 |
| G7 | E2 real e/ou condições adversas | G6 |

O primeiro ciclo útil termina em G4. G5 e G6 transformam o protótipo em experimento científico reproduzível. G7 prepara a migração para a RNP.

## 6. Definição de pronto para levar ao testbed

O laboratório estará pronto para portabilidade quando:

- M1, M2 e M3 forem selecionáveis sem editar arquivos manualmente;
- a evidência de negociação distinguir inequivocamente X25519 de X25519 + ML-KEM-768;
- SCTP funcionar nos três modos;
- o agente produzir métricas e manifestos completos sem coletar chaves;
- deploy, teste e teardown forem idempotentes;
- houver um runbook para mapear IPs, interfaces, credenciais e endpoints da RNP;
- limitações do WSL2 e dos containers estiverem separadas dos resultados criptográficos;
- a imagem e todas as dependências estiverem fixadas por versão/digest;
- os parâmetros ainda dependentes da RNP estiverem listados: RIC/E2 Node, privilégios, MTU, política de autenticação, observabilidade, P4 e janela de reserva.

## 7. Riscos e mitigação

| Risco | Impacto | Mitigação |
|---|---|---|
| XFRM indisponível no WSL2 | bloqueia IPsec de kernel | Gate 0; migrar para duas VMs Linux |
| imagem strongSwan sem plugin ML-KEM | M3 não negocia | fixar versão/build e validar `--list-algs` |
| fallback silencioso para clássico | invalida M3 | proposta estrita e teste negativo de downgrade |
| mistura de IKE rekey e CHILD rekey | atribuição errada de custo | ensaios e timestamps separados |
| recursos compartilhados dos containers | viés de desempenho | CPU/memória registradas, randomização e classificação como preliminar |
| relógios não correlacionados | tempos incorretos | relógio monotônico por endpoint e calibração de offset |
| MTU/fragmentação por mensagens IKE maiores | retransmissões e viés | registrar MTU, PCAP e fragmentação IKE; testar explicitamente |
| segredos em logs/PCAP/manifestos | exposição indevida | logs sem key material, mounts de segredo e auditoria automática de artefatos |

## 8. Referências técnicas oficiais

- strongSwan 6.0 — propostas e múltiplas trocas: https://docs.strongswan.org/docs/latest/config/proposals.html
- strongSwan — containers, kernel IPsec e `CAP_NET_ADMIN`: https://docs.strongswan.org/docs/latest/howtos/cloudPlatforms.html
- strongSwan — namespaces de rede: https://docs.strongswan.org/docs/latest/howtos/nameSpaces.html
- Containerlab — nós Linux: https://containerlab.dev/manual/kinds/linux/
- Containerlab — capacidades e sysctls de nós: https://containerlab.dev/manual/nodes/
- RFC 9370 — Multiple Key Exchanges in IKEv2: https://www.rfc-editor.org/rfc/rfc9370.html

