import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { messages, type MessageKey } from './messages'

export type Locale = 'en' | 'zh-CN'
export type ThemeMode = 'system' | 'light' | 'dark'
export type ResolvedTheme = 'light' | 'dark'

const STORAGE_KEY = 'quantmesh.preferences'

type PreferenceState = { locale: Locale; theme: ThemeMode }
type PreferenceContextValue = PreferenceState & {
  setLocale: (locale: Locale) => void
  setTheme: (theme: ThemeMode) => void
  resolvedTheme: ResolvedTheme
  t: (key: MessageKey, vars?: Record<string, string>) => string
}

const PreferencesContext = createContext<PreferenceContextValue | null>(null)

function getSystemTheme(): ResolvedTheme {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light'
}

function readInitialPreferences(): PreferenceState {
  if (typeof window === 'undefined') return { locale: 'en', theme: 'dark' }
  try {
    const stored = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? 'null') as Partial<PreferenceState> | null
    return {
      locale: stored?.locale === 'zh-CN' ? 'zh-CN' : 'en',
      theme: stored?.theme === 'light' || stored?.theme === 'system' ? stored.theme : 'dark',
    }
  } catch {
    return { locale: 'en', theme: 'dark' }
  }
}

function persistPreferences(preferences: PreferenceState) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences))
  } catch {
    // Private browsing or a locked-down browser can reject localStorage.
  }
}

export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [preferences, setPreferences] = useState<PreferenceState>(readInitialPreferences)
  const resolvedTheme: ResolvedTheme = preferences.theme === 'system' ? getSystemTheme() : preferences.theme

  useEffect(() => {
    document.documentElement.classList.toggle('dark', resolvedTheme === 'dark')
    document.documentElement.lang = preferences.locale
    document.documentElement.style.colorScheme = resolvedTheme
    persistPreferences(preferences)
  }, [preferences, resolvedTheme])

  useEffect(() => {
    if (preferences.theme !== 'system') return
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => setPreferences((current) => ({ ...current }))
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [preferences.theme])

  const value = useMemo<PreferenceContextValue>(() => ({
    ...preferences,
    resolvedTheme,
    setLocale: (locale) => setPreferences((current) => ({ ...current, locale })),
    setTheme: (theme) => setPreferences((current) => ({ ...current, theme })),
    t: (key, vars) => {
      let text: string = messages[preferences.locale][key] ?? messages.en[key]
      for (const [name, replacement] of Object.entries(vars ?? {})) {
        text = text.replaceAll(`{{${name}}}`, replacement)
      }
      return text
    },
  }), [preferences, resolvedTheme])

  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>
}

export function usePreferences() {
  const value = useContext(PreferencesContext)
  if (!value) throw new Error('usePreferences must be used inside PreferencesProvider')
  return value
}
