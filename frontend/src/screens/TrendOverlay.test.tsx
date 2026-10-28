import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { PreferencesProvider } from '@/lib/preferences'
import fixtures from '@/test/fixtures/trend-overlay.json'

const mocks = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/lib/trend-overlay-api', () => ({
  trendCases: ['campaign', 'exit-cap', 'cash-cap'], trendOverlayApi: { get: mocks.get },
}))

async function open(locale = 'en') {
  const modules = import.meta.glob('./TrendOverlay.tsx')
  expect(modules['./TrendOverlay.tsx'], 'trend inspector is implemented').toBeDefined()
  const { TrendOverlayScreen } = await modules['./TrendOverlay.tsx']() as typeof import('./TrendOverlay')
  localStorage.setItem('quantmesh.preferences', JSON.stringify({ locale, theme: 'dark' }))
  return render(<MemoryRouter><PreferencesProvider><TrendOverlayScreen /></PreferencesProvider></MemoryRouter>)
}

beforeEach(() => {
  localStorage.clear()
  window.matchMedia = vi.fn().mockReturnValue({ matches: true, addEventListener() {}, removeEventListener() {} })
  vi.clearAllMocks()
  mocks.get.mockImplementation(async (id: keyof typeof fixtures) => structuredClone(fixtures[id]))
})

describe('fixed synthetic trend step inspector', () => {
  it('defaults mobile focus to overlay on and keeps a direct comparison switch', async () => {
    await open()
    await screen.findByText('Step 1 of 5')
    const on = screen.getByRole('button', { name: 'Overlay on' })
    const off = screen.getByRole('button', { name: 'Overlay off' })
    expect(on).toHaveAttribute('aria-pressed', 'true')
    expect(off).toHaveAttribute('aria-pressed', 'false')
    await userEvent.click(off)
    expect(off).toHaveAttribute('aria-pressed', 'true')
    expect(on).toHaveAttribute('aria-pressed', 'false')
    await userEvent.click(screen.getByRole('button', { name: 'Next step' }))
    expect(off).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('Step 2 of 5')).toBeVisible()
  })
  it('keeps the ready trace when the selected case is selected again', async () => {
    await open()
    await screen.findByText('Step 1 of 5')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Fixed case' }), 'campaign')
    expect(screen.getByText('Step 1 of 5')).toBeVisible()
    expect(mocks.get).toHaveBeenCalledTimes(1)
  })
  it('keeps synthetic boundaries visible and compares one selected step without strategy math in UI', async () => {
    await open()
    await screen.findByRole('heading', { name: 'Overlay on' })
    expect(screen.getByText(/Not a real-data backtest or profitability evidence/)).toBeVisible()
    expect(screen.getByText(/Does not authorize Paper/)).toBeVisible()
    expect(screen.getByRole('combobox', { name: 'Fixed case' })).toHaveValue('campaign')
    expect(screen.getByRole('button', { name: 'Previous step' })).toBeDisabled()
    expect(screen.getByText('Step 1 of 5')).toBeVisible()
    const on = screen.getByRole('region', { name: 'Overlay on' })
    expect(within(on).getByText('0 → 333')).toBeVisible()
    expect(within(on).getByText('100000')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Next step' }))
    expect(screen.getByText('Step 2 of 5')).toBeVisible()
    expect(within(on).getByText('Add shares')).toBeVisible()
    expect(within(on).getByText('333 → 366')).toBeVisible()
    expect(within(on).getByText('33 / 33 / 33')).toBeVisible()
    expect(screen.getByText(/Cash is supplied for this step/)).toBeVisible()
    expect(screen.queryByRole('button', { name: /place|submit|paper order/i })).not.toBeInTheDocument()
  })

  it('changes cases and explains persistent partial exits and cash constraints', async () => {
    await open()
    const select = screen.getByRole('combobox', { name: 'Fixed case' })
    await screen.findByText('Step 1 of 5')
    await userEvent.selectOptions(select, 'exit-cap')
    await screen.findByText('Step 1 of 3')
    expect(screen.getAllByText('Prior-20-session volume cap').length).toBe(2)
    await userEvent.click(screen.getByRole('button', { name: 'Next step' }))
    expect(screen.getAllByText('Trend exit').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Hold trend signal').length).toBe(2)
    expect(screen.getAllByText('15 → 5').length).toBe(2)
    await userEvent.selectOptions(select, 'cash-cap')
    await screen.findByText('Step 1 of 2')
    expect(screen.getByText('Spendable cash limit')).toBeVisible()
    expect(within(screen.getByRole('region', { name: 'Overlay on' })).getByText('100')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Next step' }))
    expect(screen.getByText('Post-fee concentration limit')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Next step' })).toBeDisabled()
  })

  it('does not retain old case results after a failure and supports explicit retry', async () => {
    await open()
    await screen.findByText('Step 1 of 5')
    mocks.get.mockRejectedValueOnce(new Error('offline'))
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Fixed case' }), 'cash-cap')
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not read this fixed case')
    expect(screen.queryByText('Step 1 of 5')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Read case again' }))
    await screen.findByText('Step 1 of 2')
  })

  it('ignores stale responses when cases change quickly', async () => {
    let resolveOld!: (value: typeof fixtures.campaign) => void
    mocks.get.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
    await open()
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Fixed case' }), 'exit-cap')
    await screen.findByText('Step 1 of 3')
    resolveOld(fixtures.campaign)
    await waitFor(() => expect(screen.getByText('Step 1 of 3')).toBeVisible())
    expect(screen.queryByText('Step 1 of 5')).not.toBeInTheDocument()
  })

  it('localizes the core operation and discloses complete original evidence on request', async () => {
    await open('zh-CN')
    await screen.findByRole('heading', { name: '开启分批仓位规则' })
    expect(screen.getByText(/合成规则实验/)).toBeVisible()
    expect(screen.getByText(/不授予 Paper/)).toBeVisible()
    expect(screen.getByRole('combobox', { name: '固定案例' })).toBeVisible()
    await userEvent.click(screen.getByText('完整规则与证据'))
    expect(screen.getByText(fixtures.campaign.trace_sha256)).toBeVisible()
    expect(screen.getByRole('link', { name: '下载完整合成轨迹 JSON' })).toHaveAttribute('download', 'trend-campaign.json')
  })
})
