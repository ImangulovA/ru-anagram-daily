# ru-anagram-daily -- состояние сборки (пауза 2026-07-06)

Русская версия [[anagram-daily]] на платформе daily_github_game. Форкнута
копированием `~/Desktop/anagram-daily` -> `~/Desktop/ru-anagram-daily`
(без .git, .venv, build, data). Механика та же: две подсказки -> слова А и Б,
из их букв анаграммой собирается слово В (ответ).

Интерпретатор для скриптов (свой venv не делали, PyPI заблокирован):
`PY=~/Desktop/anagram-daily/.venv/bin/python` (там есть wordfreq + nltk).

## Ключевые решения (согласованы с Amal)
- Части речи: любые знаменательные (на деле пул сам сходится к существительным,
  т.к. кроссвордные ответы -- почти всегда существительные).
- **Ё -- строгая, отдельная буква** (без свёртки ё->е). Работает из коробки:
  `sorted()` различает ё.
- Длина ответа В по дням недели: Пн/Вт/Вс=8, Ср/Чт=9, Пт/Сб=10..12.
  **СНИЖЕНО 2026-07-06 до уровня EN** (было 9/10/11..13 -- слишком хардкор;
  русские слова и так длиннее английских). Правки: `gen_puzzles.py`
  MIN_C_LEN 9->8, PREFERRED_C_LEN (9,12)->(8,11), WEEKDAY_C_LENS сдвинут на -1,
  _raw_hardness длина нормируется (clen-8)/5.0; `verify_puzzles.py` MIN_C_LEN 9->8.
- **anchor день 0 = 2026-07-06** (`GAME.anchorDate=[2026,6,6]`). FIRST_DAY=-35
  (2026-06-01), LAST_DAY=129.
- Источник определений: **помощник кроссвордиста graycell.ru**
  (`graycell.ru/word/<слово>`) -- корректные кроссвордные подсказки, берём как
  есть, длина не важна. Слова + частота: `wordfreq`.

## Что уже СДЕЛАНО
1. Скаффолд скопирован (node_modules на месте).
2. `scripts/build_words.py` -- переписан под graycell + wordfreq. Многопоточно,
   кеш `data/graycell_cache.json`, идемпотентно. Хранит на слово:
   `{def, clues[до 12], freq}`; `def` = самая «толковая» клу (rank_clue отсеивает
   загадки-вопросы, кавычки-игру слов, буквенные ребусы, циклические).
3. `scripts/gen_puzzles.py` -- порт движка на кириллицу: подпись ё-строгая,
   длины 9/10/11-13, русские однокоренные через `nltk SnowballStemmer('russian')`
   + общий префикс, правило «исходное слово не подстрока ответа», BLOCKED_TRIPLES
   (пока пусто), пишет `data/puzzles.{json,js}` + `app/src/lib/game/data/days.js`.
4. `scripts/verify_puzzles.py` -- порт: кириллица А-ЯЁ, MIN_C_LEN=9,
   anchor 2026-07-06, проверка weekday->длина.
5. Фронтенд Russify (агентом) + ручные правки:
   - `app/src/lib/game/index.js`: id `ruanagram`, statsId `ru-anagram-daily`,
     title «Анаграмма дня», tagline RU, anchorDate [2026,6,6].
   - `app/src/lib/config.js`: `STATS_API=''` (локально; RU-воркер не деплоили).
   - `app/src/lib/game/scoring.js`: **normWord -> `/[^А-ЯЁ]/g`** (было A-Z; иначе
     кириллица обнулялась -- критично).
   - `app/src/lib/game/GameComponent.svelte`: onInput-фильтр -> `/[^А-ЯЁ]/g`;
     `inputmode` всех 3 инпутов -> `text` (было `latin`); все строки переведены.
   - `+layout.svelte`, `routes/+page.svelte`, `routes/archive`, `routes/stats`,
     `scoring.js` marks -- переведены на русский.
   - `package.json` name -> `ru-anagram-daily`.
   - `README.md` переписан на русский.
6. Deploy: `.github/workflows/deploy.yml` берёт BASE_PATH из имени репо ->
   `/ru-anagram-daily` автоматически, правок не нужно.

## Где ОСТАНОВИЛИСЬ (обновлено 2026-07-06, сессия 2)
Сбор словаря ЗАВЕРШЁН: `data/graycell_cache.json` = 24365/24365,
**`data/words_defs.json` = 5665 слов** (0 сбоев; 20 воркеров -- норм, 24 давали
редкие 503). Дни сгенерированы и проверены на СНИЖЕННОЙ сложности:
`gen_puzzles` -> 1319 триплетов, 621 уникальных C; `verify_puzzles` -> ALL CHECKS
PASSED. День 0 = 2026-07-06 = МАТЕРИАЛ (8 букв, diff 1). Гистограмма сложности
{1:72,2:28,3:26,4:25,5:14}.

**Фронтенд-свистоперделки из EN перенесены** (коммит 5d8fa3c): экран результатов
= celebration-emoji по счёту (`resultEmoji`) + emoji-recap подсказок с
тултипами (tap/hover, `activeMark`/`MARK_LEGEND` на русском) в
`routes/+page.svelte`; в `lib/game/index.js` добавлен метод `resultEmoji` и
эмодзи в `shareLine`. Анимация победы/портретный пул/архив уже были в форке.

**Почини форка (важно для сборки):**
- `node_modules/@sveltejs/kit` в форке был НЕПОЛНЫЙ (не хватало
  `src/runtime/server/data/`) -> скопировал целиком из EN (та же версия 2.69.1),
  npm-реестр заблокирован. Если пересоздавать форк -- копируй node_modules
  полностью или чини kit так же.
- Не было каталога `app/src/lib/game/data/` -> `gen_puzzles` молча НЕ писал
  `days.js` (гейт `os.path.isdir`). Создал `mkdir -p`, перегенерил.
Сборка проходит: `BASE_PATH=/ru-anagram-daily vite build` -> `app/build/` OK,
свистоперделки в бандле.

## СДЕЛАНО (сессия 2, продолжение)
- **300+ игровых дней, окно -30..277** (2026-06-06 .. 2027-04-09), день 0 =
  сегодня 2026-07-06 = МИРА+ТЕЛА=МАТЕРИАЛ. Негативные дни = играбельный
  пред-запуск с начала июня. `gen_puzzles`: FIRST_DAY=-30, LAST_DAY=277 с
  АВТО-ПОДРЕЗКОЙ хвоста (`_place_days_unique` уменьшает last_day, если пул
  непересекающихся слов не тянет; здесь подрезка не понадобилась).
- **Глобальная уникальность СЛОВ** (не только ответов): каждое слово A/B/C
  используется РОВНО ОДИН раз во всём буфере (308 дней) -> 0 повторов в первые
  300 дней. Реализация: `curate`+`_place_days_unique`/`_try_assign` --
  length-aware жадность по корзинам длины (сначала дефицитные), day 0
  зарезервирован под «дружелюбную» частотную тройку. `UNIQUE_WORDS=True`.
- **Аудит однокоренных + полного вхождения** пройден:
  - Полное вхождение (substring A/B в C): 0 (механически гарантируется).
  - Однокоренные: 6 агентов проверили все 307 троек -> 10 флагов; дельта-раунды
    -> ещё 4; в `_AUDIT_COGNATE_TRIPLES`/`BLOCKED_TRIPLES` теперь 14 троек.
  - `are_cognate` усилена: правило «общая непрерывная подстрока >=5» ловит
    семьи работ-/форм- механически (суффиксы -ЕНИЕ/-СТВО не считаются корнем).
  - `BLOCKED_WORDS={"СТУПЕНИ"}` -- слово-магнит семейства ступ-, убрано из пула.
  - Итог: мех. однокоренных 0, истинных однокоренных по агент-аудиту 0.
  - Агент дополнительно отметил ~7 «визуально лёгких» троек (костяк согласных
    источника куском лежит в ответе, напр. КАМЕРА~АМЕРИКАНКА) -- это ВНЕ
    критериев (не корень, не вхождение), не форсим; Amal может точечно
    добавить в BLOCKED_TRIPLES при желании.
- Пул после блоков: 1275 троек / 592 уник. C (хватает на 308 дней с запасом).
- verify_puzzles -> ALL CHECKS PASSED; фронт пересобран (`app/build/`).

## СЛЕДУЮЩЕЕ
- ~~Репозиторий `ImangulovA/ru-anagram-daily` + Pages~~ **СДЕЛАНО 2026-07-06:**
  запушено (commit cddf2af), Pages включён через API (build_type=workflow),
  deploy прошёл, сайт LIVE -> https://imangulova.github.io/ru-anagram-daily/
  (HTTP 200, title «Анаграмма дня»). Заметка: как и в balatrivia,
  `configure-pages enablement:true` в воркере падает («Resource not accessible
  by integration») -- Pages пришлось включить вручную:
  `gh api -X POST repos/ImangulovA/ru-anagram-daily/pages -f build_type=workflow`,
  затем `gh workflow run deploy.yml`.
- ~~Интеграция в games-hub~~ **СДЕЛАНО 2026-07-06** (`ImangulovA/games`
  commit fc8d99c): добавлена 4-я игра в `GAMES` (id `ru-anagram-daily`,
  name «Анаграмма дня», icon 🔡, base `/ru-anagram-daily/`, prefix
  `ruanagram_day`, anchor [2026,6,6], kind `anagram`, archivePath `#archive`).
  Интро «three->four», README обновлён (обе анаграммы + shape записи).
  Хаб LIVE -> https://imangulova.github.io/games/
- ~~Браузерный QA (headless-часть)~~ **СДЕЛАНО 2026-07-06:** live 200,
  title «Анаграмма дня», все 17 `_app` ассетов 200, `404.html` 200 (SPA),
  день 0 в бандле = МИРА+ТЕЛА=МАТЕРИАЛ. Осталось ИНТЕРАКТИВНОЕ QA
  (ввод ответов/стрик/шэр/тема) -- нужен реальный браузер (в песочнице
  Chrome/Playwright заблокированы), сделать вручную на live.
- Backend-воркер `ru-anagram-stats` (D1) + прописать STATS_API в config.js.
  БЛОКЕР: npm-реестр заблокирован (503) -> `wrangler` не поставить локально;
  деплой на Cloudflare требует твоего логина. Делать с девсервера/вручную.

## Где ОСТАНОВИЛИСЬ (архив, сессия 1)
Фоновый сбор `build_words.py` УБИТ (нужен был интернет). Кеш сохранён:
**`data/graycell_cache.json` = 3500 / 24365 слов, из них 1007 с подсказками**
(покрытие ~29%). `data/words_defs.json` ещё НЕ создан.
Задержка graycell ~0.5-0.7s/запрос; на 12 воркерах ~330 слов/мин (весь набор
~1 час). Можно поднять до ~24-28 воркеров (~2x), graycell терпит.

## СЛЕДУЮЩИЕ ШАГИ (по порядку)
```bash
cd ~/Desktop/ru-anagram-daily
PY=~/Desktop/anagram-daily/.venv/bin/python

# 1) Дособрать словарь (кеш продолжится с 3500; можно больше воркеров).
$PY scripts/build_words.py --limit 25000 --workers 24    # -> data/words_defs.json
# (при желании быстрее протестировать: хватит и частичного кеша -- просто запусти
#  build_words.py, он соберёт words_defs.json из того, что есть в кеше.)

# 2) Сгенерировать дни и проверить.
$PY scripts/gen_puzzles.py       # -> data/puzzles.* + app/src/lib/game/data/days.js
$PY scripts/verify_puzzles.py    # обязательный гейт (должно быть ALL CHECKS PASSED)

# 3) Собрать приложение.
export PATH="$HOME/.local/node/bin:$PATH"
cd app && BASE_PATH=/ru-anagram-daily node node_modules/vite/bin/vite.js build
```

## ЕЩЁ НЕ СДЕЛАНО (после генерации)
- **Агент-курация подсказок** («несколько агентов», как в EN): для ~слов, реально
  попавших в паззлы, агенты выбирают/чистят лучшую клу из списка `clues` в
  words_defs.json (избегать циклических/загадок), обновляют `def`, регенерируют.
- **Семантический аудит однокоренных** параллельными агентами (как EN 7-way):
  найти пары А/Б/В с общим корнем, что стеммер пропустил -> добавить в
  `BLOCKED_TRIPLES` (формат `_triple_key("А","Б","В")`), регенерировать.
- Проверить день 0 (2026-07-06 = понедельник -> длина 9), качество первых дней.
- Backend: свой воркер `ru-anagram-stats` (D1) для глобальной статистики, затем
  прописать URL в `app/src/lib/config.js` STATS_API. Пока '' (локально работает).
- Интеграция в games-hub (`ImangulovA/games`): добавить запись kind анаграммы с
  prefix `ruanagram_day`, anchor [2026,6,6]. См. [[games-hub]].
- Создать репозиторий `ImangulovA/ru-anagram-daily`, включить Pages
  (build_type=workflow), запушить (Amal пушит; assistant не пушит без явного «ок»).
- Браузерный QA (Chrome/Playwright в песочнице заблокированы).

## Риски/заметки
- Клу graycell бывают загадочно-каламбурные («Друг собаки» = человек). rank_clue
  выбирает самые «толковые», но финальную чистку лучше сделать агентами.
- Покрытие ~29%: 25k кандидатов -> ~7k слов. Если триплетов на длины 11-13 мало,
  поднять --limit.
- graycell пишет кеш раз в 500 -> счётчик «замирает» между сохранениями; это норм.
