import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { PreferencesProvider } from '@/lib/preferences'
import { api, ApiError, type CatalogEntry, type CatalogLineage } from '@/lib/api'
import { DataCatalogScreen } from './DataCatalog'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      dataCatalog: vi.fn(),
      dataCatalogLineage: vi.fn(),
    },
  }
})

const mocked = vi.mocked(api)

const FAILED_MANIFEST = 'a'.repeat(64)
const PARENT_MANIFEST = 'b'.repeat(64)

function entry(overrides: Partial<CatalogEntry> = {}): CatalogEntry {
  return {
    adjustment_policy: 'split-and-dividend-adjusted',
    calendar_version: 'XNYS-2026a',
    canonical_instrument: 'moomoo:AAPL',
    compatibility_revision: 2,
    current_manifest_id: FAILED_MANIFEST,
    data_kind: 'bars',
    dataset_id: 'moomoo-aapl-1d',
    entitlement: 'available',
    event_end: '2026-08-13T20:00:00Z',
    event_start: '2026-08-01T13:30:00Z',
    interval: '1d',
    is_current: true,
    knowledge_end: '2026-08-13T20:05:00Z',
    knowledge_start: '2026-08-01T13:35:00Z',
    latest_checkpoint: {
      attempt: 1,
      generation: 4,
      job_id: 'c'.repeat(64),
      last_complete_source_event: '2026-08-13T20:00:00Z',
      provider_cursor: 'cursor-42',
      quality_report_id: 'd'.repeat(64),
      run_id: 'e'.repeat(64),
      updated_at: '2026-08-13T20:06:00Z',
    },
    layer: 'adjusted',
    manifest_id: FAILED_MANIFEST,
    object_digests: ['f'.repeat(64)],
    parent_manifest_ids: [PARENT_MANIFEST],
    provider_access: 'authenticated-read-only',
    provider_id: 'moomoo',
    quality: {
      duplicate_count: 0,
      evaluated_at: '2026-08-13T20:06:00Z',
      evaluation_id: '1'.repeat(64),
      expected_count: 9,
      freshness_seconds: 360,
      gap_count: 1,
      hash_mismatch_count: 0,
      issue_codes: ['coverage-gap'],
      latency_seconds: 12,
      observed_count: 8,
      order_violation_count: 0,
      overlap_conflict_count: 0,
      pagination_terminal: true,
      policy_id: '2'.repeat(64),
      report_id: 'd'.repeat(64),
      schema_mismatch_count: 0,
      source_rights_known: true,
      status: 'fail',
      synthetic_row_count: 0,
      unavailable_reason: null,
    },
    row_count: 8,
    session_policy: 'regular',
    source_rights_id: 'rights-moomoo-read-only',
    trusted_for_research: false,
    ...overrides,
  }
}

function renderScreen(locale: 'en' | 'zh-CN' = 'en') {
  window.localStorage.setItem('quantmesh.preferences', JSON.stringify({ locale, theme: 'dark' }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <PreferencesProvider>
        <DataCatalogScreen />
      </PreferencesProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  mocked.dataCatalog.mockResolvedValue([entry()])
  mocked.dataCatalogLineage.mockResolvedValue({
    entry: entry(),
    ancestors: [entry({
      adjustment_policy: null,
      current_manifest_id: FAILED_MANIFEST,
      is_current: false,
      layer: 'raw',
      manifest_id: PARENT_MANIFEST,
      parent_manifest_ids: [],
      quality: null,
    })],
  } satisfies CatalogLineage)
})

describe('DataCatalogScreen', () => {
  it('shows failed quality and lineage without presenting data as usable', async () => {
    const user = userEvent.setup()
    renderScreen()

    expect((await screen.findAllByText('Failed')).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(FAILED_MANIFEST)).toBeVisible()
    expect(screen.queryByText('Ready for research')).not.toBeInTheDocument()

    const disclosure = screen.getByRole('button', { name: 'Show lineage' })
    disclosure.focus()
    await user.keyboard('{Enter}')

    await waitFor(() => expect(mocked.dataCatalogLineage).toHaveBeenCalledWith(FAILED_MANIFEST))
    const detail = await screen.findByTestId(`catalog-lineage-${FAILED_MANIFEST}`)
    expect(within(detail).getByText(PARENT_MANIFEST)).toBeVisible()
    expect(within(detail).getByText('coverage-gap')).toBeVisible()
    expect(within(detail).getByText('8 / 9')).toBeVisible()
    for (const label of [
      'Evaluation ID',
      'Report ID',
      'Policy ID',
      'Freshness',
      'Latency',
      'Order violations',
      'Overlap conflicts',
      'Synthetic rows',
      'Pagination terminal',
      'Source rights known',
      'Unavailable reason',
      'Checkpoint job ID',
      'Checkpoint run ID',
      'Attempt / generation',
      'Provider cursor',
      'Last complete source event',
      'Bound quality report',
    ]) {
      expect(within(detail).getByText(label)).toBeVisible()
    }
    expect(screen.getByText('Knowledge time')).toBeVisible()
    expect(
      screen.getAllByText('e'.repeat(64), { exact: false })
        .some((node) => node.closest('dd')?.classList.contains('break-all')),
    ).toBe(true)
  })

  it('keeps unavailable, not-due, failed and stale states explicit', async () => {
    mocked.dataCatalog.mockResolvedValue([
      entry({ manifest_id: 'failed', current_manifest_id: 'failed' }),
      entry({
        manifest_id: 'not-due',
        current_manifest_id: 'not-due',
        quality: { ...entry().quality!, status: 'not-due', issue_codes: [] },
      }),
      entry({ manifest_id: 'unavailable', current_manifest_id: 'unavailable', quality: null }),
      entry({
        manifest_id: 'stale',
        current_manifest_id: 'stale',
        quality: { ...entry().quality!, status: 'fail', issue_codes: ['freshness-sla'] },
      }),
    ])

    renderScreen()

    expect((await screen.findAllByText('Failed')).length).toBe(2)
    expect(screen.getByText('Not due')).toBeVisible()
    expect(screen.getByText('Unavailable')).toBeVisible()
    expect(screen.getByText('Stale')).toHaveClass('border-amber-500/60')
  })

  it('renders every trust state in Simplified Chinese', async () => {
    mocked.dataCatalog.mockResolvedValue([
      entry(),
      entry({ manifest_id: 'not-due', quality: { ...entry().quality!, status: 'not-due' } }),
      entry({ manifest_id: 'unavailable', quality: null }),
      entry({
        manifest_id: 'stale',
        quality: { ...entry().quality!, status: 'fail', issue_codes: ['freshness-sla'] },
      }),
    ])

    renderScreen('zh-CN')

    expect(await screen.findByRole('heading', { name: '可信数据目录' })).toBeVisible()
    expect((await screen.findAllByText('失败')).length).toBe(2)
    expect(screen.getByText('尚未到期')).toBeVisible()
    expect(screen.getByText('不可用')).toBeVisible()
    expect(screen.getByText('已过期')).toBeVisible()
  })

  it('shows a typed unavailable state when the catalog API is not attached', async () => {
    mocked.dataCatalog.mockRejectedValue(new ApiError(404, 'no trusted data catalog is attached'))
    renderScreen()

    expect(await screen.findByText('Trusted data catalog unavailable')).toBeVisible()
    expect(screen.getByText('no trusted data catalog is attached')).toBeVisible()
  })

  it('shows an instructive empty state', async () => {
    mocked.dataCatalog.mockResolvedValue([])
    renderScreen()

    expect(await screen.findByText('No cataloged datasets')).toBeVisible()
    expect(screen.getByText(/resulting state may pass, fail, remain not due or be unavailable/)).toBeVisible()
  })
})
