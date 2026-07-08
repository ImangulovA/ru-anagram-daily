// ---------------------------------------------------------------------------
// Per-fork configuration for Anagram Daily.
// ---------------------------------------------------------------------------

// Global-stats Worker (Cloudflare). Shares the deployed anagram-stats worker
// with the English game; rows stay separate because the stats "game" key is
// GAME.statsId = 'ru-anagram-daily' (English uses 'anagram-daily'). CORS on the
// worker already allows https://imangulova.github.io. Set to '' to run
// LOCAL-ONLY (every network call no-ops and nothing breaks).
export const STATS_API = 'https://anagram-stats.ru-catfishing.workers.dev';

// Password that unlocks playing FUTURE (not-yet-released) days early via
// `?unlock=<this>&day=N`. OBFUSCATION, not security — future days ship in the
// bundle regardless. Set to '' to disable the author-mode gate entirely.
export const UNLOCK_PASSWORD = 'flagship';
