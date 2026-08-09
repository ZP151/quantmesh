import type { ReactNode } from 'react'
import { Languages, Monitor, Moon, Sun } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Page } from '@/components/page'
import { usePreferences, type Locale, type ThemeMode } from '@/lib/preferences'

function SelectField({
  id,
  label,
  value,
  onChange,
  children,
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  children: ReactNode
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-9 w-full rounded-lg border border-input bg-background px-3 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 sm:max-w-sm"
      >
        {children}
      </select>
    </div>
  )
}

export function SettingsScreen() {
  const { locale, theme, resolvedTheme, setLocale, setTheme, t } = usePreferences()
  const activeTheme = theme === 'system' ? t('settings.themeSystem') : theme === 'light' ? t('settings.themeLight') : t('settings.themeDark')

  return (
    <Page title={t('settings.title')} description={t('settings.description')}>
      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Languages className="size-4" aria-hidden /> {t('settings.languageTitle')}
            </CardTitle>
            <CardDescription>{t('settings.languageDescription')}</CardDescription>
          </CardHeader>
          <CardContent>
            <SelectField
              id="interface-language"
              label={t('settings.languageLabel')}
              value={locale}
              onChange={(value) => setLocale(value as Locale)}
            >
              <option value="en">{t('settings.english')}</option>
              <option value="zh-CN">{t('settings.chinese')}</option>
            </SelectField>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              {resolvedTheme === 'dark' ? <Moon className="size-4" aria-hidden /> : <Sun className="size-4" aria-hidden />}
              {t('settings.themeTitle')}
            </CardTitle>
            <CardDescription>{t('settings.themeDescription')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <SelectField
              id="interface-theme"
              label={t('settings.themeLabel')}
              value={theme}
              onChange={(value) => setTheme(value as ThemeMode)}
            >
              <option value="system">{t('settings.themeSystem')}</option>
              <option value="light">{t('settings.themeLight')}</option>
              <option value="dark">{t('settings.themeDark')}</option>
            </SelectField>
            <p className="flex items-center gap-2 text-xs text-muted-foreground" role="status">
              <Monitor className="size-3.5" aria-hidden />
              {t('settings.themeCurrent', { theme: activeTheme })}
            </p>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">{t('settings.persistence')}</CardTitle>
            <CardDescription>{t('settings.persistenceDescription')}</CardDescription>
          </CardHeader>
        </Card>
      </div>
    </Page>
  )
}
