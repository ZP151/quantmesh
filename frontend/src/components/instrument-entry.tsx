import { useId, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { scenarioLabPath, supportedLabTicker } from '@/lib/instrument-route'
import { usePreferences } from '@/lib/preferences'

/** Bounded local discovery; submitting never contacts a provider or places an order. */
export function InstrumentEntry() {
  const { t } = usePreferences()
  const navigate = useNavigate()
  const id = useId()
  const [ticker, setTicker] = useState('')
  const [unsupported, setUnsupported] = useState(false)
  return (
    <form className="space-y-2 border-b border-border pb-4" onSubmit={(event) => {
      event.preventDefault()
      const symbol = supportedLabTicker(ticker)
      setUnsupported(symbol === null)
      if (symbol !== null) navigate(scenarioLabPath(symbol))
    }}>
      <Label htmlFor={id}>{t('lab.ticker')}</Label>
      <div className="flex flex-wrap items-center gap-2">
        <Input
          aria-describedby={`${id}-help`}
          aria-invalid={unsupported}
          autoCapitalize="characters"
          autoComplete="off"
          className="min-w-0 flex-1 basis-40 font-mono"
          id={id}
          maxLength={16}
          onChange={(event) => { setTicker(event.target.value); setUnsupported(false) }}
          placeholder="AAPL / NVDA"
          value={ticker}
        />
        <Button type="submit">{t('lab.openChart')}</Button>
      </div>
      <p className="text-xs text-muted-foreground" id={`${id}-help`} role="status">
        {t(unsupported ? 'lab.unsupported' : 'lab.supported')}
      </p>
    </form>
  )
}
