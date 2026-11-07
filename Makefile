.PHONY: help install dev test health

help:
	@echo "make install  — установить зависимости"
	@echo "make dev      — запустить API в dev-режиме (--reload)"
	@echo "make test     — запустить тесты"
	@echo "make health   — проверить /api/health"

install:
	pip install -r requirements.txt

dev:
	uvicorn api.main:app --reload --host 127.0.0.1 --port 8000

test:
	PYTHONPATH=. pytest tests/ -v

health:
	curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool