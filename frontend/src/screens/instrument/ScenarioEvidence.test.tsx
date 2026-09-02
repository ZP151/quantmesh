import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { DecisionPacket } from '@/lib/api'
import { PreferencesProvider } from '@/lib/preferences'
import { ScenarioEvidence } from './ScenarioEvidence'

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
} as DecisionPacket

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
})
