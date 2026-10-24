// Actual own-loopback API response for an owned synthetic two-row CSV.
// This is inspection/workflow evidence, not real-market research acceptance.
export const localReport = {
  "schema_version": 1,
  "snapshot_id": "5f2ab14687a0eef36602879685178e6e8e20ddd55699e5610f939e37a399afdb",
  "imported_at": "2026-10-24T16:46:13.432755+00:00",
  "label": "Owned engineering sample",
  "symbol": "SPY",
  "venue": "moomoo",
  "calendar_id": "XNYS",
  "interval": "1d",
  "evidence_kind": "user_snapshot",
  "source": {
    "provider": "Owned synthetic acceptance sample",
    "received_at": null,
    "license_scope": "unknown",
    "license_evidence": "unknown",
    "pit_status": "unknown",
    "adjustment": "unknown",
    "volume_unit": "unknown",
    "session_semantics": "unknown"
  },
  "coverage": {
    "rows": 2,
    "valid_rows": 2,
    "first_date": "2026-10-15",
    "last_date": "2026-10-16",
    "expected_sessions": 2,
    "missing_sessions": [],
    "unexpected_sessions": []
  },
  "freshness": {
    "as_of": "2026-10-24T16:46:14.347134+00:00",
    "latest_complete_session": "2026-10-23",
    "last_session": "2026-10-16",
    "age_sessions": 5,
    "status": "STALE"
  },
  "qualification": {
    "status": "INSUFFICIENT",
    "structural_status": "PASS",
    "allowed_use": [
      "inspect_evidence_only",
      "protocol_planning"
    ],
    "R1": "INSUFFICIENT",
    "R2": "INSUFFICIENT",
    "R3": "NOT_AUTHORIZED",
    "reasons": [
      "Source scope/license are caller claims; usage rights are not independently verified.",
      "Bar/session time and receipt are not historical available_at or revision/PIT evidence.",
      "Corporate actions, adjustments and dividend ex/pay-date coverage are not independently verified.",
      "Calendar alignment does not independently verify the source's daily-session semantics.",
      "Declared adjustment=unknown; price/currency units and adjustment lineage remain unverified.",
      "Declared volume unit=unknown; units do not establish executable liquidity or fills.",
      "Optional Phase1 preauthorization/post-review/source-evidence digests are retained claims, not independently verified receipts."
    ]
  },
  "checks": [
    {
      "code": "bar_values",
      "status": "PASS",
      "count": 0,
      "message": "Finite OHLCV values and price bounds checked; zero volume is not fill evidence.",
      "locations": [],
      "locations_truncated": false
    },
    {
      "code": "bar_time",
      "status": "PASS",
      "count": 0,
      "message": "UTC bar OPEN aligned to the explicitly selected daily session calendar.",
      "locations": [],
      "locations_truncated": false
    },
    {
      "code": "bar_order",
      "status": "PASS",
      "count": 0,
      "message": "Original input order checked without sorting or repairing rows.",
      "locations": [],
      "locations_truncated": false
    },
    {
      "code": "bar_duplicates",
      "status": "PASS",
      "count": 0,
      "message": "Daily session duplicates checked without silently deduplicating rows.",
      "locations": [],
      "locations_truncated": false
    },
    {
      "code": "session_coverage",
      "status": "PASS",
      "count": 0,
      "message": "Declared date range compared with the pinned session calendar.",
      "locations": [],
      "locations_truncated": false
    },
    {
      "code": "unfinished_session",
      "status": "PASS",
      "count": 0,
      "message": "Daily bar requires session close plus 30 minute research grace.",
      "locations": [],
      "locations_truncated": false
    },
    {
      "code": "source_receipt",
      "status": "PASS",
      "count": 0,
      "message": "Declared receipt chronology checked; receipt is not historical available_at.",
      "locations": [],
      "locations_truncated": false
    },
    {
      "code": "source_rights",
      "status": "INSUFFICIENT",
      "count": 0,
      "message": "Source scope/license are caller claims; usage rights are not independently verified.",
      "locations": [],
      "locations_truncated": false
    },
    {
      "code": "point_in_time",
      "status": "INSUFFICIENT",
      "count": 0,
      "message": "Bar/session time and receipt are not historical available_at or revision/PIT evidence.",
      "locations": [],
      "locations_truncated": false
    },
    {
      "code": "corporate_actions",
      "status": "INSUFFICIENT",
      "count": 0,
      "message": "Corporate actions, adjustments and dividend ex/pay-date coverage are not independently verified.",
      "locations": [],
      "locations_truncated": false
    },
    {
      "code": "source_session",
      "status": "INSUFFICIENT",
      "count": 0,
      "message": "Calendar alignment does not independently verify the source's daily-session semantics.",
      "locations": [],
      "locations_truncated": false
    },
    {
      "code": "adjustment_basis",
      "status": "INSUFFICIENT",
      "count": 0,
      "message": "Declared adjustment=unknown; price/currency units and adjustment lineage remain unverified.",
      "locations": [],
      "locations_truncated": false
    },
    {
      "code": "volume_units",
      "status": "INSUFFICIENT",
      "count": 0,
      "message": "Declared volume unit=unknown; units do not establish executable liquidity or fills.",
      "locations": [],
      "locations_truncated": false
    },
    {
      "code": "phase1_evidence",
      "status": "INSUFFICIENT",
      "count": 0,
      "message": "Optional Phase1 preauthorization/post-review/source-evidence digests are retained claims, not independently verified receipts.",
      "locations": [],
      "locations_truncated": false
    }
  ],
  "dataset_ref": {
    "dataset_id": "csv-5f2ab14687a0eef36602879685178e6e8e20ddd55699e5610f939e37a399",
    "revision": 1,
    "manifest_digest": "ce94140f6004566e230e7007e2659d20ade0bbdcdee2e4e4aac28a0843eaaf64",
    "permission_class": "local_research",
    "export_digest": "7a1b9dbf44abf1d2f1615e768fffd55223596f80270dfb911515effc09d6a7ba"
  },
  "report_digest": "2f67f414ac8b2a64fa0d027d8518cb4182b9a60668004dd0b4a1abc1f8e4a942",
  "lineage": {
    "original_sha256": "f3a11c6a50f0b70c280e8a22647ed73ea5533bf813cd5a578119c11813e5f198",
    "normalized_sha256": "7a1b9dbf44abf1d2f1615e768fffd55223596f80270dfb911515effc09d6a7ba",
    "manifest_sha256": "ce94140f6004566e230e7007e2659d20ade0bbdcdee2e4e4aac28a0843eaaf64"
  },
  "next_action": {
    "kind": "plan_experiment",
    "href": "/app/research/jobs",
    "submission_allowed": false,
    "reason": "Imported input is unqualified; existing fixture jobs cannot use this reference."
  }
}

// Actual planning-reference eligibility returned by the frozen backend.
export const actualReferenceEligibility = {
  "status": "BLOCKED",
  "reasons": [
    "Scope/license are caller claims; usage rights are not independently verified.",
    "Bar time and receipt are not historical available_at or revision/PIT evidence.",
    "Elapsed sessions by import time do not prove this held file was final when captured; source finality/revisions remain unverified.",
    "Corporate actions, adjustments and dividend ex/pay-date coverage are not independently verified.",
    "Calendar alignment does not verify the source's daily-session semantics.",
    "Declared adjustment=unknown; price/currency units and adjustment lineage remain unverified.",
    "Declared volume unit=unknown; units do not establish executable liquidity or fills.",
    "Phase1 preauthorization/post-review/source-evidence digests are claims, not independently verified receipts."
  ]
}
