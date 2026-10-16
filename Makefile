.PHONY: manuscript all fig2 cad check cfd-coarse post light docs test vr drawings report
all: fig2 cad check docs test
fig2:        ## needs the team PDF in sources/private/
	uv run python -I sources/extract_fig2.py sources/private/ICES-2026-251.pdf sources/fig2_geometry.json
cad:
	uv run python -m habitat.cad.build
check:
	uv run python -m habitat.checks.fig2_overlay
cfd-coarse:
	uv run python -m habitat.cfd.case --mesh coarse --run --np 4
post:
	uv run python -m habitat.cfd.post runs/fpm_m0_coarse
light:
	uv run python -m habitat.light_budget
	uv run python -m habitat.s3_hvac_off
docs: light
	uv run python -m habitat.docs_gen
	uv run python -m habitat.brief
test:
	uv run pytest -q
vr:
	uv run python -m habitat.vr.build
	uv run python -m habitat.vr.nav
drawings:
	uv run python -m habitat.drawings
	uv run python -m habitat.drawings_cad
report: drawings
	uv run python -m habitat.report

manuscript:   ## numbers, figures and tables from the result files, then the PDF (the PDF is git-ignored; the figures and tables are committed)
	uv run python -m habitat.manuscript_numbers
	uv run python -m habitat.manuscript_figures
	cd manuscript && latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
