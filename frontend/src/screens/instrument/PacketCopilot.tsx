import { useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { api, type PacketCopilotState } from '@/lib/api'
import { usePreferences } from '@/lib/preferences'

type CopilotRecord = NonNullable<PacketCopilotState['record']>
type CopilotItem = CopilotRecord['report']['base_explanation']

interface PacketCopilotProps {
  contextKey: string
  packetId: string | null
}

export function PacketCopilot({ contextKey, packetId }: PacketCopilotProps) {
  const { t } = usePreferences()
  const queryClient = useQueryClient()
  const currentPacket = useRef(packetId)
  currentPacket.current = packetId
  const queryKey = ['packet-copilot', contextKey, packetId] as const
  const query = useQuery({
    enabled: packetId !== null,
    queryFn: () => api.packetCopilot(packetId!),
    queryKey,
    retry: false,
  })
  const request = useMutation({
    mutationFn: (requestedPacketId: string) => api.requestPacketCopilot(requestedPacketId),
    mutationKey: ['request-packet-copilot', packetId],
    onSuccess: (state, requestedPacketId) => {
      if (currentPacket.current !== requestedPacketId) return
      queryClient.setQueryData(
        ['packet-copilot', contextKey, requestedPacketId],
        state,
      )
    },
  })
  const loading = packetId !== null && (
    query.isPending || (request.isPending && request.variables === packetId)
  )
  const state = query.data
  const degraded = query.isError || request.isError || state?.status === 'degraded'
  const report = state?.status === 'ready' ? state.record?.report : null
  const requestReport = () => {
    if (packetId !== null) request.mutate(packetId)
  }

  return (
    <details
      className="min-w-0 border-y border-border py-3"
      data-testid="packet-copilot"
      open
    >
      <summary className="mx-3 cursor-pointer text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        {t('screen.workspace.copilot')}
      </summary>
      <div className="min-w-0 space-y-3 px-3 pt-3">
        <p className="text-xs leading-relaxed text-muted-foreground">
          {t('screen.workspace.copilotAdvisory')}
        </p>
        {packetId === null ? (
          <>
            <p className="text-xs text-muted-foreground">
              {t('screen.workspace.copilotSaveFirst')}
            </p>
            <Button disabled size="sm" type="button" variant="outline">
              {t('screen.workspace.copilotAction')}
            </Button>
          </>
        ) : loading ? (
          <div className="space-y-2" role="status">
            <p className="text-xs text-muted-foreground">
              {t('screen.workspace.copilotLoading')}
            </p>
            <div className="h-2 w-full animate-pulse bg-muted motion-reduce:animate-none" />
            <Button disabled size="sm" type="button" variant="outline">
              {t('screen.workspace.copilotAction')}
            </Button>
          </div>
        ) : report ? (
          <CopilotReport report={report} />
        ) : degraded ? (
          <div className="space-y-2" role="status">
            <p className="text-xs leading-relaxed text-amber-800 dark:text-amber-300">
              {t('screen.workspace.copilotUnavailable')}
            </p>
            <Button onClick={requestReport} size="sm" type="button" variant="outline">
              {t('screen.workspace.copilotRetry')}
            </Button>
          </div>
        ) : (
          <Button onClick={requestReport} size="sm" type="button" variant="outline">
            {t('screen.workspace.copilotAction')}
          </Button>
        )}
      </div>
    </details>
  )
}

function CopilotReport({ report }: { report: CopilotRecord['report'] }) {
  const { t } = usePreferences()
  const sections: { key: string; label: string; items: readonly CopilotItem[] }[] = [
    { key: 'base', label: t('screen.workspace.copilotBase'), items: [report.base_explanation] },
    { key: 'bull', label: t('screen.workspace.copilotBull'), items: [report.bull_challenge] },
    { key: 'bear', label: t('screen.workspace.copilotBear'), items: [report.bear_challenge] },
    {
      key: 'gaps',
      label: t('screen.workspace.copilotGaps'),
      items: report.evidence_gaps_or_contradictions,
    },
    {
      key: 'limitations',
      label: t('screen.workspace.copilotLimitations'),
      items: report.limitations,
    },
    {
      key: 'questions',
      label: t('screen.workspace.copilotQuestions'),
      items: report.operator_questions,
    },
  ]
  return (
    <div className="min-w-0 divide-y divide-border border-t border-border">
      {sections.map((section) => (
        <section className="min-w-0 space-y-2 py-3" key={section.key}>
          <h3 className="text-xs font-semibold">{section.label}</h3>
          {section.items.map((item, index) => (
            <article className="min-w-0 space-y-2" key={`${section.key}:${index}`}>
              <p className="break-words text-xs leading-relaxed">{item.text}</p>
              <CitationDisclosure item={item} />
            </article>
          ))}
        </section>
      ))}
    </div>
  )
}

function CitationDisclosure({ item }: { item: CopilotItem }) {
  const { t } = usePreferences()
  const count = item.citations.length
  return (
    <details className="min-w-0 text-[10px] text-muted-foreground">
      <summary className="cursor-pointer font-medium underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        {t(
          count === 1
            ? 'screen.workspace.copilotCitationCount'
            : 'screen.workspace.copilotCitationCountPlural',
          { count: String(count) },
        )}
      </summary>
      <dl className="mt-2 min-w-0 space-y-2 border-l border-border pl-2">
        {item.citations.map((citation) => (
          <div
            className="min-w-0 space-y-1 [overflow-wrap:anywhere]"
            data-testid="packet-copilot-citation"
            key={`${citation.source_id}:${citation.json_pointer}`}
          >
            <dt>{t('screen.workspace.copilotPacketField')}</dt>
            <dd className="break-all font-mono text-foreground">
              {String(citation.json_pointer)}
            </dd>
            <dt>{t('screen.workspace.copilotValueDigest')}</dt>
            <dd className="break-all font-mono text-foreground">
              {String(citation.value_digest)}
            </dd>
            <dt>{t('screen.workspace.copilotSourcePacket')}</dt>
            <dd className="break-all font-mono text-foreground">
              {String(citation.source_id)}
            </dd>
          </div>
        ))}
      </dl>
    </details>
  )
}

export default PacketCopilot
