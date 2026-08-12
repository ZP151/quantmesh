import { useQuery } from '@tanstack/react-query'
import { Link, Navigate, useParams } from 'react-router-dom'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorState, LoadingState } from '@/components/state'
import { Page } from '@/components/page'
import { api } from '@/lib/api'
import { instrumentPath } from '@/lib/instrument-route'
import { usePreferences } from '@/lib/preferences'

export function LegacyCockpitRedirect() {
  const { symbol = '', venue } = useParams<{ symbol: string; venue?: string }>()
  const { t } = usePreferences()
  const directory = useQuery({
    queryKey: ['markets'],
    queryFn: api.markets,
    enabled: venue === undefined,
    retry: false,
  })

  if (venue !== undefined) {
    return <Navigate replace to={instrumentPath(venue, symbol)} />
  }

  if (directory.isPending) return <LoadingState rows={2} />
  if (directory.isError) {
    return (
      <ErrorState
        title={t('screen.cockpitLegacy.title')}
        detail={directory.error instanceof Error ? directory.error.message : String(directory.error)}
      />
    )
  }

  const venues = Array.from(new Set(
    directory.data.instruments
      .filter((instrument) => instrument.symbol === symbol)
      .map((instrument) => instrument.venue),
  ))
  if (venues.length === 1) {
    return <Navigate replace to={instrumentPath(venues[0], symbol)} />
  }

  const reason = venues.length === 0
    ? t('screen.cockpitLegacy.missing', { symbol })
    : t('screen.cockpitLegacy.ambiguous', { symbol })
  return (
    <Page
      title={t('screen.cockpitLegacy.title')}
      description={t('screen.cockpitLegacy.description')}
    >
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('screen.cockpitLegacy.unresolved')}</CardTitle>
          <CardDescription role="alert">{reason}</CardDescription>
        </CardHeader>
        <CardContent>
          <Link
            className="text-sm font-medium text-primary underline-offset-4 hover:underline focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            to="/markets"
          >
            {t('screen.cockpitLegacy.openMarkets')}
          </Link>
        </CardContent>
      </Card>
    </Page>
  )
}
