set -eu
cd /var/tmp/qm-openai-provider-ed95-zzXQXTHi/repo
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=src:services/research_agent/src:.
/var/tmp/quantmesh-portfolio-runtime-9r8rsnwz/venv/bin/python -B -m pytest -p no:cacheprovider -c services/research_agent/pyproject.toml services/research_agent/tests/test_openai_responses.py::test_owned_resolver_ignores_caller_module_shadow -q --basetemp /var/tmp/qm-openai-provider-ed95-zzXQXTHi/root-shadow-red-tmp