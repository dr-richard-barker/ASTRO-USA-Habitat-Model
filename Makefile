.PHONY: all fig2 cad check cfd-coarse post docs test vr
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
docs:
	uv run python -m habitat.docs_gen
test:
	uv run pytest -q
vr:
	uv run python -m habitat.vr.build
