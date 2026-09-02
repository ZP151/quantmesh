import type { DecisionPacket } from '@/lib/api'
import { dateTime, moneyPrecise, number } from '@/lib/format'
import { usePreferences } from '@/lib/preferences'

const scenarioOrder = ['bull', 'base', 'bear'] as const

export function PacketEvidenceSummary({ packet }: { packet: DecisionPacket }) {
  const { locale, t } = usePreferences()
  const evidence = packet.evidence
  const chronology = evidence.forecast_chronology
  const forecastMetrics = evidence.forecast_metrics ?? []
  const limitations = [
    ...(evidence.history_limitations ?? []),
    ...(evidence.forecast_limitations ?? []),
    ...(evidence.forecast_blockers ?? []),
  ]

  return (
    <section className="min-w-0 space-y-3 px-3" aria-label={t('screen.workspace.packetEvidence')}>
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          {t('screen.workspace.archivedEvidence')}
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">{t('screen.workspace.archivedEvidenceNote')}</p>
      </div>
      <dl className="space-y-1 border-y border-border py-3 text-xs">
        <EvidenceFact label={t('screen.workspace.dataset')} value={evidence.history_dataset_id} />
        <EvidenceFact label={t('screen.workspace.datasetRevision')} value={String(evidence.history_dataset_revision)} />
        <EvidenceFact label={t('screen.workspace.source')} value={evidence.history_source} />
        <EvidenceFact label={t('screen.workspace.generated')} value={dateTime(evidence.history_generated_at, locale)} />
        <EvidenceFact label={t('screen.workspace.manifestId')} value={evidence.history_manifest_id} />
        <EvidenceFact label={t('screen.workspace.qualityEvaluationId')} value={evidence.history_quality_evaluation_id} />
        <EvidenceFact label={t('screen.workspace.artifact')} value={evidence.forecast_artifact_id} />
        <EvidenceFact label={t('screen.workspace.model')} value={evidence.forecast_model_name} />
        <EvidenceFact label={t('screen.workspace.modelVersion')} value={evidence.forecast_model_version} />
        <EvidenceFact label={t('screen.workspace.configDigest')} value={evidence.forecast_config_digest} />
        <EvidenceFact label={t('screen.workspace.historyDigest')} value={evidence.forecast_history_digest} />
        <EvidenceFact label={t('screen.workspace.benchmark')} value={evidence.forecast_benchmark_name} />
        <EvidenceFact label={t('screen.workspace.forecastVintage')} value={evidence.forecast_generated_at ? dateTime(evidence.forecast_generated_at, locale) : null} />
        <EvidenceFact label={t('screen.workspace.manifestId')} value={evidence.forecast_manifest_id} />
        <EvidenceFact label={t('screen.workspace.qualityEvaluationId')} value={evidence.forecast_quality_evaluation_id} />
        {chronology && (
          <EvidenceFact
            label={t('screen.workspace.trainWindow')}
            value={`${dateTime(chronology.train_start, locale)} → ${dateTime(chronology.train_end, locale)}`}
          />
        )}
      </dl>
      {forecastMetrics.length > 0 && (
        <div className="space-y-1 border-b border-border pb-3 text-xs">
          {forecastMetrics.map((metric) => (
            <p className="break-all font-mono [overflow-wrap:anywhere]" key={metric.sessions}>
              {t('screen.workspace.packetMetric', {
                benchmark: number(metric.benchmark_mae, locale),
                mae: number(metric.mae, locale),
                rmse: number(metric.rmse, locale),
                sessions: String(metric.sessions),
              })}
            </p>
          ))}
        </div>
      )}
      {limitations.length > 0 && (
        <ul className="space-y-1 text-[10px] leading-relaxed text-muted-foreground">
          {limitations.map((item) => (
            <li className="break-words" key={item}>{item}</li>
          ))}
        </ul>
      )}
    </section>
  )
}

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

function EvidenceFact({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="flex min-w-0 justify-between gap-3">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-all text-right font-mono tabular-nums [overflow-wrap:anywhere]">{value ?? '—'}</dd>
    </div>
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
