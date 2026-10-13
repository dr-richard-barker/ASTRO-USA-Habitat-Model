# Third-party assets

**VR geometry and materials:** none. All are generated procedurally by `habitat/vr/blender/build_scene.py` (no
image textures, HDRIs or downloaded models). If textures are added later, record source, licence and URL here.

**Validation data:** `sources/annex20_lda.json` holds the laser-Doppler mean and RMS velocity profiles of the IEA
Annex 20 two-dimensional test case. They were converted by `sources/annex20_data.py` from Aalborg University's CFD
benchmark spreadsheet "592302 2D Benchmark Test Measurements New"
(https://en.build.aau.dk/web/cfd-benchmarks/two-dimensional-benchmark-test). The file's metadata gives
"Laser-doppler measurements of the two dimensional test case", author Arnkell Jónas Petersen, last saved by Peter V.
Nielsen, 2006. The test case is specified in Nielsen P.V. (1990) *Specification of a Two-Dimensional Test Case
(IEA)*, Aalborg University. No licence is stated on the page. The data are published as a public benchmark and are
used here with this attribution; confirm terms with Aalborg University before redistributing outside this repository.
