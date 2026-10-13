set -eu
cd /var/tmp/qm-openai-provider-ed95-zzXQXTHi/repo
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=src:services/research_agent/src:.
python=/var/tmp/quantmesh-portfolio-runtime-9r8rsnwz/venv/bin/python
"$python" -B -m ruff check --no-cache services/research_agent/src/qm_research_agent/openai_responses.py services/research_agent/tests/test_openai_responses.py
"$python" -B -m ruff format --check --no-cache services/research_agent/src/qm_research_agent/openai_responses.py services/research_agent/tests/test_openai_responses.py
"$python" -B -m pytest -p no:cacheprovider -c services/research_agent/pyproject.toml services/research_agent/tests/test_openai_responses.py services/research_agent/tests/test_agent.py services/research_agent/tests/test_hardening.py services/research_agent/tests/test_portfolio_budgets.py services/research_agent/tests/test_service.py -q --basetemp /var/tmp/qm-openai-provider-ed95-zzXQXTHi/root-final-green-tmp --junitxml=/var/tmp/qm-openai-provider-ed95-zzXQXTHi/root-final-green.xml