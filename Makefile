.PHONY: install test demo serve clean
install:
	python -m pip install -e '.[dev]'
test:
	pytest
demo:
	dsc run --snapshot data/demo --config configs/demo.yml --output build/demo --site-template site
serve: demo
	python -m http.server 8000 --directory build/demo/site
clean:
	rm -rf build .pytest_cache
