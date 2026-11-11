import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { PreferencesProvider, usePreferences } from '@/lib/preferences'
import { ResearchJobsScreen } from './ResearchJobs'

vi.mock('./NativeDailyPanel', () => ({ NativeDailyPanel: () => <p data-testid="native-panel" /> }))
vi.mock('./SpyReplayPanel', () => ({ SpyReplayPanel: () => <p data-testid="replay-panel" /> }))
vi.mock('./VnpyFixturePanel', () => ({ VnpyFixturePanel: () => <p data-testid="vnpy-panel" /> }))

function LocaleControl() {
  const { setLocale } = usePreferences()
  return <button onClick={() => setLocale('en')}>English</button>
}

beforeEach(() => {
  localStorage.clear()
  localStorage.setItem('quantmesh.preferences', JSON.stringify({ locale: 'zh-CN', theme: 'dark' }))
  history.replaceState({ retained: true }, '', '/app/research/jobs?engine=native-daily-v2&native_job=original-id&view=review#report')
})

it('uses the selected language for research chrome and switches without losing the saved context', async () => {
  const before = location.href
  render(<PreferencesProvider><LocaleControl /><ResearchJobsScreen /></PreferencesProvider>)
  expect(screen.getByLabelText('研究方式')).toHaveValue('native-daily-v2')
  expect(screen.getByRole('link', { name: '趋势规则实验' })).toHaveAttribute('href', '/app/research/trend-overlay')
  expect(screen.getByRole('link', { name: '导入日线 CSV 并规划协议' })).toBeVisible()
  expect(screen.getByRole('option', { name: '固定原生日线研究' })).toBeInTheDocument()
  expect(screen.queryByText('Trend rule experiment · 趋势规则实验')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'English' }))
  expect(screen.getByLabelText('Research engine')).toHaveValue('native-daily-v2')
  expect(screen.getByRole('link', { name: 'Trend rule experiment' })).toBeVisible()
  expect(screen.queryByRole('link', { name: /趋势规则实验/ })).not.toBeInTheDocument()
  expect(location.href).toBe(before)
  expect(history.state).toEqual({ retained: true })
  expect(screen.getByTestId('native-panel')).toBeInTheDocument()
})
