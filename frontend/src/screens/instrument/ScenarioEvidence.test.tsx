import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { DecisionPacket } from '@/lib/api'
import { dateTime } from '@/lib/format'
import { PreferencesProvider } from '@/lib/preferences'
import { PacketEvidenceSummary, ScenarioEvidence } from './ScenarioEvidence'

function displayTime(value: string): string {
  return dateTime(value, 'en')
}

function displayWindow(start: string, end: string): string {
  return [displayTime(start), displayTime(end)].join(' → ')
}

const packet = {
  scenarios: [
    {
      confidence: 'qualitative',
      confidence_reason: 'Forecast quantiles are not calibrated probabilities.',
      invalidation: 180,
      kind: 'bull',
      probability: null,
      target: 210,
      thesis: 'Price holds support and follows the upper forecast path.',
      trigger: 'Close above 195.',
    },
    {
      confidence: 'qualitative',
      confidence_reason: 'Forecast quantiles are not calibrated probabilities.',
      invalidation: 178,
      kind: 'base',
      probability: null,
      target: 200,
      thesis: 'Price follows the median forecast path.',
      trigger: 'Hold the entry zone.',
    },
    {
      confidence: 'qualitative',
      confidence_reason: 'Forecast quantiles are not calibrated probabilities.',
      invalidation: 176,
      kind: 'bear',
      probability: null,
      target: 165,
      thesis: 'Price loses support and follows the lower forecast path.',
      trigger: 'Close below 180.',
    },
  ],
} as unknown as DecisionPacket

const packetWithMetricWindows = {
  ...packet,
  evidence: {
    costs: {
      fee_bps: 1.5,
      half_spread_bps: null,
      slippage_bps: 2.5,
      spread_status: 'confirmation-quote-required',
    },
    forecast_artifact_id: 'artifact-metric-window-fixture',
    forecast_benchmark_name: 'last-close',
    forecast_blockers: [],
    forecast_chronology: {
      test_end: '2025-12-31T00:00:00Z',
      test_start: '2025-12-01T00:00:00Z',
      train_end: '2025-10-31T00:00:00Z',
      train_start: '2024-01-01T00:00:00Z',
      validation_end: '2025-11-30T00:00:00Z',
      validation_start: '2025-11-01T00:00:00Z',
    },
    forecast_eligible: true,
    forecast_limitations: [],
    forecast_metrics: [
      {
        benchmark_mae: 1.3,
        coverage_50: 0.51,
        coverage_80: 0.81,
        coverage_95: 0.96,
        interval_test_count: 7,
        mae: 1.1,
        residual_count: 70,
        rmse: 1.2,
        sessions: 7,
        test_end: '2026-02-07T00:00:00Z',
        test_start: '2026-02-01T00:00:00Z',
        validation_end: '2026-01-20T00:00:00Z',
        validation_start: '2026-01-10T00:00:00Z',
      },
      {
        benchmark_mae: 3.3,
        coverage_50: 0.52,
        coverage_80: 0.82,
        coverage_95: 0.97,
        interval_test_count: 30,
        mae: 3.1,
        residual_count: 300,
        rmse: 3.2,
        sessions: 30,
        test_end: '2026-04-30T00:00:00Z',
        test_start: '2026-04-01T00:00:00Z',
        validation_end: '2026-03-31T00:00:00Z',
        validation_start: '2026-03-01T00:00:00Z',
      },
    ],
    forecast_paths: [],
    forecast_synthetic: false,
    history_dataset_id: 'history-metric-window-fixture',
    history_dataset_revision: 1,
    history_duplicates: [],
    history_gaps: [],
    history_generated_at: '2026-05-01T00:00:00Z',
    history_limitations: [],
    history_source: 'trusted-test-source',
  },
} as unknown as DecisionPacket

describe('ScenarioEvidence', () => {
  it('renders the exact Bull, Base and Bear facts without inventing probabilities', () => {
    render(<ScenarioEvidence packet={packet} />, { wrapper: PreferencesProvider })

    expect(screen.getAllByRole('article')).toHaveLength(3)
    expect(screen.getByRole('heading', { name: 'Bull' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Base' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Bear' })).toBeInTheDocument()
    expect(screen.getByText('Price holds support and follows the upper forecast path.')).toBeInTheDocument()
    expect(screen.getByText('Close below 180.')).toBeInTheDocument()
    expect(screen.getAllByText('Forecast quantiles are not calibrated probabilities.')).toHaveLength(3)
    expect(screen.queryByText(/%/)).not.toBeInTheDocument()
  })

  it('binds every forecast metric to its own validation and test sample windows', () => {
    render(<PacketEvidenceSummary packet={packetWithMetricWindows} />, { wrapper: PreferencesProvider })

    const artifactOverview = screen.getByRole('group', { name: 'Forecast artifact chronology overview' })
    expect(within(artifactOverview).getByText(displayWindow(
      '2025-11-01T00:00:00Z',
      '2025-11-30T00:00:00Z',
    ))).toBeInTheDocument()
    expect(within(artifactOverview).getByText(displayWindow(
      '2025-12-01T00:00:00Z',
      '2025-12-31T00:00:00Z',
    ))).toBeInTheDocument()

    const sevenSession = screen.getByRole('group', { name: '7-session metrics' })
    expect(within(sevenSession).getByText('1.1')).toBeInTheDocument()
    expect(within(sevenSession).getByText('1.2')).toBeInTheDocument()
    expect(within(sevenSession).getByText('1.3')).toBeInTheDocument()
    expect(within(sevenSession).getByText('51% / 81% / 96%')).toBeInTheDocument()
    expect(within(sevenSession).getByText('70')).toBeInTheDocument()
    expect(within(sevenSession).getByText('7')).toBeInTheDocument()
    expect(within(sevenSession).getByText(displayTime('2026-01-10T00:00:00Z'))).toBeInTheDocument()
    expect(within(sevenSession).getByText(displayTime('2026-01-20T00:00:00Z'))).toBeInTheDocument()
    expect(within(sevenSession).getByText(displayTime('2026-02-01T00:00:00Z'))).toBeInTheDocument()
    expect(within(sevenSession).getByText(displayTime('2026-02-07T00:00:00Z'))).toBeInTheDocument()
    expect(within(sevenSession).queryByText(displayTime('2026-03-01T00:00:00Z'))).not.toBeInTheDocument()
    expect(within(sevenSession).queryByText(displayWindow(
      '2025-11-01T00:00:00Z',
      '2025-11-30T00:00:00Z',
    ))).not.toBeInTheDocument()

    const thirtySession = screen.getByRole('group', { name: '30-session metrics' })
    expect(within(thirtySession).getByText('3.1')).toBeInTheDocument()
    expect(within(thirtySession).getByText('3.2')).toBeInTheDocument()
    expect(within(thirtySession).getByText('3.3')).toBeInTheDocument()
    expect(within(thirtySession).getByText('52% / 82% / 97%')).toBeInTheDocument()
    expect(within(thirtySession).getByText('300')).toBeInTheDocument()
    expect(within(thirtySession).getByText('30')).toBeInTheDocument()
    expect(within(thirtySession).getByText(displayTime('2026-03-01T00:00:00Z'))).toBeInTheDocument()
    expect(within(thirtySession).getByText(displayTime('2026-03-31T00:00:00Z'))).toBeInTheDocument()
    expect(within(thirtySession).getByText(displayTime('2026-04-01T00:00:00Z'))).toBeInTheDocument()
    expect(within(thirtySession).getByText(displayTime('2026-04-30T00:00:00Z'))).toBeInTheDocument()
    expect(within(thirtySession).queryByText(displayTime('2026-01-10T00:00:00Z'))).not.toBeInTheDocument()
  })
})
