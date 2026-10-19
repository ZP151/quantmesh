import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import { PreferencesProvider } from '@/lib/preferences'
import { CommandPalette } from './CommandPalette'

const mocks = vi.hoisted(() => ({ status: vi.fn(), disarm: vi.fn(), engage: vi.fn(), reset: vi.fn() }))
vi.mock('@/lib/paper-controls-api', () => ({ paperControlsApi: { status: mocks.status } }))
vi.mock('@/lib/api', () => ({ api: { disarmKillSwitch: mocks.disarm, engageKillSwitch: mocks.engage, demoReset: mocks.reset } }))
function Location() { return <p data-testid="location">{useLocation().pathname}</p> }
function mount(open = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><PreferencesProvider><MemoryRouter>
    <CommandPalette open={open} onOpenChange={vi.fn()} demoAttached /><Location />
  </MemoryRouter></PreferencesProvider></QueryClientProvider>)
}
beforeEach(() => {
  vi.clearAllMocks(); localStorage.clear()
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })
})
it.each(['configured', 'loading', 'error'])('hides old disarm/reset for %s and navigates to verified controls', async mode => {
  if (mode === 'configured') mocks.status.mockResolvedValue({ synthetic: true })
  else if (mode === 'error') mocks.status.mockRejectedValue({ code: 'request_failed' })
  else mocks.status.mockReturnValue(new Promise(() => {}))
  mount()
  await userEvent.click(await screen.findByRole('button', { name: /Review paper controls/ }))
  expect(screen.getByTestId('location')).toHaveTextContent('/ops/kill-switch')
  expect(screen.queryByRole('button', { name: /Disarm kill switch/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Reset demo/ })).not.toBeInTheDocument()
  expect(mocks.disarm).not.toHaveBeenCalled(); expect(mocks.reset).not.toHaveBeenCalled()
})
it('restores legacy commands only after verified unavailable503', async () => {
  mocks.status.mockRejectedValue({ code: 'unavailable' }); mount()
  const disarm = await screen.findByRole('button', { name: /Disarm kill switch/ })
  expect(screen.getByRole('button', { name: /Reset demo/ })).toBeInTheDocument()
  await userEvent.click(disarm)
  await waitFor(() => expect(mocks.disarm).toHaveBeenCalledOnce())
})
it('does not poll controls while the palette is closed', () => {
  mount(false); expect(mocks.status).not.toHaveBeenCalled()
})
