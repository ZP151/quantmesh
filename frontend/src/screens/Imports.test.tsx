import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ImportsScreen } from './Imports'
import type { ImportPreview } from '@/lib/api'
import { PreferencesProvider } from '@/lib/preferences'

// The screen talks to the kernel through the api client; the unit
// surface mocks it so the mapping gate, required-field enforcement and
// the committed list render against deterministic payloads.
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      imports: vi.fn(),
      importUpload: vi.fn(),
      importCommit: vi.fn(),
    },
  }
})

import { api } from '@/lib/api'

const mocked = vi.mocked(api)

const PREVIEW: ImportPreview = {
  session_id: 'abc123',
  filename: 'smoke.csv',
  format: 'CSV',
  rows: 3,
  columns: [
    { name: 'timestamp', inferred: 'datetime', samples: ['2026-08-01T00:00:00Z'] },
    { name: 'open', inferred: 'number', samples: [100] },
    { name: 'high', inferred: 'number', samples: [101] },
    { name: 'low', inferred: 'number', samples: [99] },
    { name: 'close', inferred: 'number', samples: [100.5] },
  ],
  preview: [{ timestamp: '2026-08-01T00:00:00Z', open: 100, high: 101, low: 99, close: 100.5 }],
  suggested_mapping: {
    timestamp: 'timestamp',
    open: 'open',
    high: 'high',
    low: 'low',
    close: 'close',
  },
}

function renderScreen() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <PreferencesProvider>
        <ImportsScreen />
      </PreferencesProvider>
    </QueryClientProvider>,
  )
}

/** The upload input is an unlabeled file picker inside the card. */
function uploadInput(container: HTMLElement): HTMLInputElement {
  const input = container.querySelector('input[type="file"]')
  if (!(input instanceof HTMLInputElement)) throw new Error('file input not found')
  return input
}

beforeEach(() => {
  vi.clearAllMocks()
  mocked.imports.mockResolvedValue([])
})

describe('ImportsScreen', () => {
  it('shows the empty notice when no datasets are committed', async () => {
    renderScreen()
    await waitFor(() =>
      expect(screen.getByText('No operator-imported datasets yet', { exact: false })).toBeInTheDocument(),
    )
  })

  it('lists committed datasets from the server', async () => {
    mocked.imports.mockResolvedValue([
      {
        dataset: 'my-data',
        source: 'operator-import',
        license: 'operator-import',
        revision: 1,
        generated_at: '2026-08-09T00:00:00+00:00',
        series: 1,
        rows: 4,
        start: '2026-08-01T00:00:00+00:00',
        end: '2026-08-04T00:00:00+00:00',
      },
    ])
    renderScreen()
    await waitFor(() => expect(screen.getByText('my-data')).toBeInTheDocument())
    expect(screen.getByText(/4 rows/)).toBeInTheDocument()
  })

  it('auto-fills the suggested mapping and gates the commit on dataset + symbol', async () => {
    mocked.importUpload.mockResolvedValue(PREVIEW)
    const { container } = renderScreen()

    fireEvent.change(uploadInput(container), {
      target: { files: [new File(['x'], 'smoke.csv', { type: 'text/csv' })] },
    })

    await waitFor(() => expect(mocked.importUpload).toHaveBeenCalledTimes(1))

    // The suggested mapping lands in the selects.
    await waitFor(() => {
      const commit = screen.getByRole('button', {
        name: /Commit dataset \(3 rows\)/,
      }) as HTMLButtonElement
      // Dataset name and symbol are still empty -> disabled.
      expect(commit.disabled).toBe(true)
    })

    fireEvent.change(screen.getByLabelText('Dataset name'), { target: { value: 'unit-data' } })
    fireEvent.change(screen.getByLabelText('Symbol'), { target: { value: 'UNIT' } })

    const commit = screen.getByRole('button', {
      name: /Commit dataset \(3 rows\)/,
    }) as HTMLButtonElement
    expect(commit.disabled).toBe(false)
  })

  it('flags a required field whose mapping was cleared', async () => {
    mocked.importUpload.mockResolvedValue(PREVIEW)
    const { container } = renderScreen()

    fireEvent.change(uploadInput(container), {
      target: { files: [new File(['x'], 'smoke.csv', { type: 'text/csv' })] },
    })
    await waitFor(() => expect(mocked.importUpload).toHaveBeenCalledTimes(1))

    const timestampSelect = screen.getByLabelText(/^timestamp/) as HTMLSelectElement
    fireEvent.change(timestampSelect, { target: { value: '' } })

    await waitFor(() =>
      expect(
        screen.getByText('Required fields without a column: timestamp'),
      ).toBeInTheDocument(),
    )
    const commit = screen.getByRole('button', {
      name: /Commit dataset/,
    }) as HTMLButtonElement
    expect(commit.disabled).toBe(true)
  })
})
