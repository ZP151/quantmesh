set -eu
cd /var/tmp/qm-openai-provider-ed95-zzXQXTHi/repo
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=src:services/research_agent/src:.
python=/var/tmp/quantmesh-portfolio-runtime-9r8rsnwz/venv/bin/python
"$python" -B /var/tmp/qm-openai-provider-ed95-zzXQXTHi/frozen-check.py
"$python" -B /var/tmp/quantmesh-portfolio-runtime-9r8rsnwz/admit.py /var/tmp/qm-openai-provider-ed95-zzXQXTHi/repo