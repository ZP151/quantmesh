import { expect, it } from 'vitest'

import { ApiError, generatedApiError } from './api'

it('preserves the safe top-level Decision Inbox replay message', () => {
  const error = generatedApiError(new Response(JSON.stringify({
    code: 'decision_inbox_replay_unavailable',
    message: 'Decision Inbox is unavailable because stored decision state cannot be replayed.',
  }), {
    headers: { 'content-type': 'application/json' },
    status: 409,
    statusText: 'Conflict',
  }), {
    code: 'decision_inbox_replay_unavailable',
    message: 'Decision Inbox is unavailable because stored decision state cannot be replayed.',
  })

  expect(error).toEqual(new ApiError(
    409,
    'Decision Inbox is unavailable because stored decision state cannot be replayed.',
  ))
})
