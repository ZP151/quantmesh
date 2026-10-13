set -eu
cd /var/tmp/qm-openai-provider-ed95-zzXQXTHi/repo
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=src:services/research_agent/src:.
/var/tmp/quantmesh-portfolio-runtime-9r8rsnwz/venv/bin/python -B /var/tmp/qm-openai-provider-ed95-zzXQXTHi/frozen-check.py
/var/tmp/quantmesh-portfolio-runtime-9r8rsnwz/venv/bin/python -B /var/tmp/quantmesh-portfolio-runtime-9r8rsnwz/admit.py /var/tmp/qm-openai-provider-ed95-zzXQXTHi/repo
du -sk /var/tmp/qm-openai-provider-ed95-zzXQXTHi
