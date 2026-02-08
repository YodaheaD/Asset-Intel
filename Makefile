# Makefile
# ------------------------------------------------------------
# AssetIntel Dev Runner (WSL/Ubuntu)
#
# Primary usage:
#   make dev
#   make attach
#
# Stop:
#   make stop
#
# Help:
#   make help
# ------------------------------------------------------------

SHELL := /bin/bash

# ---- Config ----
PROJECT_DIR ?= .
HOST ?= 0.0.0.0
PORT ?= 8000
APP_IMPORT ?= app.main:app
WORKER_SETTINGS ?= app.worker.WorkerSettings

# Env (override by exporting in shell or via make VAR=value)
DATABASE_URL ?= postgresql+asyncpg://postgres:password@localhost:5432/assetintel
REDIS_URL ?= redis://localhost:6379/0
USE_ARQ_WORKER ?= true
ARQ_MAX_TRIES ?= 3

ADMIN_API_ENABLED ?= false
ADMIN_KEY ?=

TMUX_SESSION ?= assetintel

# ---- Internal helper for exporting env to tmux panes ----
define EXPORT_ENV
export DATABASE_URL="$(DATABASE_URL)"; \
export REDIS_URL="$(REDIS_URL)"; \
export USE_ARQ_WORKER="$(USE_ARQ_WORKER)"; \
export ARQ_MAX_TRIES="$(ARQ_MAX_TRIES)"; \
export ADMIN_API_ENABLED="$(ADMIN_API_ENABLED)"; \
export ADMIN_KEY="$(ADMIN_KEY)";
endef

.PHONY: help install-tools install-py dev attach stop redis api worker redis-ping health arq-keys config

help:
	@echo ""
	@echo "AssetIntel Make targets:"
	@echo "  make dev            Start Redis + API + Worker in tmux"
	@echo "  make attach         Attach to tmux session"
	@echo "  make stop           Stop tmux session"
	@echo ""
	@echo "Run individually:"
	@echo "  make redis          Start redis-server in foreground"
	@echo "  make api            Start FastAPI (uvicorn)"
	@echo "  make worker         Start ARQ worker"
	@echo ""
	@echo "Checks:"
	@echo "  make redis-ping     redis-cli ping"
	@echo "  make health         curl /api/v1/health"
	@echo "  make arq-keys       show arq:* keys in Redis"
	@echo ""
	@echo "Setup:"
	@echo "  make install-tools  Install tmux + redis"
	@echo "  make install-py     Install pinned python deps (arq, redis)"
	@echo ""
	@echo "Config override examples:"
	@echo "  REDIS_URL=redis://localhost:6380/0 make dev"
	@echo "  PORT=9000 make api"
	@echo ""

install-tools:
	@echo "==> Installing system tools (tmux, redis-server, redis-cli)..."
	sudo apt update
	sudo apt install -y tmux redis-server redis-tools

install-py:
	@echo "==> Installing python deps (pin versions for stability)..."
	pip install -U arq==0.26.3 redis==5.0.8

# ---- Run processes individually ----

redis:
	@echo "==> Starting Redis (foreground)..."
	redis-server

api:
	@echo "==> Starting FastAPI (uvicorn)..."
	cd "$(PROJECT_DIR)" && \
	$(EXPORT_ENV) \
	uvicorn "$(APP_IMPORT)" --reload --host "$(HOST)" --port "$(PORT)"

worker:
	@echo "==> Starting ARQ worker..."
	cd "$(PROJECT_DIR)" && \
	$(EXPORT_ENV) \
	arq "$(WORKER_SETTINGS)"

# ---- Dev mode (tmux) ----

dev:
	@command -v tmux >/dev/null 2>&1 || { echo "tmux not found. Run: make install-tools"; exit 1; }
	@command -v redis-server >/dev/null 2>&1 || { echo "redis-server not found. Run: make install-tools"; exit 1; }
	@echo "==> Starting tmux session '$(TMUX_SESSION)' (redis | worker | api)"
	@tmux has-session -t "$(TMUX_SESSION)" 2>/dev/null && { echo "Session already exists. Run: make attach"; exit 0; } || true

	# Create session (pane 0 = TOP)
	@tmux new-session -d -s "$(TMUX_SESSION)" -n main

	# Split TOP / BOTTOM
	@tmux split-window -v -t "$(TMUX_SESSION):main.0"

	# TOP-LEFT: Redis (pane 0)
	@tmux send-keys -t "$(TMUX_SESSION):main.0" \
		'cd "$(PROJECT_DIR)" && $(EXPORT_ENV) redis-server' Enter

	# TOP-RIGHT: ARQ worker (pane 1)
	@tmux split-window -h -t "$(TMUX_SESSION):main.0"
	@tmux send-keys -t "$(TMUX_SESSION):main.1" \
		'cd "$(PROJECT_DIR)" && $(EXPORT_ENV) arq "$(WORKER_SETTINGS)"' Enter

	# BOTTOM: FastAPI (pane 2)
	@tmux send-keys -t "$(TMUX_SESSION):main.2" \
		'cd "$(PROJECT_DIR)" && $(EXPORT_ENV) uvicorn "$(APP_IMPORT)" --reload --host "$(HOST)" --port "$(PORT)"' Enter

	# Resize for balance
	@tmux resize-pane -t "$(TMUX_SESSION):main.0" -y 15

	# Labels (optional but 🔥)
	@tmux select-pane -t "$(TMUX_SESSION):main.0" -T "Redis"
	@tmux select-pane -t "$(TMUX_SESSION):main.1" -T "ARQ Worker"
	@tmux select-pane -t "$(TMUX_SESSION):main.2" -T "FastAPI"

	# Focus FastAPI on attach
	@tmux select-pane -t "$(TMUX_SESSION):main.2"

	@echo "==> Running. Next:"
	@echo "    make attach"
	@echo "==> Stop with:"
	@echo "    make stop"
attach:
	@tmux attach -t "$(TMUX_SESSION)"

stop:
	@tmux kill-session -t "$(TMUX_SESSION)" 2>/dev/null || true
	@echo "==> Stopped tmux session '$(TMUX_SESSION)'"

# ---- Checks ----

redis-ping:
	@redis-cli ping

health:
	@curl -sS "http://localhost:$(PORT)/api/v1/health" || true
	@echo ""

arq-keys:
	@redis-cli KEYS "arq:*"

config:
	@echo "DATABASE_URL=$(DATABASE_URL)"
	@echo "REDIS_URL=$(REDIS_URL)"
	@echo "USE_ARQ_WORKER=$(USE_ARQ_WORKER)"
	@echo "ARQ_MAX_TRIES=$(ARQ_MAX_TRIES)"
	@echo "ADMIN_API_ENABLED=$(ADMIN_API_ENABLED)"
