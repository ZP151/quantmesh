export function retainSameInstrument<T>(
  previous: T | undefined,
  previousQueryKey: readonly unknown[] | undefined,
  venue: string,
  symbol: string,
): T | undefined {
  return previousQueryKey?.[1] === venue && previousQueryKey[2] === symbol
    ? previous
    : undefined
}
