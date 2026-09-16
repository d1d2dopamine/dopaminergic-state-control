# Первый запуск после распаковки ZIP

## 1. Создай репозиторий

Название: `dopaminergic-state-control`

Распакуй содержимое ZIP в корень репозитория и сделай обычный commit/push.

## 2. Проверь CI

После push открой **Actions → CI**. Он должен:

1. установить Python;
2. установить пакет;
3. запустить тесты;
4. прогнать synthetic demo;
5. собрать demo-сайт как artifact.

Demo нужен только для проверки самого инструмента. Его намеренно нельзя трактовать как результат по мухе.

## 3. Включи GitHub Pages

Один раз:

**Settings → Pages → Build and deployment → Source → GitHub Actions**

После этого workflow `Build and deploy research site` сможет публиковать сайт вручную. Он специально не запускается на каждый push, чтобы synthetic demo не мог затереть уже опубликованный реальный результат.

До первого real-data run этот workflow можно использовать только как ручной preview synthetic demo.

## 4. Первый реальный запуск

Открой:

**Actions → Update MaleCNS dopamine snapshot → Run workflow**

Для первого запуска оставь:

- `min_synapses = 3`

Workflow автоматически:

1. скачает официальные MaleCNS v1.0 flat-connectome файлы;
2. посчитает SHA-256;
3. выберет `consensus_nt == dopamine` среди traced neurons;
4. построит 1-hop snapshot;
5. запустит discovery engine;
6. соберёт Findings / Network / Runs;
7. сохранит полный artifact;
8. задеплоит результат на твой GitHub Pages.

Первый запуск скачивает примерно 1.1 GB+ исходных файлов. Workflow использует Actions cache, поэтому последующие запуски той же версии dataset не должны каждый раз начинать с нуля, пока cache доступен.

## 5. Как работать дальше

Твой основной экран — `Findings`.

Не надо просматривать все нейроны. Сначала смотри кандидатов с высоким score. Если кандидат выглядит содержательно, тогда создаём отдельный каталог `experiments/00X_name/` и формулируем для него null model.

Никогда не меняй discovery threshold только потому, что хочется поднять конкретный кандидат выше. Если меняется метод — это новая версия метода.

## Что делать, если real-data workflow упал

Смотри конкретный failing step.

Особенно важны ошибки вида:

- upstream schema changed;
- no dopamine neurons selected;
- source file download failed;
- no edges survived filter.

Это не надо обходить молча. Если официальный dataset поменял schema или файл, адаптер надо обновить явно, сохранив старый manifest.

## Почему больше нет min_nt_confidence

MaleCNS хранит одновременно raw prediction и curated `consensus_nt`. Для идентичности нейромедиатора проект использует именно `consensus_nt`; confidence относится к raw prediction и не должен отбрасывать или переопределять consensus.
