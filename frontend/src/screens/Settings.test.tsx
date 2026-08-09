import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { PreferencesProvider } from '@/lib/preferences'
import { SettingsScreen } from './Settings'

describe('SettingsScreen', () => {
  beforeEach(() => {
    window.localStorage.clear()
    document.documentElement.className = 'dark'
  })

  it('exposes global language and theme controls', () => {
    render(
      <PreferencesProvider>
        <SettingsScreen />
      </PreferencesProvider>,
    )

    expect(screen.getByRole('heading', { name: 'Global settings' })).toBeInTheDocument()
    expect(screen.getByLabelText('Interface language')).toHaveValue('en')
    expect(screen.getByLabelText('Appearance')).toHaveValue('dark')

    fireEvent.change(screen.getByLabelText('Interface language'), { target: { value: 'zh-CN' } })
    fireEvent.change(screen.getByLabelText('外观'), { target: { value: 'light' } })

    expect(screen.getByRole('heading', { name: '全局设置' })).toBeInTheDocument()
    expect(screen.getByLabelText('界面语言')).toHaveValue('zh-CN')
    expect(screen.getByLabelText('外观')).toHaveValue('light')
  })
})
