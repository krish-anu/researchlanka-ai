.PHONY: all figures clean

all: figures
	latexmk -pdf main.tex

figures:
	python generate_figures.py

clean:
	latexmk -C
