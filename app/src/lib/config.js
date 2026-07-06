// ---------------------------------------------------------------------------
// Per-fork configuration for Anagram Daily.
// ---------------------------------------------------------------------------

// Global-stats Worker (Cloudflare). Its own RU worker (deploy from backend/).
// Set to '' to run LOCAL-ONLY (every network call no-ops and nothing breaks).
// Left empty until the ru-anagram-stats worker is deployed.
export const STATS_API = '';

// Password that unlocks playing FUTURE (not-yet-released) days early via
// `?unlock=<this>&day=N`. OBFUSCATION, not security — future days ship in the
// bundle regardless. Set to '' to disable the author-mode gate entirely.
export const UNLOCK_PASSWORD = 'flagship';
