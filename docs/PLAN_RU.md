# План проекта

## Идея

`dopaminergic-state-control` — не атлас, который надо листать руками. Код сам проходит по дофаминовой части MaleCNS, считает свойства сети и показывает кандидатов, которые отличаются от остальных.

Главный рабочий цикл:

`commit -> GitHub Actions -> analysis -> JSON/figures -> GitHub Pages`

Ты работаешь с кандидатами и экспериментами; рутинный поиск по графу делает код.

## v0.1 — Discovery Engine

1. Получить официальные MaleCNS v1.0 файлы.
2. Выделить нейроны с предсказанным dopamine выше заданной уверенности.
3. Оставить их прямые входы/выходы и связи выше порога synapse count.
4. Посчитать структурные признаки каждого DAN.
5. Найти robust outliers.
6. Найти цели с сильной конвергенцией нескольких DAN.
7. Показать кандидатов на собственном сайте.
8. Сохранить manifest, hashes, dataset version и параметры.

## Почему не делаем симуляцию сразу

Структура MaleCNS не содержит достаточной информации, чтобы честно объявить динамическую модель dopamine/D1/D2/ADHD. Сначала мы используем то, что dataset реально измеряет: wiring + annotations + predicted neurotransmitter.

## v0.2 — Null Models

После первого реального запуска добавляем проверки, которые отвечают: «это действительно необычно или просто следствие degree/размера/области мозга?»

Планируемые нулевые модели:

- degree-preserving edge rewiring;
- type-preserving permutations;
- region-conditioned comparisons (когда будет надёжный region layer);
- left/right matched comparisons для типов, где это корректно.

Только кандидаты, пережившие подходящий null, переходят в `experiments/`.

## v0.3 — Evidence layer

Не вручную каталогизировать весь мозг. Для surviving candidates код формирует маленький evidence packet: типы клеток, связи, направления, известные annotations и список поисковых терминов. Уже после этого читается литература по конкретному вопросу.

## v0.4 — Functional / dopamine-state hypotheses

Здесь могут появиться реальные вопросы про arousal, attention, sleep, DAT, D1-like/D2-like signalling и ADHD-relevant parallels — но только если они выросли из конкретной проверяемой находки.
