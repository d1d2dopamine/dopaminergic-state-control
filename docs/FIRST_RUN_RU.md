# Первый запуск v0.4.0

После commit/push обычный `CI` должен стать зелёным.

Затем:

1. **Actions → Update MaleCNS dopamine snapshot**.
2. `min_synapses` оставь `3`, если мы специально не проверяем другой primary cutoff.
3. Запусти workflow.
4. В summary самого GitHub Action появятся counts по control statuses и первые элементы review queue.
5. На Pages открой `findings` и сначала фильтруй по `survived controls` / `survived thresholds`.

Внутренне workflow теперь хранит one-hop edges начиная с weight 1. Это не означает, что основной анализ стал использовать threshold 1: primary cutoff по-прежнему 3. Низкий floor нужен, чтобы тот же run мог проверить 1/3/5/10 без повторного скачивания connectome.

Если ROI metadata доступны, dopamine-input findings используют ROI-overlap availability null. Если нет — соответствующая карточка будет `global_only`, а не замаскирована под anatomy-controlled result.

3D остался инструментом проверки: серый прозрачный brain shell, реальные skeletons и, где применимо, реальные synapse sites.
