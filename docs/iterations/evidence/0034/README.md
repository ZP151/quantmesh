# Iteration 0034 — AWS observation evidence

Captured on 2026-09-12 against deployed build
`e185c3b052ca0cdd3590b0d5d05fd7460d783fb7` at the existing private workstation.

- `aws-witness-summary.json`: five-minute application API witness, health before
  and after, source counts/ages, receipt delays, replay extent and safety checks.
- `aws-quote-observations.jsonl`: 180 public-market quote observations (60 samples
  x BTC/ETH/SOL) extracted from the same API witness. Source time (`data_time`)
  and server receipt time (`received_at`) are separate; `observed_at` is the
  sampler clock. These are sampled observations, not every received frame.
- `aws-browser-witness.json`: three actual rendered DOM observations, plus
  desktop/mobile, keyboard replay and reload inspection. Concatenated row text
  preserves DOM extraction order: symbol, venue, label, bid, ask, mid, spread,
  last, event time, received time, lag, age. Event/received display uses UTC+08;
  observation timestamps use UTC. DOM ages and API ages are different samples.

The 304.88-second API run has zero disconnected samples, not proof of perpetual
uptime. Browser observations span 323.567 seconds; no continuous end-to-end
latency SLA is claimed. Controlled disconnect/reconnect coverage is recorded in
the [iteration ledger](../../0034-live-data-delivery.md), separate from live AWS
observations. Replay counts differ by observation time as ingestion continues.
Only public quote payloads and non-secret health/acceptance metadata are retained.
