# Первый запуск v0.2.1

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
6. скачивает/кэширует официальные ROI meshes и строит из них облегчённый browser LOD;
7. вендорит приоритетные реальные neuron skeletons;
8. публикует GitHub Pages сайт.

Ожидаемый sanity check: dopamine core должен быть порядка сотен клеток, не тысяч. В проверенном MaleCNS run было 392 traced consensus-dopamine neurons. Если число внезапно становится >1000, importer специально падает.

## Что изменено в 3D после v0.2.0

В v0.2.0 браузер получал все 80 исходных ROI meshes (~7.27 млн треугольников) и сам преобразовывал их на main thread. Это было слишком тяжело и могло подвесить не только вкладку, но и GPU compositor браузера.

v0.2.1 оставляет исходные meshes в CI/cache как источник истины, а на сайт кладёт только детерминированный low-detail derivative. В `geometry.json` остаются source URL, source SHA-256, исходное число triangles и hash самого LOD.

Focus neuron загружается первым. Контекстные нейроны по умолчанию выключены и грузятся только по кнопке `context`.
