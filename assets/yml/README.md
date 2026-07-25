# Asset YAMLs

Torch asset definitions for OoT ROM versions. This is torch's `--src` directory for every gate
and every check in this harness.

- `config.yml` — hand-maintained Torch config mapping ROM SHA1 hashes to version paths
- `<version>/` — per-file YAML asset definitions, produced by `zapd_to_torch.py`

The version directories are gitignored here and must be produced locally. Either clone them from
the repository that now owns them:

    git clone git@github.com:briaguya0/soh-asset-yml.git  # config.yml + the 14 version dirs

...or regenerate them, per version:

    python3 tools/zapd_to_torch.py \
        --xml-dir shipwright/soh/assets/xml/<XML_DIR> \
        --dma-json dma/<version>.json \
        --supplemental-json supplemental/<version>.json \
        --out-dir assets/yml/<version>

`--supplemental-json` is not optional in practice: without it only ~1.3k of ~18.5k assets are
declared and the comparison reports tens of thousands "not generated". See the root README for
the full pipeline (`extract_dma.py` → `generate_supplemental.py` → `zapd_to_torch.py`).

**`soh-asset-yml` is the source of truth for these files**, not this directory — it is what
Shipwright submodules, and it is edited directly. This harness generated its initial contents and
verifies them (19/19 ROM dumps byte-identical to the OTRExporter reference), but it does not own
them.
