No actionable P1/P2 findings in the narrow unexpected-poll repair.

Scope: working diff against HEAD 042fb0b491c13f4535bddbb61290b191d29b1790, comprising six added source lines in src/quantmesh/live/moomoo.py and the 32-line parametrized regression in tests/test_live_moomoo.py. Reviewed the relevant poll/recv/close, SDK method cleanup boundaries, dispatch, and VenueSupervisor.run handoff. No source edits or test reruns.

The added Exception handler covers unexpected quote, ticker, and candle call failures, including context.close() failures escaping the SDK's classified boundary. It queues a fixed poll_error message without inspecting or exposing the original exception. The existing OpenDError branch remains first and unchanged. Cancellation and other BaseException subclasses remain outside the new handler. SDK arguments and market calculations are unchanged.

recv delivers poll_error to dispatch, which raises MoomooProtocolError; VenueSupervisor.run catches that Exception, closes the transport, marks disconnect, and enters reconnect backoff. The three regression cases verify delivery, exact sanitized content, and dispatch rejection, with finally close plus gather to retrieve the poll task result.

Recorded evidence inspected: red.log/red.exit show all three new cases failing with TimeoutError (exit 1); green.log/green.exit and green.xml show the complete tests/test_live_moomoo.py file passing, 17 tests, 5 warnings, 6.75 seconds (exit 0). The regressions directly test the transport-to-dispatch boundary; the reconnect conclusion additionally follows from the unchanged run caller inspected here. This review does not establish an actual AWS incident cause or certify deployed runtime behavior.
