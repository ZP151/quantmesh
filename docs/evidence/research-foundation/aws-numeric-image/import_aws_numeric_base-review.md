# Bounded pre-execution import review

Reviewed source: `output/import_aws_numeric_base.py`.

Actual reviewed SHA256: `1ED0B09272CD5D2EC2783C081D2F8E61978AE312318AA262F065F35D130CDAF0`.

Disposition: clear within this operator recipe; no substantive P1/P2 found in the reviewed privilege, fixed-input, failure/accounting and normal-verification paths.

The recipe binds an owned new phase, the archive digest through a held descriptor, the expected Engine/build and an initially empty image/container state. The root command uses explicit empty Docker config, a literal local Unix socket and a clean environment. It contains no pull, container creation/start, service activation, prune or daemon-stop command. GNU timeout bounds the CLI command group; the recipe explicitly does not treat CLI exit as daemon cancellation. Failure retains the CLI result, final measured space, retained file sizes and an Engine observation or NOT_PROVEN. A guard breach marks failure rather than proving cancellation or a hard storage quota.

Normal acceptance requires the sole exact success line, expected image target ID/platform, ordered rootfs diff IDs, config comparison and final Engine/image count plus disk gate. The pinned [Engine load implementation](https://raw.githubusercontent.com/moby/moby/a5b58c94d334674eae3a3207d4f05417643a90d0/daemon/containerd/image_exporter.go) can emit an unpack error and return success; the extra error line is rejected here. Its other skipped-unpack paths mean these checks still establish only the stated returned import request and observed image metadata, not successful execution or native qualification.

## Config comparison question

The pinned [inspect implementation](https://raw.githubusercontent.com/moby/moby/a5b58c94d334674eae3a3207d4f05417643a90d0/daemon/containerd/image_inspect.go) decodes the config into a Go struct before returning it. The matching [Docker config type](https://raw.githubusercontent.com/moby/docker-image-spec/v1.3.1/specs-go/v1/image.go) embeds the [OCI config type](https://raw.githubusercontent.com/opencontainers/image-spec/v1.1.1/specs-go/v1/config.go), whose fields use omitempty. Consequently, raw source keys with empty/null/false values can disappear from inspect output. Existing local receipts bind the original config digest but do not contain its config subsection; this review therefore does not assert a demonstrated mismatch for this particular pinned config.

Keep the literal comparison fail closed. If an actual benign normalization mismatch occurs, do not omit fields merely to obtain success: an independently bounded export/content proof preserving the original manifest-to-config chain and exact raw config hash is the coherent alternative. Any change to that verification needs its own narrow review.

## Evidence limits

Read-only source and existing capsule/build receipts were inspected, along with primary pinned upstream source. No recipe execution, remote command, image import, tests or probes were performed by this reviewer. The recipe was unexecuted at this review. This receipt certifies no materialized image, unpacked rootfs, runtime, numerical/native closure or completion of Option A.
