/* Phase 8 - Fetch Cache (경로별 TTL 차등) */

const TTL_DEFAULT = 5 * 60 * 1000;
const TTL_RULES = [
  { match: /portfolio\.json$/, ttl: 30 * 60 * 1000 },
  { match: /strategy_config\.json$/, ttl: 60 * 60 * 1000 },
  { match: /healthcheck\//, ttl: 30 * 60 * 1000 },
  { match: /leaderboard\.json$/, ttl: 5 * 60 * 1000 },
  { match: /candidates_/, ttl: 30 * 60 * 1000 },
  { match: /summary\.json$/, ttl: 10 * 60 * 1000 },
  { match: /trades\.json$/, ttl: 10 * 60 * 1000 },
];

function getTTL(path) {
  for (const rule of TTL_RULES) {
    if (rule.match.test(path)) return rule.ttl;
  }
  return TTL_DEFAULT;
}

const _cache = new Map();

export async function fetchCached(path, force = false) {
  const now = Date.now();
  if (!force && _cache.has(path)) {
    const entry = _cache.get(path);
    if (entry.expires > now) return entry.data;
  }
  const ttl = getTTL(path);
  try {
    const res = await fetch(path + '?t=' + now);
    if (!res.ok) {
      if (path.endsWith('.md')) {
        const text = await res.text().catch(() => null);
        if (text) {
          _cache.set(path, { data: text, expires: now + ttl });
          return text;
        }
      }
      _cache.set(path, { data: null, expires: now + ttl });
      return null;
    }
    const ct = res.headers.get('content-type') || '';
    const data = ct.includes('json') ? await res.json() : await res.text();
    _cache.set(path, { data, expires: now + ttl });
    return data;
  } catch (e) {
    console.warn('fetchCached fail:', path, e.message);
    return null;
  }
}

export function clearCache() {
  _cache.clear();
}

export function getCacheStats() {
  return {
    size: _cache.size,
    entries: Array.from(_cache.keys()),
  };
}
