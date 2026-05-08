.PHONY: build preprocess pandoc clean serve

SRC       := main.tex
PROCESSED := build/processed.md
OUTPUT    := output/index.html
TEMPLATE  := templates/default.html
FILTER    := filters/boxes.lua
CSS       := styles/main.css

build: $(OUTPUT)

$(PROCESSED): $(SRC) scripts/preprocess.py
	mkdir -p build
	python3 scripts/preprocess.py $(SRC) $(PROCESSED)

$(OUTPUT): $(PROCESSED) $(TEMPLATE) $(FILTER) $(CSS)
	mkdir -p output/styles output/images
	cp $(CSS) output/styles/main.css
	cp *.png *.jpg *.jpeg *.svg *.pdf output/images/ 2>/dev/null || true
	pandoc $(PROCESSED) \
		--from markdown+raw_tex \
		--to html5 \
		--lua-filter $(FILTER) \
		--template $(TEMPLATE) \
		--mathjax \
		--toc \
		--toc-depth=3 \
		--number-sections \
		--metadata title="Advanced Macroeconomics" \
		-o $(OUTPUT)
	@echo "Built → $(OUTPUT)"

clean:
	rm -rf build output

serve: build
	python3 -m http.server 8080 --directory output
	@echo "Serving at http://localhost:8080"
