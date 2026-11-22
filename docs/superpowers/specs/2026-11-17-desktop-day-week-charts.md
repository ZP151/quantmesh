# Desktop day/week chart slice

Issue [308](https://github.com/ZP151/quantmesh/issues/308). This extends the existing
Operate chart adapter and desktop workstation identity. It is not a new visual world.

## Authority and user action

The actual 2026-11-17 operator request prioritizes a usable product, independently
developed multi-period charts, later prediction evaluation and beta accounts in
parallel. The registered Root assignment gives this owner all frontend, locale,
router, generated-client and frontend tests; Product owns backend/auth only.
Implementation choices below are this implementer's decisions under that scope,
not invented detailed operator approvals. The specified daily/weekly view and
independent dimensions settle the structure; no repeated design interview blocks it.

Open one instrument's chart child route, choose how far to look back independently
from daily/weekly bar display, and compare time-linked observations without changing
the saved decision or starting research. Success is correct, inspectable weekly
OHLCV plus working crosshair/pan/zoom linkage from one daily input.

## Selected approach

Reuse `InstrumentChart` and add a bounded child route
`/instruments/:venue/:symbol/charts`, linked from the current market view. This keeps
the decision workspace and its disclosure layout intact. A new chart framework or
a rewrite of the workspace would add risk without serving this user action.

Load existing manifest-gated history at the fixed `1y` source window, which selects
daily resolution in the current API. Lookback is a display time window (1M/3M/6M/1Y),
not a request to select intraday data. Bar display is Daily, Weekly or Both; Both
has clearly labeled independent views in the available desktop region. English and
Chinese use the existing preference mechanism. Source, actual covered dates,
calendar version, sample status and material limitations stay visible. Full source
identity and missing-session dates may disclose in place.

No forecast is generated in this slice. Preserve the existing forecast prop boundary
as the minimal seam; Quant's frozen 5/21/63-trading-day contract comes later. Account
UI similarly follows Product's frozen API after this chart slice.

## Data contract and aggregation

- Accept only explicit daily input from the current history contract: series and
  each bar `interval=1d`, XNYS calendar, matching instrument, finite valid OHLCV,
  aware timestamp instants and unique New York trading dates. Reject hourly,
  unsupported calendar, malformed, duplicate-session or calendar-conflicting input.
- Use the already pinned `exchange-calendars:4.13.2:XNYS` regular-session schedule.
  Export only bounded public session facts for 2024-01-01 through 2027-12-31 from
  the existing installed package; retain generator/version/hash provenance. No new
  package or handwritten holiday algorithm. Outside the calendar bound is an
  explicit unavailable/unknown state, never a completeness claim.
- Group by Monday-to-Sunday New York week. Weekly open is first observed daily
  open; high/low are extrema; close is last observed daily close; volume is the
  sum of daily volume. Do not mutate original rows, interpolate or synthesize bars.
- Keep actual source-session dates and first/last timestamps. Use the first actual
  session as the weekly chart point; a holiday Monday never becomes a fake candle.
- Distinguish missing completed sessions, an in-progress week, live/unfinalized
  daily tails and a source-window boundary week. Do not expect five sessions in a
  holiday week, or mark a partial week complete. A wholly missing week has no OHLCV
  candle and still appears in the missing-session evidence.
- Preserve source-declared gaps/limitations. Structural chart eligibility is not
  real-data, financial, OOS, Paper or live qualification. In particular the new IVV
  extended-session hourly package cannot be turned into RTH daily input here.

## Interaction contract

Link views using UTC instants and their New York week membership, never equal bar
indices. Daily hover maps to the containing observed week; weekly hover maps to
its actual first observed daily session. Each chart shows its own corresponding
price, not a copied price. Missing points clear crosshair rather than invent one.
Visible time windows propagate after a user gesture; programmatic echoes do not
become a new leader. Registration/unmount/rebuild removes callbacks and stale ports.
Lookback, bar display and later forecast horizon are independent states.

## Boundaries and evidence

Desktop Web only, with representative1280/1440/1912 layouts as appropriate. Reuse
the existing read-only dependency junction. No backend/schema/client change is
needed for the chart stage, no provider/SDK/model/new trial/trading operation, no
external raw-data redistribution, mobile, billing, AWS or invitations. Protect
8878/18956/64462 and their source/runtime identities; only an owned temporary preview
may run after a full forecast. Preserve old holds, failures, profiles and originals.

New independent full192MiB purpose: sourceGit32, logs32, build32, browser/captures80,
privateTemp16. ACK2026-11-17 00:08:46SGT; reference2h first increment/4h reviewable
slice, not a whole-product promise. Browser tools currently absent is a reported
capability limitation, not browser verification or a reason to stop testable code.

Deliver short TDD checkpoints, targeted checks, bounded fresh review, then unique
Publisher normal required CI/merge and an actual operable desktop entry. Do not
repeat PR307 acceptance or run broad CI after each field edit.
