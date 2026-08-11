import { useState } from 'react'
import { X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { usePreferences } from '@/lib/preferences'

const PEER_PATTERN = /^[a-z][a-z0-9_-]*:[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/

export function ComparisonPicker({
  onChange,
  primary,
  selected,
}: {
  onChange: (peers: string[]) => void
  primary: string
  selected: readonly string[]
}) {
  const { t } = usePreferences()
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)
  const full = selected.length >= 3

  const add = () => {
    const peer = value.trim()
    if (!PEER_PATTERN.test(peer) || peer === primary || selected.includes(peer)) {
      setError(t('screen.workspace.compareInvalid'))
      return
    }
    if (full) return
    onChange([...selected, peer])
    setValue('')
    setError(null)
  }

  return (
    <div className="space-y-2 px-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          {t('screen.workspace.comparisons')}
        </h3>
        <span className="font-mono text-[10px] text-muted-foreground">{selected.length} / 3</span>
      </div>
      <div className="flex gap-2">
        <Input
          aria-label={t('screen.workspace.compareInput')}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') add()
          }}
          placeholder="moomoo:AAPL"
          value={value}
        />
        <Button disabled={full || value.trim().length === 0} onClick={add} type="button" variant="outline">
          {t('screen.workspace.compareAdd')}
        </Button>
      </div>
      {error !== null && <p className="text-xs text-destructive">{error}</p>}
      <div className="flex flex-wrap gap-1.5">
        {selected.map((peer) => (
          <span key={peer} className="inline-flex items-center gap-1 border border-border px-2 py-1 font-mono text-[10px]">
            {peer}
            <button
              aria-label={t('screen.workspace.compareRemove', { peer })}
              className="text-muted-foreground hover:text-foreground"
              onClick={() => onChange(selected.filter((item) => item !== peer))}
              type="button"
            >
              <X className="size-3" aria-hidden />
            </button>
          </span>
        ))}
      </div>
    </div>
  )
}
