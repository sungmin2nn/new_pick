/* Phase 8 - Fetch Cache (5분 TTL) */

const CACHE_TTL = 5 * 60 * 1000;
const _cache = new Map();

export async function fetchCached(path, force = false) {
  const now = Date.now();
  if (!force && _cache.has(path)) {
    const entry = _cache.get(path);
    if (entry.expires > now) return entry.data;
  }
  try {
    const res = await fetch(path + '?t=' + now);
    if (!res.ok) {
      if (path.endsWith('.md')) {
        const text = await res.text().catch(() => null);
        if (text) {
          _cache.set(path, { data: text, expires: now + CACHE_TTL });
          return text;
        }
      }
      _cache.set(path, { data: null, expires: now + CACHE_TTL });
      return null;
    }
    const ct = res.headers.get('content-type') || '';
    const data = ct.includes('json') ? await res.json() : await res.text();
    _cache.set(path, { data, expires: now + CACHE_TTL });
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
