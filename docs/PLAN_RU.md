# План исследования — v0.5

## Главная смена направления

UI на этом этапе замораживаем. Следующая задача — не делать симулятор красивее, а попытаться **уничтожить гипотезу PAM04**.

Наш текущий MaleCNS lead: несколько PAM04 имеют необычно концентрированный вход. Но для PAM04 уже известна внутренняя типизация, поэтому простая фраза «PAM04 неоднородны» не является новой.

Вопрос v0.5:

> остаётся ли аномалия `max_input_share` внутри явно аннотированного PAM04-подтипа и повторяется ли похожий структурный motif в независимых connectomes?

## Шаг 1 — known-subtype check

Для каждой MaleCNS PAM04 pipeline подтягивает доступные identity-поля из `male-cns:v1.0` neuPrint:

- FlyWire type;
- Hemibrain type;
- supertype;
- hemilineage;
- dimorphism;
- synonyms.

Подтип считается известным только если в annotation/match поле явно присутствует имя вида `PAM04-*`. Код не кластеризует клетки и не придумывает subtype из той же метрики, которую потом тестирует.

Если у подтипа минимум 4 клетки, `max_input_share` пересчитывается внутри этого подтипа.

Интерпретация:

- `persists_within_known_subtype` — кандидат остаётся сильным outlier внутри известного subtype;
- `compatible_with_known_subtype_structure` — глобальная «аномалия» объясняется известной subtype-структурой;
- `subtype_too_small` — мало peers;
- `known_subtype_unresolved` — нет явной subtype annotation.

## Шаг 2 — BANC v888

В BANC берём только строго proofread PAM04 для connectivity-sensitive теста.

Для каждой клетки считаем при connection threshold `count >= 5`:

- total incoming weight;
- число presynaptic partners;
- долю самого сильного входа;
- global robust-z;
- within-known-subtype robust-z, если subtype достаточно большой;
- наличие outlier слева и справа.

Это structural replication. Мы не требуем одинаковых root IDs между мухами.

## Шаг 3 — FlyWire v783

Тот же тест проводится на FlyWire PAM04.

FlyWire connectivity хранит pair-neuropil rows, поэтому pipeline сначала агрегирует их до neuron-to-neuron pair, затем применяет threshold 5. Это делает метрику сопоставимой по смыслу с BANC/MaleCNS, хотя сами datasets и synapse detectors различаются.

## Шаг 4 — правило решения

`experiment_001_replication.json` показывает отдельно MaleCNS / BANC / FlyWire.

Мы не объявляем «репликацию» только потому, что где-то есть большой z-score. Смотрим:

1. разрешён ли известный subtype;
2. есть ли within-subtype outlier;
3. повторяется ли motif на обеих сторонах внутри external dataset;
4. повторяется ли он в одном или обоих независимых connectomes.

Возможные исходы:

- pattern объясняется known subtype → PAM04 становится validation case для detector;
- pattern есть только в MaleCNS → вероятная individual/connectome variation, PAM04 закрываем;
- pattern есть в одном внешнем connectome → продолжаем осторожно;
- pattern появляется в обоих внешних connectomes → делаем synapse-level spatial comparison и только потом усиливаем mechanistic simulation.

## ROI-анатомический null

v0.5 также чинит старую проблему 0% ROI coverage.

Если `inputRois/outputRois` пустые, compact neuPrint fetch теперь получает `roiInfo` и извлекает:

- input ROI, если `post > 0`;
- output ROI, если `pre > 0`.

Старый пустой cache считается непригодным и автоматически заменяется. Если и новый запрос не даёт usable coverage, convergence остаётся `global_only`.

## Что делаем после зелёного v0.5 heavy run

1. Смотрим `Experiment 001 → replication`.
2. Проверяем, получили ли 158196 и 186566 явные known subtypes.
3. Смотрим within-subtype z, а не только глобальный PAM04 z.
4. Сравниваем BANC и FlyWire.
5. Только если PAM04 пережил эти проверки, строим spatial/synapse consensus и parameter sweeps State Lab.
6. Если не пережил — не спасаем гипотезу, а переходим к PAM05/PAM13 тем же pipeline.

Live State Lab остаётся инструментом понимания и counterfactual-моделирования, а не доказательством физиологии.
