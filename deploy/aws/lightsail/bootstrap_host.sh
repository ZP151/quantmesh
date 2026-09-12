#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 || ! "$1" =~ ^[0-9a-f]{40}$ ]]; then
  echo "usage: sudo ./bootstrap_host.sh <40-character-lowercase-commit> <https-tailscale-origin>" >&2
  exit 2
fi

commit="$1"
staging_origin="$2"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install --yes --no-install-recommends ca-certificates curl git python3 python3-venv

if ! id --user quantmesh >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/quantmesh --create-home --shell /usr/sbin/nologin quantmesh
fi

install -d -m 0755 /opt/quantmesh /opt/quantmesh/releases /usr/local/lib/quantmesh
install -d -o quantmesh -g quantmesh -m 0750 /var/lib/quantmesh /var/lib/quantmesh/demo
install -m 0644 "${script_dir}/quantmesh-staging.service" /etc/systemd/system/quantmesh-staging.service
install -m 0755 "${script_dir}/deploy_release.py" /usr/local/lib/quantmesh/deploy_release.py

systemctl daemon-reload
python3 /usr/local/lib/quantmesh/deploy_release.py "$commit" --origin "$staging_origin"
systemctl enable quantmesh-staging.service
