import type { DecisionPacket } from '@/lib/api'
import { moneyPrecise } from '@/lib/format'
import { usePreferences } from '@/lib/preferences'

const scenarioOrder = ['bull', 'base', 'bear'] as const

export function ScenarioEvidence({ packet }: { packet: DecisionPacket }) {
  const { locale, t } = usePreferences()
  const scenarios = scenarioOrder.map((kind) => packet.scenarios.find((item) => item.kind === kind)!)

  return (
    <section className="min-w-0 space-y-3 px-3" aria-label={t('screen.workspace.scenarios')}>
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          {t('screen.workspace.scenarios')}
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          {t('screen.workspace.scenarioAuthority')}
        </p>
      </div>
      <div className="divide-y divide-border border-y border-border">
        {scenarios.map((scenario) => (
          <article className="min-w-0 space-y-2 py-3" key={scenario.kind}>
            <div className="flex items-baseline justify-between gap-3">
              <h3 className="text-sm font-semibold">{t(`screen.workspace.scenario.${scenario.kind}`)}</h3>
              {scenario.probability !== null && scenario.probability !== undefined && (
                <span className="font-mono text-xs tabular-nums">
                  {scenario.probability}%
                </span>
              )}
            </div>
            <p className="text-xs leading-relaxed">{scenario.thesis}</p>
            <dl className="space-y-1 text-xs">
              <ScenarioFact label={t('screen.workspace.trigger')} value={scenario.trigger} />
              <ScenarioFact label={t('screen.workspace.invalidation')} value={moneyPrecise(scenario.invalidation, locale)} />
              <ScenarioFact label={t('screen.workspace.target')} value={moneyPrecise(scenario.target, locale)} />
            </dl>
            <p className="text-[10px] leading-relaxed text-muted-foreground">
              {scenario.confidence_reason}
            </p>
          </article>
        ))}
      </div>
    </section>
  )
}

function ScenarioFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-w-0 justify-between gap-3">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words text-right font-mono tabular-nums">{value}</dd>
    </div>
  )
}
