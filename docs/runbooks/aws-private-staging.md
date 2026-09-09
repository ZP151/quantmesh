# AWS private staging operator runbook

This runbook creates one private, demo-only QuantMesh acceptance station for a
single operator. It does not enable live or testnet trading, public HTTP(S), a
database, snapshots, CI deployment or multi-user access.

## Known account and cost boundary

The AWS console inspection on 2026-09-09 showed USD 0 current/prior-month cost,
no active credits, no Free Tier usage, no budget and no Lightsail instance.
The create page offered the first instance free for 90 days. Recheck that offer
immediately before creation; the repository cannot guarantee account-specific
eligibility.

Select the Linux public-IPv4 2 vCPU / 2 GB / 60 GB plan. AWS currently lists
it at USD 12/month and includes the $12 Linux bundle in the three-month Free
Tier offer. Billing is hourly up to the monthly price. A stopped Lightsail
instance still accrues charges; deletion stops instance charges, while any
retained snapshot, static IP, disk or load balancer may continue charging.

Official references:

- [Lightsail bundle specifications](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-bundles.html)
- [Lightsail pricing and Free Tier](https://aws.amazon.com/lightsail/pricing/)
- [Lightsail billing behavior](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-frequently-asked-questions-faq-billing-and-account-management.html)
- [Deleting an instance and attached-resource warning](https://docs.aws.amazon.com/lightsail/latest/userguide/delete-an-amazon-lightsail-instance.html)

## Stop points that require operator confirmation

Stop and confirm at the moment of each action:

1. Clicking **Create instance** creates a paid-capable AWS resource.
2. Creating an AWS Budget subscribes the supplied email address to alerts.
3. Installing/signing in to Tailscale on Windows and approving the server adds
   devices to a private network.

Do not paste AWS credentials, Tailscale auth keys, broker keys or wallet data
into commands, repository files, chat, logs or fixtures.

## 1. Create the Lightsail instance

On the Lightsail create page select exactly:

- Region: **Asia Pacific (Singapore), ap-southeast-1**
- Platform: **Linux/Unix**
- Blueprint: **OS Only — Ubuntu 24.04 LTS**
- Networking: **public IPv4 bundle**
- Plan: **2 vCPU, 2 GB RAM, 60 GB SSD, USD 12/month after trial**
- Name: `quantmesh-staging`
- Quantity: one
- Automatic snapshots: off

Do not add a database, load balancer, CDN, domain, static IP or snapshot. After
the operator confirms, click **Create instance** once.

Open the instance's **Networking** tab immediately. Lightsail IPv4 and IPv6
firewalls are independent and rules are permissive, so inspect both. Remove
any public 80, 443 or 8765 rule. Temporarily keep SSH/TCP 22 only from the
operator's current public IP (`/32` for IPv4); keep no unrestricted IPv6 SSH
rule. The official firewall behavior is documented in
[Control instance traffic with firewalls](https://docs.aws.amazon.com/lightsail/latest/userguide/understanding-firewall-and-port-mappings-in-amazon-lightsail.html).

## 2. Join the private network

Tailscale's Personal plan is currently free for an individual tailnet and
allows up to six users. Confirm the plan shown during signup; do not accept a
paid upgrade. See [Tailscale free plans](https://tailscale.com/docs/reference/free-plans-discounts)
and [Windows installation](https://tailscale.com/docs/install/windows).

After the operator confirms device installation/authorization:

1. Install the stable Tailscale Windows client and sign in with the intended
   personal identity.
2. In the temporary Lightsail SSH session, install the stable Linux client:

   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up --hostname=quantmesh-staging --ssh
   ```

3. Open the printed authentication URL, sign in to the same tailnet and approve
   the server if device approval is enabled.
4. Confirm the server appears in the Tailscale Machines page. The commands are
   from Tailscale's [Linux install guide](https://tailscale.com/docs/install/linux)
   and [Tailscale SSH guide](https://tailscale.com/docs/features/tailscale-ssh).

On the server, derive the canonical HTTPS origin. `DNSName` has a trailing dot,
which must be removed:

```bash
export QM_DNS_NAME="$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
export QM_ORIGIN="https://${QM_DNS_NAME}"
printf '%s\n' "$QM_ORIGIN"
```

The value must look like
`https://quantmesh-staging.<your-tailnet>.ts.net`. Do not substitute a public
domain or IP address.

## 3. Bootstrap the exact release

The target commit must already be pushed to the public canonical repository.
Set its full SHA; a branch or tag is not accepted:

```bash
export QM_COMMIT='<40-character-lowercase-commit>'
export QM_BOOTSTRAP_DIR="$(mktemp -d)"
curl -fSLo "${QM_BOOTSTRAP_DIR}/bootstrap_host.sh" \
  "https://raw.githubusercontent.com/ZP151/quantmesh/${QM_COMMIT}/deploy/aws/lightsail/bootstrap_host.sh"
curl -fSLo "${QM_BOOTSTRAP_DIR}/deploy_release.py" \
  "https://raw.githubusercontent.com/ZP151/quantmesh/${QM_COMMIT}/deploy/aws/lightsail/deploy_release.py"
curl -fSLo "${QM_BOOTSTRAP_DIR}/quantmesh-staging.service" \
  "https://raw.githubusercontent.com/ZP151/quantmesh/${QM_COMMIT}/deploy/aws/lightsail/quantmesh-staging.service"
sudo bash "${QM_BOOTSTRAP_DIR}/bootstrap_host.sh" "$QM_COMMIT" "$QM_ORIGIN"
```

The bootstrap installs only OS prerequisites, creates the unprivileged service
account, installs the unit and deploys the exact commit. The application stays
on `127.0.0.1:8765`.

Enable private HTTPS after the loopback health check succeeds:

```bash
curl --fail --silent http://127.0.0.1:8765/api/health | python3 -m json.tool
sudo tailscale serve --bg http://127.0.0.1:8765
tailscale serve status
```

Tailscale Serve terminates private HTTPS and proxies to the loopback target;
do not use Funnel. See the official
[Serve command reference](https://tailscale.com/docs/reference/tailscale-cli/serve).

From Windows PowerShell, set the exact values and verify identity:

```powershell
$StagingUrl = 'https://quantmesh-staging.<your-tailnet>.ts.net'
$Commit = '<40-character-lowercase-commit>'
$Health = Invoke-RestMethod "$StagingUrl/api/health"
if ($Health.status -ne 'ok' -or $Health.deployment.environment -ne 'staging' -or $Health.deployment.build_ref -ne $Commit) {
    throw 'Staging health identity mismatch'
}
$Health
```

Open these three bounded smoke routes in the browser:

- `$StagingUrl/app/`
- `$StagingUrl/app/markets`
- `$StagingUrl/app/markets/watchlist`

Confirm the visible `STAGING · <short commit>` badge, the paper-demo badge and
one safe demo write such as arming/canceling the reset control. Arbitrary
public origins remain blocked by the application.

After Tailscale SSH from Windows succeeds (`ssh ubuntu@quantmesh-staging`),
remove the temporary public SSH rule from both Lightsail firewalls. The final
public inbound rule set must contain no 22, 80, 443 or 8765 access.

## 4. Update to another exact commit

From a Tailscale SSH session, retain the canonical origin and download the
deployment program from the target commit before invoking it:

```bash
export QM_NEW_COMMIT='<new-40-character-lowercase-commit>'
export QM_ORIGIN="https://$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
curl -fSLo /tmp/quantmesh-deploy-release.py \
  "https://raw.githubusercontent.com/ZP151/quantmesh/${QM_NEW_COMMIT}/deploy/aws/lightsail/deploy_release.py"
sudo install -m 0755 /tmp/quantmesh-deploy-release.py /usr/local/lib/quantmesh/deploy_release.py
sudo python3 /usr/local/lib/quantmesh/deploy_release.py "$QM_NEW_COMMIT" --origin "$QM_ORIGIN"
```

The command succeeds only after loopback health reports the new exact commit.
If activation fails, it restores and restarts the previous release. A partially
prepared directory is deliberately retained and blocks a blind retry; inspect
it rather than deleting it automatically.

## 5. Deliberate rollback

List retained releases and current identity, then reactivate one exact prior
commit through the same health gate:

```bash
readlink -f /opt/quantmesh/current
find /opt/quantmesh/releases -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort
export QM_OLD_COMMIT='<retained-40-character-lowercase-commit>'
sudo python3 /usr/local/lib/quantmesh/deploy_release.py "$QM_OLD_COMMIT" \
  --origin "$QM_ORIGIN" --activate-existing
```

If the retained release fails its identity check, the command restores the
release that was current before the attempt. Release pruning is manual and is
not part of this runbook.

## 6. Bounded diagnosis

Use these checks; do not start the full pytest/release gate on the server:

```bash
systemctl status quantmesh-staging.service --no-pager
journalctl -u quantmesh-staging.service -n 100 --no-pager
readlink -f /opt/quantmesh/current
curl --fail --silent http://127.0.0.1:8765/api/health | python3 -m json.tool
tailscale status
tailscale serve status
```

## 7. Cost alerts and shutdown

After separate confirmation, create one monthly **Cost budget** named
`quantmesh-staging-monthly` for USD 15 with email alerts at:

- 50% actual spend (USD 7.50),
- 80% forecasted spend (USD 12), and
- 100% actual spend (USD 15).

Enable AWS Free Tier usage alerts as well. Budget monitoring and notifications
are currently free; do not create a charged Budget Report or automatic budget
action. Budgets notify—they are not a hard spending cap and they do not stop
the instance. See [AWS Budgets pricing](https://aws.amazon.com/aws-cost-management/aws-budgets/pricing/)
and [budget creation](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-create.html).

To stop using the station, first preserve only evidence you deliberately need,
then delete the instance in Lightsail. Verify that no snapshot, static IP,
attached disk, load balancer, database or CDN remains. Merely stopping the
instance does not stop billing.
