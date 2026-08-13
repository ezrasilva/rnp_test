SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help
.NOTPARALLEL: m1 m2 m3 all-modes distributed-all cycles campaign

VENV ?= .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
VENV_STAMP := $(VENV)/.openran-pqc-installed
SUDO ?= sudo
RUN_ID ?=
KIND ?= combined
TELEMETRY ?= 1
REPS ?= 10
SEED ?= 20260813
PRECISION ?= 0.10
CAMPAIGN_ID ?=

RUN_ENV = RUN_ID='$(RUN_ID)' EXPERIMENT_KIND='$(KIND)' DISTRIBUTED_TELEMETRY='$(TELEMETRY)'
CAMPAIGN_ARGS = --repetitions '$(REPS)' --seed '$(SEED)' --relative-precision '$(PRECISION)'
ifneq ($(strip $(CAMPAIGN_ID)),)
CAMPAIGN_ARGS += --campaign-id '$(CAMPAIGN_ID)'
endif

.PHONY: help setup preflight build image-validate test test-unit test-grpc \
	m1 m2 m3 all-modes cycles agent-m1 agent-m2 agent-m3 \
	campaign campaign-plan distributed-all

help: ## Mostra os alvos e as variáveis disponíveis
	@printf '%s\n' \
	  'OpenRAN PQC — execução dos experimentos' \
	  '' \
	  'Preparação e validação:' \
	  '  make setup             cria .venv e instala dependências' \
	  '  make build             constrói openran-pqc:6.0.7' \
	  '  make image-validate    valida strongSwan, PQC, Agent e Collector' \
	  '  make test              executa todos os testes sem Containerlab' \
	  '' \
	  'Experimentos completos:' \
	  '  make m1                baseline SCTP sem IPsec' \
	  '  make m2                integração PSK + X25519 + ESP' \
	  '  make m3                integração X25519 + ML-KEM-768 + ESP' \
	  '  make all-modes         executa M1, M2 e M3 em sequência' \
	  '  make distributed-all   alias explícito de all-modes com gRPC' \
	  '  make cycles            executa os três ciclos completos de M1' \
	  '' \
	  'Campanha:' \
	  '  make campaign-plan     grava a agenda sem executar' \
	  '  make campaign          executa/retoma a campanha randomizada' \
	  '' \
	  'Variáveis (exemplo: make m3 TELEMETRY=1 KIND=steady):' \
	  '  RUN_ID=<id>            identificador da execução individual' \
	  '  KIND=combined|steady|establishment' \
	  '  TELEMETRY=1|0          gRPC ligado por padrão; use 0 para desabilitar' \
	  '  REPS=10 SEED=20260813 PRECISION=0.10 CAMPAIGN_ID=<id>' \
	  '  SUDO=sudo              comando de elevação; use SUDO= se já for root'

setup: $(VENV_STAMP) ## Cria o ambiente Python de desenvolvimento

$(VENV_STAMP): requirements-dev.txt agent/pyproject.toml collector/pyproject.toml
	python3 -m venv '$(VENV)'
	'$(PIP)' install -r requirements-dev.txt
	@touch '$(VENV_STAMP)'

preflight: ## Confere as ferramentas necessárias aos experimentos completos
	@for tool in docker containerlab jq openssl python3 rg; do \
		command -v "$$tool" >/dev/null || { echo "ERRO: $$tool não encontrado" >&2; exit 1; }; \
	done
	@docker image inspect openran-pqc:6.0.7 >/dev/null 2>&1 || { \
		echo 'ERRO: imagem openran-pqc:6.0.7 ausente; execute make build' >&2; exit 1; }

build: ## Constrói a imagem reproduzível
	./image/build.sh

image-validate: preflight ## Executa o smoke test da imagem
	./image/validate.sh

test: test-unit test-grpc ## Executa toda a suíte automatizada sem privilégios
	@bash -n experiments/run.sh image/build.sh image/validate.sh \
		tests/integration/run-m2.sh tests/integration/run-m3.sh \
		tests/integration/run-agent.sh tests/smoke/run-cycles.sh
	@git diff --check

test-unit: setup ## Testes unitários do Agent, Collector e campanha
	PYTHONPATH=agent/src:collector/src '$(PYTHON)' -m unittest discover -s agent/tests -v
	PYTHONPATH=collector/src:agent/src '$(PYTHON)' -m unittest discover -s collector/tests -v
	PYTHONPATH=agent/src '$(PYTHON)' -m unittest discover -s tests/unit -v

test-grpc: setup ## Teste de queda, reconexão, replay e deduplicação gRPC
	PYTHONPATH=agent/src:collector/src '$(PYTHON)' -m unittest \
		tests.integration.test_grpc_reconnect -v

m1: preflight ## Executa o experimento completo M1
	$(SUDO) env $(RUN_ENV) ./experiments/run.sh m1

m2: preflight ## Executa e valida o experimento completo M2
	$(SUDO) env $(RUN_ENV) ./tests/integration/run-m2.sh

m3: preflight ## Executa e valida o experimento completo M3
	$(SUDO) env $(RUN_ENV) ./tests/integration/run-m3.sh

all-modes: preflight ## Executa M1, M2 e M3 em sequência
	$(MAKE) m1 RUN_ID='$(if $(strip $(RUN_ID)),$(RUN_ID)-m1,)' \
		KIND='$(KIND)' TELEMETRY='$(TELEMETRY)' SUDO='$(SUDO)'
	$(MAKE) m2 RUN_ID='$(if $(strip $(RUN_ID)),$(RUN_ID)-m2,)' \
		KIND='$(KIND)' TELEMETRY='$(TELEMETRY)' SUDO='$(SUDO)'
	$(MAKE) m3 RUN_ID='$(if $(strip $(RUN_ID)),$(RUN_ID)-m3,)' \
		KIND='$(KIND)' TELEMETRY='$(TELEMETRY)' SUDO='$(SUDO)'

distributed-all: ## Executa M1, M2 e M3 com telemetria distribuída
	$(MAKE) all-modes TELEMETRY=1 KIND='$(KIND)' SUDO='$(SUDO)'

cycles: preflight ## Executa os três ciclos completos do gate M1
	$(SUDO) env DISTRIBUTED_TELEMETRY='$(TELEMETRY)' \
		CAMPAIGN_ID='$(CAMPAIGN_ID)' ./tests/smoke/run-cycles.sh

agent-m1: preflight ## Valida artefatos do Agent numa execução M1
	$(SUDO) env $(RUN_ENV) ./tests/integration/run-agent.sh m1

agent-m2: preflight ## Valida artefatos do Agent numa execução M2
	$(SUDO) env $(RUN_ENV) ./tests/integration/run-agent.sh m2

agent-m3: preflight ## Valida artefatos do Agent numa execução M3
	$(SUDO) env $(RUN_ENV) ./tests/integration/run-agent.sh m3

campaign-plan: setup ## Cria/mostra a agenda randomizada, sem executar
	'$(PYTHON)' ./experiments/campaign.py $(CAMPAIGN_ARGS) --plan-only

campaign: preflight ## Executa ou retoma a campanha completa
	$(SUDO) env DISTRIBUTED_TELEMETRY='$(TELEMETRY)' \
		'$(PYTHON)' ./experiments/campaign.py $(CAMPAIGN_ARGS)
