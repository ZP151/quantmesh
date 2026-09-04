import type { DecisionPacket } from '@/lib/api'
import { dateTime, moneyPrecise, number, percent } from '@/lib/format'
import { type Locale, usePreferences } from '@/lib/preferences'

const scenarioOrder = ['bull', 'base', 'bear'] as const

export function PacketEvidenceSummary({ packet }: { packet: DecisionPacket }) {
  const { locale, t } = usePreferences()
  const evidence = packet.evidence
  const chronology = evidence.forecast_chronology
  const forecastMetrics = evidence.forecast_metrics ?? []
  const forecastPaths = evidence.forecast_paths ?? []
  const historyGaps = evidence.history_gaps ?? []
  const historyDuplicates = evidence.history_duplicates ?? []
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
        <EvidenceFact label={t('screen.workspace.historyDataset')} value={evidence.history_dataset_id} />
        <EvidenceFact label={t('screen.workspace.historyDatasetRevision')} value={String(evidence.history_dataset_revision)} />
        <EvidenceFact label={t('screen.workspace.source')} value={evidence.history_source} />
        <EvidenceFact label={t('screen.workspace.generated')} value={dateTime(evidence.history_generated_at, locale)} />
        <EvidenceFact label={t('screen.workspace.historyManifestId')} value={evidence.history_manifest_id} />
        <EvidenceFact label={t('screen.workspace.historyQualityEvaluationId')} value={evidence.history_quality_evaluation_id} />
        <EvidenceFact label={t('screen.workspace.artifact')} value={evidence.forecast_artifact_id} />
        <EvidenceFact label={t('screen.workspace.forecastDataset')} value={evidence.forecast_dataset_id} />
        <EvidenceFact label={t('screen.workspace.forecastDatasetRevision')} value={evidence.forecast_dataset_revision} />
        <EvidenceFact label={t('screen.workspace.model')} value={evidence.forecast_model_name} />
        <EvidenceFact label={t('screen.workspace.modelVersion')} value={evidence.forecast_model_version} />
        <EvidenceFact label={t('screen.workspace.configDigest')} value={evidence.forecast_config_digest} />
        <EvidenceFact label={t('screen.workspace.historyDigest')} value={evidence.forecast_history_digest} />
        <EvidenceFact label={t('screen.workspace.benchmark')} value={evidence.forecast_benchmark_name} />
        <EvidenceFact label={t('screen.workspace.forecastVintage')} value={evidence.forecast_generated_at ? dateTime(evidence.forecast_generated_at, locale) : null} />
        <EvidenceFact label={t('screen.workspace.forecastManifestId')} value={evidence.forecast_manifest_id} />
        <EvidenceFact label={t('screen.workspace.forecastQualityEvaluationId')} value={evidence.forecast_quality_evaluation_id} />
        <EvidenceFact
          label={t('screen.workspace.forecastEligibility')}
          value={evidence.forecast_eligible === null || evidence.forecast_eligible === undefined
            ? null
            : t(evidence.forecast_eligible ? 'screen.workspace.eligible' : 'screen.workspace.notEligible')}
        />
        <EvidenceFact
          label={t('screen.workspace.syntheticEvidence')}
          value={evidence.forecast_synthetic === null || evidence.forecast_synthetic === undefined
            ? null
            : t(evidence.forecast_synthetic ? 'screen.workspace.synthetic' : 'screen.workspace.nonSynthetic')}
        />
        <EvidenceFact label={t('screen.workspace.fees')} value={`${number(evidence.costs.fee_bps, locale)} bps`} />
        <EvidenceFact label={t('screen.workspace.slippage')} value={`${number(evidence.costs.slippage_bps, locale)} bps`} />
        <EvidenceFact
          label={t('screen.workspace.halfSpread')}
          value={evidence.costs.half_spread_bps === null || evidence.costs.half_spread_bps === undefined
            ? t('screen.workspace.spreadAtConfirmation')
            : `${number(evidence.costs.half_spread_bps, locale)} bps`}
        />
      </dl>
      {chronology && (
        <div
          aria-label={t('screen.workspace.forecastChronologyOverview')}
          className="space-y-1 border-b border-border pb-3 text-xs"
          role="group"
        >
          <p className="font-semibold">{t('screen.workspace.forecastChronologyOverview')}</p>
          <dl className="space-y-1">
            <EvidenceFact
              label={t('screen.workspace.trainWindow')}
              value={`${dateTime(chronology.train_start, locale)} → ${dateTime(chronology.train_end, locale)}`}
            />
            <EvidenceFact
              label={t('screen.workspace.validationWindow')}
              value={timeWindow(chronology.validation_start, chronology.validation_end, locale)}
            />
            <EvidenceFact
              label={t('screen.workspace.testWindow')}
              value={timeWindow(chronology.test_start, chronology.test_end, locale)}
            />
          </dl>
        </div>
      )}
      {forecastMetrics.length > 0 && (
        <div className="space-y-3 border-b border-border pb-3 text-xs">
          {forecastMetrics.map((metric) => {
            const metricLabel = t('screen.workspace.metricHorizon', { sessions: String(metric.sessions) })
            return (
              <div aria-label={metricLabel} className="space-y-1" key={metric.sessions} role="group">
                <p className="font-semibold">{metricLabel}</p>
                <dl className="space-y-1">
                  <EvidenceFact label={t('screen.workspace.oosMae')} value={number(metric.mae, locale)} />
                  <EvidenceFact label={t('screen.workspace.oosRmse')} value={number(metric.rmse, locale)} />
                  <EvidenceFact label={t('screen.workspace.benchmarkMae')} value={number(metric.benchmark_mae, locale)} />
                  <EvidenceFact
                    label={t('screen.workspace.coverage')}
                    value={`${percent(metric.coverage_50, locale)} / ${percent(metric.coverage_80, locale)} / ${percent(metric.coverage_95, locale)}`}
                  />
                  <EvidenceFact label={t('screen.workspace.residualSamples')} value={number(metric.residual_count, locale)} />
                  <EvidenceFact label={t('screen.workspace.intervalTests')} value={number(metric.interval_test_count, locale)} />
                  <EvidenceFact
                    label={t('screen.workspace.validationStart')}
                    value={metric.validation_start ? dateTime(metric.validation_start, locale) : null}
                  />
                  <EvidenceFact
                    label={t('screen.workspace.validationEnd')}
                    value={metric.validation_end ? dateTime(metric.validation_end, locale) : null}
                  />
                  <EvidenceFact
                    label={t('screen.workspace.testStart')}
                    value={metric.test_start ? dateTime(metric.test_start, locale) : null}
                  />
                  <EvidenceFact
                    label={t('screen.workspace.testEnd')}
                    value={metric.test_end ? dateTime(metric.test_end, locale) : null}
                  />
                </dl>
              </div>
            )
          })}
        </div>
      )}
      {forecastPaths.map((path) => (
        <details className="border-b border-border pb-3 text-xs" key={path.sessions}>
          <summary className="cursor-pointer font-semibold">
            {t('screen.workspace.forecastPath', { sessions: String(path.sessions) })}
          </summary>
          <ul className="mt-2 space-y-2">
            {path.points.map((point) => (
              <li className="break-all font-mono text-[10px] [overflow-wrap:anywhere]" key={`${path.sessions}:${point.session}`}>
                {t('screen.workspace.forecastPathPoint', {
                  p025: moneyPrecise(point.p025, locale),
                  p10: moneyPrecise(point.p10, locale),
                  p25: moneyPrecise(point.p25, locale),
                  p50: moneyPrecise(point.p50, locale),
                  p75: moneyPrecise(point.p75, locale),
                  p90: moneyPrecise(point.p90, locale),
                  p975: moneyPrecise(point.p975, locale),
                  session: String(point.session),
                  time: dateTime(point.timestamp, locale),
                })}
              </li>
            ))}
          </ul>
        </details>
      ))}
      <EvidenceTimes details={historyGaps} label={t('screen.workspace.historyGapsLabel')} locale={locale} />
      <EvidenceTimes details={historyDuplicates} label={t('screen.workspace.historyDuplicatesLabel')} locale={locale} />
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

function timeWindow(
  start: string | null | undefined,
  end: string | null | undefined,
  locale: Locale,
): string | null {
  return start && end ? `${dateTime(start, locale)} → ${dateTime(end, locale)}` : null
}

function EvidenceTimes({ details, label, locale }: {
  details: readonly string[]
  label: string
  locale: Locale
}) {
  if (details.length === 0) return null
  return (
    <details className="border-b border-border pb-3 text-xs">
      <summary className="cursor-pointer font-semibold">{label}</summary>
      <ul className="mt-2 space-y-1 font-mono text-[10px]">
        {details.map((time) => <li key={time} title={time}>{dateTime(time, locale)}</li>)}
      </ul>
    </details>
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
