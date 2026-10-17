// A small cache of recent requests in a fixed ring of slots: a new entry
// overwrites the oldest, so memory stays bounded. Entries are promises, so a
// request still in flight is shared rather than sent twice; failures, and
// results that `keep` rejects, are dropped so they can be retried.
export function ringCache<T>(slots: number, keep: (value: T) => boolean = () => true) {
  const keys: (string | null)[] = new Array(slots).fill(null)
  const values: Promise<T>[] = new Array(slots)
  let next = 0
  return function cached(key: string, load: () => Promise<T>): Promise<T> {
    const i = keys.indexOf(key)
    if (i >= 0) return values[i]
    const slot = next
    next = (next + 1) % slots
    const p = load()
    keys[slot] = key
    values[slot] = p
    p.then(v => { if (!keep(v) && keys[slot] === key) keys[slot] = null },
      () => { if (keys[slot] === key) keys[slot] = null })
    return p
  }
}
