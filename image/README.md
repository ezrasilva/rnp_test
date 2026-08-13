# Imagem dos endpoints OpenRAN PQC

A mesma imagem é usada pelo RIC e pelo DU. Ela contém strongSwan 6.0.7,
`charon`, `swanctl`, VICI, `kernel-netlink`, X25519, ML-KEM, ferramentas de rede,
SCTP e Python.

```bash
./image/build.sh
./image/validate.sh
```

O build fixa a imagem-base por digest e valida o SHA-256 do código-fonte do
strongSwan antes de compilá-lo. A validação executa a imagem como os dois
endpoints lógicos e grava manifesto, inventário de componentes e saídas dos
algoritmos em `results/image/<run-id>/`.

Nenhuma credencial é adicionada à imagem. Configurações e segredos de cada
execução serão montados em tempo de execução.

