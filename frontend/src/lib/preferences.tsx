import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type Locale = 'en' | 'zh-CN'
export type ThemeMode = 'system' | 'light' | 'dark'
export type ResolvedTheme = 'light' | 'dark'

const STORAGE_KEY = 'quantmesh.preferences'

const messages = {
  en: {
    'nav.overview': 'Overview',
    'nav.markets': 'Markets',
    'nav.watchlist': 'Watchlist',
    'nav.cockpit': 'Live cockpit',
    'nav.prediction': 'Prediction markets',
    'nav.experiments': 'Experiments',
    'nav.promotions': 'Promotions',
    'nav.forecasts': 'Forecasts',
    'nav.paperOrder': 'Paper order',
    'nav.positions': 'Positions',
    'nav.orders': 'Orders',
    'nav.pnl': 'P&L',
    'nav.risk': 'Risk',
    'nav.connectors': 'Connectors',
    'nav.imports': 'Data imports',
    'nav.audit': 'Audit',
    'nav.killSwitch': 'Kill switch',
    'nav.enablement': 'Enablement',
    'nav.settings': 'Settings',
    'group.overview': 'Overview',
    'group.markets': 'Markets',
    'group.research': 'Research',
    'group.trading': 'Trading',
    'group.ops': 'Risk & ops',
    'shell.workstation': 'Workstation',
    'shell.settings': 'Settings',
    'shell.search': 'Search…',
    'shell.openSettings': 'Open global settings',
    'shell.killSwitchOff': 'Kill switch off',
    'shell.killSwitchOn': 'Kill switch on',
    'shell.demoReset': 'Reset demo',
    'shell.confirmReset': 'Confirm reset',
    'shell.demoSession': 'Deterministic paper session — every surface is synthetic and labeled, every order gated by the kernel.',
    'shell.liveSession': 'Live read-only session — venue freshness and provenance are explicit; paper writes remain kernel-gated.',
    'shell.operatorSession': 'Operator mode — no live or demo feed is attached.',
    'shell.footerDemo': 'Demo surfaces are synthetic and labeled.',
    'shell.footerLive': 'Venue feeds are read-only; freshness is shown per source.',
    'shell.footerOperator': 'No live or demo feed is attached.',
    'palette.title': 'Command palette',
    'palette.placeholder': 'Search screens and actions…',
    'palette.goToGroup': 'Go to {{group}}',
    'palette.engageKill': 'Engage kill switch',
    'palette.disarmKill': 'Disarm kill switch',
    'palette.refuseOrders': 'Refuse every paper and live order',
    'palette.allowPaper': 'Re-allow paper orders',
    'palette.resetDemo': 'Reset demo session',
    'palette.restoreDemo': 'Restore the pristine seeded root',
    'palette.noMatch': 'No screens or actions match “{{query}}”.',
    'palette.demoAttached': 'Paper demo session attached',
    'palette.operatorMode': 'Operator mode — no demo session',
    'palette.writesRefetch': 'writes refetch every screen',
    'settings.title': 'Global settings',
    'settings.description': 'Preferences are stored locally in this browser and apply across the workstation.',
    'settings.languageTitle': 'Language',
    'settings.languageDescription': 'Choose the language for navigation, shell controls and settings.',
    'settings.languageLabel': 'Interface language',
    'settings.english': 'English',
    'settings.chinese': '简体中文',
    'settings.themeTitle': 'UI theme',
    'settings.themeDescription': 'Choose a stable theme or follow the operating system appearance.',
    'settings.themeLabel': 'Appearance',
    'settings.themeSystem': 'System',
    'settings.themeLight': 'Light',
    'settings.themeDark': 'Dark',
    'settings.themeCurrent': 'Active theme: {{theme}}',
    'settings.persistence': 'Local-only preference',
    'settings.persistenceDescription': 'No preference is sent to a broker, venue or remote service.',
  },
  'zh-CN': {
    'nav.overview': '总览',
    'nav.markets': '市场',
    'nav.watchlist': '自选',
    'nav.cockpit': '实时驾驶舱',
    'nav.prediction': '预测市场',
    'nav.experiments': '实验',
    'nav.promotions': '策略晋级',
    'nav.forecasts': '预测报告',
    'nav.paperOrder': '模拟下单',
    'nav.positions': '持仓',
    'nav.orders': '订单',
    'nav.pnl': '盈亏',
    'nav.risk': '风险',
    'nav.connectors': '连接器',
    'nav.imports': '数据导入',
    'nav.audit': '审计',
    'nav.killSwitch': '熔断开关',
    'nav.enablement': '启用管理',
    'nav.settings': '设置',
    'group.overview': '总览',
    'group.markets': '市场',
    'group.research': '研究',
    'group.trading': '交易',
    'group.ops': '风险与运维',
    'shell.workstation': '工作站',
    'shell.settings': '设置',
    'shell.search': '搜索…',
    'shell.openSettings': '打开全局设置',
    'shell.killSwitchOff': '熔断关闭',
    'shell.killSwitchOn': '熔断开启',
    'shell.demoReset': '重置演示',
    'shell.confirmReset': '确认重置',
    'shell.demoSession': '确定性模拟会话——所有界面均为已标注的合成数据，所有订单均受内核约束。',
    'shell.liveSession': '实时只读会话——数据新鲜度与来源明确，模拟写入仍受内核约束。',
    'shell.operatorSession': '操作员模式——当前未连接实时或演示数据源。',
    'shell.footerDemo': '演示界面使用已标注的合成数据。',
    'shell.footerLive': '市场连接器只读，每个来源显示独立的新鲜度。',
    'shell.footerOperator': '当前未连接实时或演示数据源。',
    'palette.title': '命令面板',
    'palette.placeholder': '搜索界面和操作…',
    'palette.goToGroup': '前往{{group}}',
    'palette.engageKill': '开启熔断开关',
    'palette.disarmKill': '关闭熔断开关',
    'palette.refuseOrders': '拒绝所有模拟和实时订单',
    'palette.allowPaper': '重新允许模拟订单',
    'palette.resetDemo': '重置演示会话',
    'palette.restoreDemo': '恢复初始种子状态',
    'palette.noMatch': '没有匹配“{{query}}”的界面或操作。',
    'palette.demoAttached': '已连接模拟演示会话',
    'palette.operatorMode': '操作员模式——未连接演示会话',
    'palette.writesRefetch': '写入后刷新所有界面',
    'settings.title': '全局设置',
    'settings.description': '偏好设置仅保存在当前浏览器，并应用于整个工作站。',
    'settings.languageTitle': '语言',
    'settings.languageDescription': '选择导航、工作站控制和设置界面的语言。',
    'settings.languageLabel': '界面语言',
    'settings.english': 'English',
    'settings.chinese': '简体中文',
    'settings.themeTitle': '界面主题',
    'settings.themeDescription': '选择固定主题，或跟随操作系统的外观设置。',
    'settings.themeLabel': '外观',
    'settings.themeSystem': '跟随系统',
    'settings.themeLight': '浅色',
    'settings.themeDark': '深色',
    'settings.themeCurrent': '当前主题：{{theme}}',
    'settings.persistence': '仅本地偏好',
    'settings.persistenceDescription': '偏好不会发送给券商、交易平台或远程服务。',
  },
} as const

export type MessageKey = keyof typeof messages.en
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
