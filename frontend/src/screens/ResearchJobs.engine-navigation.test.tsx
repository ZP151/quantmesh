import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { ResearchJobsScreen } from './ResearchJobs'

vi.mock('./NativeDailyPanel', () => ({ NativeDailyPanel: () => <p>Native panel</p> }))
vi.mock('./SpyReplayPanel', () => ({ SpyReplayPanel: () => <p>Replay panel</p> }))
vi.mock('./VnpyFixturePanel', () => ({ VnpyFixturePanel: () => <p>Fixture panel</p> }))
vi.mock('@/lib/api', () => ({ api: { researchJobOptions: vi.fn().mockRejectedValue(new Error('offline')) } }))

beforeEach(() => {
  localStorage.clear()
  history.replaceState(null, '', '/app/research/jobs')
})

it('keeps the selected engine and retained job query on reload without submission', async () => {
  history.replaceState({ retained: true }, '', '/app/research/jobs?native_job=saved-id&view=review#report')
  const first = render(<ResearchJobsScreen />)
  await userEvent.selectOptions(screen.getByLabelText('Research engine'), 'vnpy')
  const url = new URL(location.href)
  expect(url.searchParams.get('engine')).toBe('vnpy')
  expect(url.searchParams.get('native_job')).toBe('saved-id')
  expect(url.searchParams.get('view')).toBe('review')
  expect(url.hash).toBe('#report')
  expect(history.state).toEqual({ retained: true })
  first.unmount()
  render(<ResearchJobsScreen />)
  expect(screen.getByLabelText('Research engine')).toHaveValue('vnpy')
  expect(screen.getByText('Fixture panel')).toBeInTheDocument()
})

it.each(['baseline', 'vnpy', 'spy-replay', 'native-daily-v2'])('restores explicit %s before legacy job inference', async engine => {
  history.replaceState(null, '', `/app/research/jobs?engine=${engine}&native_job=retained`)
  render(<ResearchJobsScreen />)
  expect(screen.getByLabelText('Research engine')).toHaveValue(engine)
  if (engine === 'baseline') await screen.findByText(/Research service unavailable/)
})

it.each([['native_job', 'native-daily-v2'], ['spy_job', 'spy-replay']])('retains legacy %s reopening', (key, engine) => {
  history.replaceState(null, '', `/app/research/jobs?${key}=retained`)
  render(<ResearchJobsScreen />)
  expect(screen.getByLabelText('Research engine')).toHaveValue(engine)
})
