# План исследования — v0.4

## Что изменилось

Мы больше не хотим страницу из пятидесяти «странностей». Задача v0.4 — пытаться уничтожить каждый кандидат простыми объяснениями до того, как мы вообще начнём им интересоваться.

Код теперь спрашивает не только «это большое число?», а:

- сохраняется ли эффект при пороге связей 1 / 3 / 5 / 10;
- сравнивается ли нейрон именно со своим exact type;
- есть ли похожая аномалия на противоположной стороне;
- не тянет ли результат одна огромная связь;
- для dopamine convergence: могли ли потенциальные presynaptic клетки вообще попадать в те же ROI, куда target получает входы;
- если есть реальные synapse coordinates: занимают ли разные dopamine sources отдельные территории на target.

## ROI-availability null

Для target берём его `inputRois`. Для каждого traced source смотрим `outputRois`. Source попадает в допустимый pool, если есть хотя бы одно пересечение.

После этого спрашиваем: при фиксированном полном in-degree target насколько необычно получить наблюдаемое число dopamine sources из этого анатомически доступного pool?

Это лучше глобального перемешивания всего CNS, но это ещё не геометрический contact model. Два нейрона могут иметь общий ROI и всё равно физически не встречаться.

Если ROI данных не хватает в flat annotations, CI пытается получить только компактные `bodyId/inputRois/outputRois` из закреплённого `male-cns:v1.0` neuPrint и кэширует ответ. Если и это недоступно, карточка не притворяется anatomy-controlled: она получает статус `global_only`, а источник/coverage ROI остаётся в `snapshot_meta.json` и Actions summary.

## Статусы findings

- `survived_controls` — direct dopamine-input candidate прошёл ROI null и устойчивость по thresholds;
- `survived_thresholds` — exact-type outlier устойчив по thresholds, но это не causal result;
- `threshold_sensitive` — результат сильно зависит от cutoff;
- `global_only` — для convergence доступен только старый global degree null;
- `candidate` — отдельный detector дал lead, но полного набора v0.4 controls для него нет.

`review_queue.json` содержит только первые две категории. Именно с неё стоит начинать ручной разбор.

## Spatial synapse evidence

Для direct dopamine-input findings CI получает реальные pre/post synapse positions из MaleCNS neuPrint. Для queried dopamine sources считается доля пространственной вариации post-sites, объясняемая source identity (`eta²`). Source labels переставляются permutation test'ом, затем p-values корректируются BH.

Высокое значимое eta² значит: разные dopamine sources занимают различимые территории на target среди **запрошенных dopamine inputs**. Это не тест «dopamine clustered against all other transmitters».

## Что после первого реального v0.4 run

1. Берём `review_queue.json`.
2. Проверяем самые устойчивые 3–10 кандидатов на reconstruction/annotation артефакты.
3. Для оставшихся делаем глубокий literature/preprint novelty search.
4. Только после этого выбираем `Experiment 001` и начинаем связывать конкретный circuit mechanism с D1/D2/DAT/internal-state literature.

## Experiment 001 — PAM04

Первый focused experiment проверяет, имеет ли необычно концентрированный вход части PAM04 функциональное значение хотя бы в простой connectome-constrained модели.

Порядок проверки:

1. exact-type структурный кандидат и robustness thresholds;
2. bilateral evidence;
3. реальные upstream/downstream partners;
4. counterfactual `knockout / medianize / amplify / shuffle`;
5. parameter sweeps в State Lab;
6. только после устойчивого model effect — независимая replication / литература / более биофизическая модель.

State Lab не превращает модельный результат в биологический вывод. Его задача — быстро находить counterfactuals, которые стоит проверять дальше.


## Live State Lab v0.4.2

Чтобы проверка не сводилась к чтению таблиц, Experiment 001 теперь воспроизводится как синхронный визуальный playback. Анатомия и точки синапсов остаются реальными MaleCNS данными; яркость нейронов, движущиеся импульсы, event raster и задержки — только визуализация текущей rate-модели.

Во время одного запуска нужно глазами сравнивать одинаковый stimulus в `real` и контрфактуальном режиме. Если эффект виден только в красивой анимации, но исчезает по численным trace/summary, это не считается подтверждением. И наоборот, визуал нужен, чтобы быстро понять *где* в реальной геометрии возникает различие и какую следующую проверку имеет смысл поставить.
