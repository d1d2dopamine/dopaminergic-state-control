# Первый запуск v0.4.2

После commit/push обычный `CI` должен стать зелёным.

Затем:

1. **Actions → Update MaleCNS dopamine snapshot**.
2. `min_synapses` оставь `3`, если мы специально не проверяем другой primary cutoff.
3. Запусти workflow.
4. В summary самого GitHub Action появятся counts по control statuses и первые элементы manual investigation queue.
5. На Pages открой `findings` и сначала фильтруй по `survived controls` / `survived thresholds`.

Внутренне workflow теперь хранит one-hop edges начиная с weight 1. Это не означает, что основной анализ стал использовать threshold 1: primary cutoff по-прежнему 3. Низкий floor нужен, чтобы тот же run мог проверить 1/3/5/10 без повторного скачивания connectome.

Если ROI metadata доступны, dopamine-input findings используют ROI-overlap availability null. Если нет — соответствующая карточка будет `global_only`, а не замаскирована под anatomy-controlled result.

3D остался инструментом проверки: серый прозрачный brain shell, реальные skeletons и, где применимо, реальные synapse sites.

## Experiment 001 / State Lab

Начиная с v0.4.2 реальный heavy-run автоматически строит `Experiment 001 — PAM04 input specialization`.

После зелёной сборки открой `state lab` на GitHub Pages. Главный экран теперь — живой 3D playback: реальные MaleCNS skeletons светятся по модельной активности, по ним идут simulated pulse markers, реальные synapse sites вспыхивают, а ниже синхронно двигаются raster событий, activity trace и mini circuit. Можно выбрать PAM04-кандидата, upstream cell-type channel и сравнить исходную структуру с `knockout`, `medianize`, `amplify` или детерминированным `shuffle`.

Ползунки `dopamine tone`, `DAT clearance`, `Dop1R1`, `Dop1R2`, `Dop2R` относятся к модельному слою, а не к измеренным значениям конкретных клеток. Это специально подписано на сайте.

Если комбинация параметров выглядит интересной, нажми **export run JSON** и положи файл в `experiments/001_pam04/scenarios/`. Следующий `Update MaleCNS dopamine snapshot` воспроизведёт этот JSON уже в Python/CI и положит результат в research artifact и на сайт в список committed CI scenarios.
