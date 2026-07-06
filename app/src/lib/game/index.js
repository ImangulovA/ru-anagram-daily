// ===========================================================================
// GAME CONFIG — Anagram Daily.
//
// The platform (routing, timer, storage, stats, backend, archive, share) talks
// to your game ONLY through this object and the component's callback contract.
// ===========================================================================
import GameComponent from './GameComponent.svelte';
import { dayIndexes as dataDayIndexes, loadDay as dataLoadDay } from './data/days.js';
import { MAX_SCORE } from './scoring.js';

// Trim a score for display: integers print plain, halves get one decimal.
function trimNum(n) {
  if (typeof n !== 'number' || Number.isNaN(n)) return '—';
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

export const GAME = {
  // Storage namespace. localStorage key is `ruanagram_day<N>` — distinct from
  // the English 'anagram' game so the two never collide, and the games-hub can
  // read it as its own entry.
  id: 'ruanagram',

  // Backend stats-worker "game" key (its own RU worker / D1 table).
  statsId: 'ru-anagram-daily',

  title: 'Анаграмма дня',
  tagline: 'Две подсказки, два слова — собери из всех их букв третье.',

  // Day 0 = 6 July 2026 (monthIndex 6). Day N = this + N calendar days.
  anchorDate: [2026, 6, 6],

  component: GameComponent,

  dayIndexes: dataDayIndexes,
  loadDay: dataLoadDay,

  // Higher is better: the day's remaining points (0..20). The worker stores it
  // in tenths; /agg returns it back in points for the histogram.
  scoreOf(result) {
    return result && typeof result.score === 'number' ? result.score : null;
  },

  // Score-based celebratory emoji (mirrors the end screen; single copy here).
  resultEmoji(score) {
    if (typeof score !== 'number' || Number.isNaN(score)) return '';
    if (score >= 15) return '🐗🤯';
    if (score >= 10) return '🎊';
    if (score >= 0.5) return '👍';
    return '';
  },

  // Rich, spoiler-free share block. `result.marks` is precomputed at finish
  // time (clean solve / gave up / hint summary) by the scoring engine.
  shareLine(result, dayIdx, url) {
    const s = trimNum(result?.score);
    const max = result?.max ?? MAX_SCORE;
    const emoji = this.resultEmoji(result?.score);
    const head = `${GAME.title} #${dayIdx} -- ${s}/${max}`;
    const line2 = [emoji, result?.marks || ''].filter(Boolean).join(' ');
    return [head, line2, url].filter(Boolean).join('\n');
  }
};
