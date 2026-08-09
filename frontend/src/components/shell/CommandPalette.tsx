import { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Dialog } from '@base-ui/react/dialog'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { RotateCcw, Search } from 'lucide-react'
import { api } from '@/lib/api'
import { NAV_ITEMS } from '@/lib/nav'
import { usePreferences } from '@/lib/preferences'
import { cn } from '@/lib/utils'

interface PaletteItem {
  key: string
  label: string
  hint: string
  run: () => void
}

/**
 * The command palette (⌘K / Ctrl+K): every screen plus the shell's
 * kernel write-actions, keyboard-driven. Arrow keys move, Enter runs,
 * Escape closes. A write action lands and then every screen refetches,
 * so the shell, the palette and the screens always agree.
 */
export function CommandPalette({
  open,
  onOpenChange,
  demoAttached,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  demoAttached: boolean
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { t } = usePreferences()
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  const invalidateAll = () => queryClient.invalidateQueries()

  const killSwitch = useMutation({
    mutationFn: (engage: boolean) => (engage ? api.engageKillSwitch() : api.disarmKillSwitch()),
    onSuccess: invalidateAll,
  })
  const resetDemo = useMutation({ mutationFn: api.demoReset, onSuccess: invalidateAll })

  const items = useMemo<PaletteItem[]>(() => {
    const screens: PaletteItem[] = NAV_ITEMS.map((item) => ({
      key: `nav:${item.path}`,
      label: t(item.labelKey),
      hint: t('palette.goToGroup', { group: t(item.groupKey) }),
      run: () => navigate(item.path),
    }))
    const actions: PaletteItem[] = [
      { key: 'ks-engage', label: t('palette.engageKill'), hint: t('palette.refuseOrders'), run: () => void killSwitch.mutate(true) },
      { key: 'ks-disarm', label: t('palette.disarmKill'), hint: t('palette.allowPaper'), run: () => void killSwitch.mutate(false) },
      ...(demoAttached
        ? [
            { key: 'demo-reset', label: t('palette.resetDemo'), hint: t('palette.restoreDemo'), run: () => void resetDemo.mutate() },
          ]
        : []),
    ]
    const needle = query.trim().toLowerCase()
    if (!needle) return [...screens, ...actions]
    return [...screens, ...actions].filter(
      (item) => item.label.toLowerCase().includes(needle) || item.hint.toLowerCase().includes(needle),
    )
  }, [query, navigate, killSwitch, resetDemo, demoAttached, t])

  function runItem(item: PaletteItem | undefined) {
    if (!item) return
    onOpenChange(false)
    setQuery('')
    item.run()
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-black/60 backdrop-blur-[2px]" />
        <Dialog.Popup className="fixed top-[15vh] left-1/2 z-50 w-[min(36rem,calc(100vw-2rem))] -translate-x-1/2 rounded-xl border border-border bg-popover text-popover-foreground shadow-2xl outline-none">
          <Dialog.Title className="sr-only">{t('palette.title')}</Dialog.Title>
          <div className="flex items-center gap-2 border-b border-border px-3 py-2.5">
            <Search className="size-4 shrink-0 text-muted-foreground" aria-hidden />
            <input
              ref={inputRef}
              className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
              placeholder={t('palette.placeholder')}
              value={query}
              onChange={(event) => {
                setQuery(event.target.value)
                setActiveIndex(0)
              }}
              onKeyDown={(event) => {
                if (event.key === 'ArrowDown') {
                  event.preventDefault()
                  setActiveIndex((index) => (items.length ? (index + 1) % items.length : 0))
                } else if (event.key === 'ArrowUp') {
                  event.preventDefault()
                  setActiveIndex((index) => (items.length ? (index - 1 + items.length) % items.length : 0))
                } else if (event.key === 'Enter') {
                  event.preventDefault()
                  runItem(items[activeIndex])
                }
              }}
            />
            <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-sans text-[10px] text-muted-foreground">
              esc
            </kbd>
          </div>
          <ul className="max-h-72 overflow-y-auto p-1.5" role="listbox" aria-label={t('palette.title')}>
            {items.length === 0 && (
              <li className="px-3 py-4 text-sm text-muted-foreground">{t('palette.noMatch', { query })}</li>
            )}
            {items.map((item, index) => (
              <li key={item.key} role="option" aria-selected={index === activeIndex}>
                <button
                  type="button"
                  className={cn(
                    'flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm outline-none',
                    index === activeIndex ? 'bg-accent text-accent-foreground' : 'text-foreground',
                  )}
                  onMouseEnter={() => setActiveIndex(index)}
                  onClick={() => runItem(item)}
                >
                  <span>{item.label}</span>
                  <span className="text-xs text-muted-foreground">{item.hint}</span>
                </button>
              </li>
            ))}
          </ul>
          <div className="flex items-center justify-between border-t border-border px-3 py-1.5 text-[10px] text-muted-foreground">
            <span>
              {demoAttached ? t('palette.demoAttached') : t('palette.operatorMode')}
            </span>
            <span className="flex items-center gap-1">
              <RotateCcw className="size-3" aria-hidden /> {t('palette.writesRefetch')}
            </span>
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
