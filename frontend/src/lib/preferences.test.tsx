import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act } from 'react'
import { PreferencesProvider, usePreferences } from './preferences'

function Probe() {
  const { locale, theme, resolvedTheme, setLocale, setTheme, t } = usePreferences()
  return (
    <div>
      <output data-testid="locale">{locale}</output>
      <output data-testid="theme">{theme}</output>
      <output data-testid="resolved-theme">{resolvedTheme}</output>
      <output>{t('settings.title')}</output>
      <button type="button" onClick={() => setLocale('zh-CN')}>中文</button>
      <button type="button" onClick={() => setTheme('light')}>浅色</button>
    </div>
  )
}

describe('global preferences', () => {
  beforeEach(() => {
    window.localStorage.clear()
    document.documentElement.className = ''
    document.documentElement.lang = 'en'
    document.documentElement.style.colorScheme = ''
  })

  it('starts in the dark English workstation and applies document metadata', () => {
    render(
      <PreferencesProvider>
        <Probe />
      </PreferencesProvider>,
    )

    expect(screen.getByTestId('locale')).toHaveTextContent('en')
    expect(screen.getByTestId('theme')).toHaveTextContent('dark')
    expect(screen.getByTestId('resolved-theme')).toHaveTextContent('dark')
    expect(screen.getByText('Global settings')).toBeInTheDocument()
    expect(document.documentElement).toHaveClass('dark')
    expect(document.documentElement.lang).toBe('en')
    expect(document.documentElement.style.colorScheme).toBe('dark')
  })

  it('updates and persists language and theme changes locally', () => {
    render(
      <PreferencesProvider>
        <Probe />
      </PreferencesProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: '中文' }))
    fireEvent.click(screen.getByRole('button', { name: '浅色' }))

    expect(screen.getByTestId('locale')).toHaveTextContent('zh-CN')
    expect(screen.getByTestId('theme')).toHaveTextContent('light')
    expect(screen.getByTestId('resolved-theme')).toHaveTextContent('light')
    expect(screen.getByText('全局设置')).toBeInTheDocument()
    expect(document.documentElement).not.toHaveClass('dark')
    expect(document.documentElement.lang).toBe('zh-CN')
    expect(JSON.parse(window.localStorage.getItem('quantmesh.preferences') ?? '{}')).toEqual({
      locale: 'zh-CN',
      theme: 'light',
    })
  })

  it('resolves system theme and responds to operating-system changes', () => {
    let listener: (() => void) | undefined
    const media = {
      matches: true,
      addEventListener: (_event: string, callback: () => void) => {
        listener = callback
      },
      removeEventListener: vi.fn(),
    }
    vi.stubGlobal('matchMedia', vi.fn(() => media))
    window.localStorage.setItem('quantmesh.preferences', JSON.stringify({ locale: 'en', theme: 'system' }))

    render(
      <PreferencesProvider>
        <Probe />
      </PreferencesProvider>,
    )

    expect(screen.getByTestId('resolved-theme')).toHaveTextContent('dark')
    expect(document.documentElement).toHaveClass('dark')

    media.matches = false
    act(() => listener?.())

    expect(screen.getByTestId('resolved-theme')).toHaveTextContent('light')
    expect(document.documentElement).not.toHaveClass('dark')
    vi.unstubAllGlobals()
  })
})
