<script>
  // Personal stats (localStorage) + optional global numbers (Worker). PLATFORM code.
  import { onMount } from 'svelte';
  import { base } from '$app/paths';
  import { computeStats } from '$lib/platform/stats.js';
  import { fetchAgg, statsEnabled } from '$lib/platform/api.js';
  import { fmtTime } from '$lib/platform/timer.js';

  let s = $state(null);
  let global = $state(null);

  onMount(async () => {
    s = computeStats();
    if (statsEnabled() && s && s.finishedIdx.length) {
      const agg = await fetchAgg(s.finishedIdx);
      global = agg?.agg || null;
    }
  });

  const pct = (x) => Math.round((x || 0) * 100);
</script>

<h1>Статистика</h1>

{#if !s || s.started === 0}
  <p class="muted">Сыграйте хотя бы один день, и здесь появится ваша статистика.</p>
{:else}
  <div class="grid">
    <div class="stat"><span class="num">{s.finished}</span><span class="lbl">дней разгадано</span></div>
    <div class="stat"><span class="num">{pct(s.finishRate)}%</span><span class="lbl">завершаемость</span></div>
    <div class="stat"><span class="num">🔥 {s.currentStreak}</span><span class="lbl">серия</span></div>
    <div class="stat"><span class="num">{fmtTime(s.avgMs)}</span><span class="lbl">среднее время</span></div>
    <div class="stat"><span class="num">{fmtTime(s.bestMs)}</span><span class="lbl">лучшее время</span></div>
    {#if s.scored}
      <div class="stat"><span class="num">{s.avgScore?.toFixed(1)}</span><span class="lbl">средний счёт</span></div>
      <div class="stat"><span class="num">{s.bestScore}</span><span class="lbl">лучший счёт</span></div>
    {/if}
  </div>

  <h2>По дням</h2>
  <ul class="days">
    {#each [...s.days].reverse() as d}
      <li>
        <a href="{base}/?day={d.idx}">
          <span class="idx">#{d.idx}</span>
          <span class="time">{fmtTime(d.ms)}</span>
          {#if global?.[d.idx]}
            <span class="g">всего: {global[d.idx].started} начали · {global[d.idx].finished} завершили</span>
          {/if}
        </a>
      </li>
    {/each}
  </ul>

  {#if !statsEnabled()}
    <p class="hint">Глобальная статистика отключена. Разверните Worker (см. <code>backend/README.md</code>) и вставьте его URL в <code>config.js</code>.</p>
  {/if}
{/if}

<style>
  h1 {
    font-size: 24px;
  }
  h2 {
    font-size: 18px;
    margin-top: 24px;
  }
  .muted {
    color: var(--muted);
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 12px;
    margin: 16px 0;
  }
  .stat {
    background: var(--surface);
    border: var(--border);
    box-shadow: var(--shadow);
    border-radius: 10px;
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .num {
    font-family: var(--mono);
    font-size: 22px;
    font-weight: 700;
  }
  .lbl {
    color: var(--muted);
    font-size: 12px;
  }
  .days {
    list-style: none;
    padding: 0;
    margin: 12px 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .days a {
    display: flex;
    align-items: center;
    gap: 12px;
    text-decoration: none;
    color: var(--ink);
    border-bottom: 1px solid color-mix(in srgb, var(--muted) 30%, transparent);
    padding: 8px 2px;
  }
  .idx {
    font-family: var(--mono);
    color: var(--muted);
    min-width: 44px;
  }
  .time {
    font-family: var(--mono);
    font-weight: 600;
  }
  .g {
    margin-left: auto;
    font-size: 12px;
    color: var(--muted);
  }
  .hint {
    margin-top: 20px;
    color: var(--muted);
    font-size: 13px;
  }
  code {
    font-family: var(--mono);
    background: var(--surface-2);
    padding: 1px 4px;
    border-radius: 4px;
  }
</style>
