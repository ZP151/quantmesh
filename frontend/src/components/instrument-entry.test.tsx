import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { beforeEach, expect, it } from 'vitest'

import { PreferencesProvider } from '@/lib/preferences'
import { CommandPalette } from './shell/CommandPalette'
import { InstrumentEntry } from './instrument-entry'

function Location() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}{location.search}</output>
}

function setup(children: React.ReactNode, locale = 'en') {
  localStorage.setItem('quantmesh.preferences', JSON.stringify({ locale, theme: 'dark' }))
  render(<QueryClientProvider client={new QueryClient()}><PreferencesProvider><MemoryRouter>
    {children}<Location />
  </MemoryRouter></PreferencesProvider></QueryClientProvider>)
  return userEvent.setup()
}

beforeEach(() => localStorage.clear())

it('normalizes the supported ticker and opens chart analysis by keyboard', async () => {
  const user = setup(<InstrumentEntry />)
  await user.type(screen.getByRole('textbox', { name: 'Ticker' }), '  nvda {Enter}')
  expect(screen.getByTestId('location')).toHaveTextContent('/instruments/moomoo/NVDA?horizon=30&analysis=fresh')
})

it('explains unsupported symbols without navigating', async () => {
  const user = setup(<InstrumentEntry />)
  await user.type(screen.getByRole('textbox', { name: 'Ticker' }), 'TSLA{Enter}')
  expect(screen.getByRole('textbox', { name: 'Ticker' })).toHaveAccessibleDescription(
    'Scenario Lab supports AAPL and NVDA on Moomoo. Enter a supported ticker.',
  )
  expect(screen.getByTestId('location')).toHaveTextContent(/^\/$/)
})

it('offers the same supported entry in Simplified Chinese', async () => {
  const user = setup(<InstrumentEntry />, 'zh-CN')
  await user.type(screen.getByRole('textbox', { name: '股票代码' }), 'aapl')
  await user.click(screen.getByRole('button', { name: '打开图表' }))
  expect(screen.getByTestId('location')).toHaveTextContent('/instruments/moomoo/AAPL?horizon=30&analysis=fresh')
})

it('opens a typed ticker from the existing command palette', async () => {
  const user = setup(<CommandPalette open onOpenChange={() => {}} demoAttached={false} />)
  await user.type(screen.getByRole('textbox'), 'nvda{Enter}')
  expect(screen.getByTestId('location')).toHaveTextContent('/instruments/moomoo/NVDA?horizon=30&analysis=fresh')
})
