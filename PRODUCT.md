# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

QuantMesh has an existing Python and FastAPI backend. The operator-facing
frontend will be replaced with a React and TypeScript application that reuses
selected shadcn/ui components and compiles into the Python package for a
one-command local production launch. The exact frontend boundary, build
pipeline and generated API-client contract require an ADR before implementation.

## Users

The primary user is a research-minded individual active trader operating a
local workstation. They need to turn a ticker or watchlist idea into a
defensible risk-first decision quickly, without trusting a black-box signal or
reconstructing evidence through the CLI or database.

## Product Purpose

QuantMesh turns heterogeneous market data, experiments, forecasts and venue
state into one inspectable DecisionPacket. Success means the operator can move
from ticker to a saved Reject, Watch or Paper proposal in no more than two
minutes, understand every blocker and citation, and later replay the paper
result and review from the UI.

## Positioning

Unlike a single-venue trading terminal or a generic AI signal dashboard,
QuantMesh joins equities, crypto and event probabilities under one local
evidence and risk model while preserving each venue's constraints. It
compresses market context, scenarios, risk, evidence and action into one short
path. AI may explain and challenge research, but deterministic code retains
evidence, risk and execution authority.

## Operating Context

- Local desktop use, initially on Windows, through a loopback web application.
- Deterministic offline demo data is the default acceptance environment.
- Optional read-only or simulated integrations include Moomoo OpenD,
  Hyperliquid testnet and supported prediction-market data providers.
- The normal loop is ticker/watchlist → market state and key levels →
  Bull/Base/Bear scenarios → entry/invalidation/stop/target/size → Reject,
  Watch or Paper proposal → monitoring and review.

## Capabilities and Constraints

- Paper trading is the default and must work without credentials.
- Every displayed value must identify its source, timestamp and freshness.
- External integrations must expose connected, delayed, stale, empty and error
  states rather than silently producing blank screens.
- AI output is research input and cannot bypass deterministic risk approval.
- A deterministic DecisionPacket remains available when no model service is
  configured or an AI response fails schema or citation validation.
- Stale, low-quality, leakage-affected or missing evidence blocks Paper
  proposal while leaving Reject and Watch available with explicit reasons.
- Paper proposals use the existing risk kernel and require a second explicit
  confirmation.
- Real-money orders, mainnet signing and credential use remain outside
  iteration 0027 and require separate explicit authority.
- The backend domain, risk and execution contracts stay authoritative while
  the operator interface is replaced.

## Brand Commitments

- The product name is QuantMesh.
- The interface should feel precise, calm, high-trust and technically serious.
- The user has selected a restrained black and green dark-technical direction,
  with Hyperliquid as a quality reference rather than a screen to copy.
- English remains the primary project language, with Chinese companion guidance
  for operator acceptance.

## Evidence on Hand

M0 through M10 provide implemented backend behavior, adapters, research
artifacts, paper execution, risk controls and audit records with an extensive
automated test baseline. RC1 proved packaging and engineering integration, but
its runtime starts with an empty paper account and exposes a minimally styled
server-rendered interface. There are no production-user claims or real trading
performance claims, and future UI work must not fabricate them.

## Product Principles

1. A testable product must expose a complete user workflow, not only passing
   backend tests.
2. Demonstration state is deterministic, labeled and resettable; real provider
   state is visibly sourced and never confused with synthetic data.
3. Reuse mature open-source components behind owned boundaries before building
   commodity UI or infrastructure from scratch.
4. Dense information stays scannable, with progressive disclosure for evidence
   and risk details.
5. Safety state is always visible, and paper/live authority is never ambiguous.
6. Optimize for completed, replayable user decisions rather than framework,
   model, route or test counts.

## Accessibility & Inclusion

The workstation targets WCAG 2.2 AA, full keyboard operation, visible focus,
reduced-motion support and layouts that do not encode gain, loss, warning or
approval through red/green color alone.
