# Первый запуск v0.2

После commit/push обычный `CI` должен стать зелёным.

Затем запускай:

**Actions → Update MaleCNS dopamine snapshot → Run workflow**

Для `min_synapses` оставь `3`.

Workflow:

1. восстанавливает/скачивает официальный MaleCNS v1.0;
2. выбирает `consensus_nt == dopamine`;
3. во время полного прохода по edge table считает full traced input degree для null model;
4. строит bounded dopamine snapshot;
5. запускает within-type, left/right и convergence screens;
6. генерирует manifest официальной 3D геометрии;
7. публикует собственный GitHub Pages сайт.

После зелёного run не надо вручную разбирать логи. Сохрани run как provenance; findings анализируются уже по опубликованному artifact/site.

Ожидаемый sanity check: dopamine core должен быть порядка сотен клеток, не тысяч. В v0.1.1 было 392 traced consensus-dopamine neurons. Если число внезапно становится >1000, importer специально падает.

3D шаг тяжелее старого сайта: workflow копирует официальные ROI meshes и до 256 приоритетных skeletons в Pages artifact. Остальные контекстные skeletons при открытии кандидата берутся напрямую из официального MaleCNS public storage. Это не отдельный сторонний viewer — интерфейс и рендерер принадлежат этому репозиторию.
