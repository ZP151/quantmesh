import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { PreferencesProvider } from '@/lib/preferences'
import { WorkspaceDegraded } from './WorkspaceStates'

it('describes a fresh last-trade limitation without declaring market evidence stale', () => {
  localStorage.clear()
  render(<PreferencesProvider><WorkspaceDegraded isStale={false} reason="Last trade has no bid/ask depth" /></PreferencesProvider>)
  expect(screen.getByText('Live evidence has limitations')).toBeInTheDocument()
  expect(screen.queryByText('Stale market evidence')).not.toBeInTheDocument()
  expect(screen.getByText('Last trade has no bid/ask depth')).toBeInTheDocument()
})
