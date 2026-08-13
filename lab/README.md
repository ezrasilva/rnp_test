# Laboratório OpenRAN PQC

A topologia contém os endpoints `ric` e `du`, ligados diretamente pelas
interfaces `eth1` (`10.10.0.1/30` e `10.10.0.2/30`). A rede de gerenciamento do
Containerlab permanece separada e não é usada pelos testes de saúde.

No ambiente local, o nó `collector` é ligado somente à rede de gerenciamento
automática do Containerlab e escuta gRPC na porta 50051. Ele não possui
interface no enlace experimental.

Essa rede reproduz localmente a separação prevista, mas não define a topologia
do testbed. Fora do Containerlab, o Agent conecta ao destino passado em
`--collector`, e a tabela de roteamento do host escolhe a interface apropriada.

Execute o baseline M1 uma vez:

```bash
sudo ./experiments/run.sh m1
```

Execute o modo clássico M2 com IKEv2/X25519 e ESP/AES-GCM:

```bash
sudo ./tests/integration/run-m2.sh
```

O PSK de M2 é criado aleatoriamente em cada execução, carregado nos daemons e
removido antes da coleta. Os dumps XFRM têm as chaves de tráfego redigidas.

Execute o modo híbrido M3 com X25519 + ML-KEM-768:

```bash
sudo ./tests/integration/run-m3.sh
```

Execute os três ciclos exigidos pelo gate:

```bash
sudo ./tests/smoke/run-cycles.sh
```

Em um host onde `sudo` sem senha esteja configurado para o Containerlab, os
scripts também podem ser executados pelo usuário normal e elevam apenas o
comando `containerlab`.
