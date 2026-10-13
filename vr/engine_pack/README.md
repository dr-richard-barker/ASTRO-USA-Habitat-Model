# Engine-ready asset pack

Built by `make vr` into `out/vr/` (not committed; large binaries go to a GitHub Release / Zenodo when published).

| File | Use |
|---|---|
| `fpm_vr_lod0.glb` | hyper-detail glTF 2.0 — Unreal (glTF importer / Datasmith), Unity (glTFast), Omniverse, Blender |
| `fpm_vr_lod1.glb` | headset tier (budget 500 k triangles) |
| `fpm_vr_lod2.glb` | web tier (budget 300 k triangles) |
| `fpm_vr_lod0.usdz` / `.usdc` | OpenUSD — visionOS / Reality Composer Pro, Omniverse (`usdchecker`: Success) |
| `fpm_vr_lod0.fbx` | FBX for engines that prefer it (custom properties included) |
| `fpm_vr_lod0.blend` | Blender source scene |

Triangle and draw counts for the current build are in `out/vr/VR_QA.json` (written by `make vr`).

**Conventions.** glTF: metres, +Y up (Blender exporter maps model (x, y, z) → (x, z, −y)); the model frame is
x along the container from the door end, y from the printed bottom wall of ICES-2026-251 Fig 2 toward the hydroponic
wall, z up. CFD overlays (`vr/web/assets/*_age_*.glb`) use the same mapping and line up without offsets.

**Per-node metadata (glTF `extras`, FBX custom properties).** `element` (scene element id), `part` (registry part),
`layer` (e.g. structure, plants, power, air, crew, work, controls, payloads, site), `illustrative` (true = generic stand-in for
equipment the paper does not describe), `refs` (ledger records the element was built from). The root node carries
`ledger_digest`: compare it with `ASSUMPTIONS.md` to know which ledger version you are looking at.

**Import notes.**
- *Unreal 5*: import the GLB (Interchange glTF) at scale 100 (cm); enable "Combine meshes" off to keep per-part picking;
  plant instances arrive as `EXT_mesh_gpu_instancing` nodes — convert to Instanced Static Mesh components.
- *Unity*: glTFast keeps extras on `GltfAsset` nodes; GPU instancing nodes import as instanced renderers.
- Materials are plain metallic-roughness PBR without image textures (no third-party assets; see `ASSETS.md`).
