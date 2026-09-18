# Первый запуск v0.5.0

После commit/push обычный `CI` должен стать зелёным.

Затем:

1. **Actions → Update MaleCNS dopamine snapshot**.
2. `min_synapses` оставь `3`.
3. Запусти workflow.
4. Первый v0.5 heavy-run может быть заметно дольше прошлых: он впервые кэширует BANC v888 и FlyWire v783 источники для replication.
5. В Actions summary появятся обычные discovery counts и отдельный `PAM04 replication` status.
6. На Pages открой `state lab` и секцию **cross-connectome replication**.

## Что смотреть первым

Не начинай с симуляции. Сначала проверь:

- получил ли MaleCNS candidate `known subtype`;
- `known subtype check` для 158196 и 186566;
- сколько PAM04/subtype cells нашлось в BANC;
- сколько PAM04/subtype cells нашлось в FlyWire;
- есть ли `within-subtype` outliers и bilateral motif;
- какой итоговый replication status.

Если subtype не разрешился, это честно помечается как unresolved. Если внешний источник не скачался/не прочитался, workflow должен сохранить fail-soft status, а не придумать результат.

## ROI fix

Cache key ROI изменён, поэтому первый v0.5 run заново запросит compact MaleCNS ROI metadata. Теперь запрос включает `roiInfo`.

В summary проверь `ROI output coverage` и `targets with anatomical pool`. Если coverage снова 0%, dopamine-convergence часть всё ещё надо считать `global_only`; PAM04 exact-type/subtype тест от этого отдельно не ломается.

## State Lab

Live 3D State Lab остаётся: реальные skeletons/synapse coordinates плюс simulated glow/pulses/events.

После structural replication можно снова использовать `real / knockout / medianize / amplify / shuffle` и сохранять интересные run JSON. Но parameter sandbox идёт **после** subtype/cross-connectome проверки, а не вместо неё.
