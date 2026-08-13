# Asset YAMLs

Torch asset definitions for Majora's Mask ROM versions. This is torch's `--src`
directory for every check in this harness.

- `config.yml` — hand-maintained Torch config mapping ROM SHA1 hashes to version
  paths, plus the `filelist:` each version resolves named offsets against
- `<version>/` — per-file YAML asset definitions, produced by `zapd_to_torch.py`

Generate per-version YAMLs with (run from the harness root):

    python3 tools/zapd_to_torch.py \
        --xml-dir 2ship/mm/assets/xml/N64_US \
        --dma-json dma/<version>.json \
        --supplemental-json supplemental/<version>.json \
        --out-dir assets/yml/<version>

The version directories are gitignored and must be regenerated locally.

Segment offsets are emitted as **DMA file names**, not hex ROM addresses —

    :config:
      segments:
        - [ 6, object_link_child ]

— which Torch resolves through the `filelist:` named in `config.yml` (Torch
PR #253). That keeps the `:config:` header version-independent, so a second ROM
version reuses this tree instead of needing its own copy.
