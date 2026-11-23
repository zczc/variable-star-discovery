# Public photometry archive: 2000-target discovery search

Unchanged public TESS SPOC FITS, compressed losslessly. This is a data archive for reproducibility. It is not an announcement of new variables or a VSX submission. The fixed target/protocol commit is fd0d79e9.

Each tar asset contains repository-relative `.fits.gz` paths. The adjacent `shard-NNN.json` in the repository records compressed and original FITS SHA256 hashes, public MAST URIs and the verified GitHub asset digest. Original acquisition receipts, scripts, results and plots remain in the repository. Extract an asset from the repository root to restore exactly those file bytes. No private credentials or user data are included.

Large later tar archives use 16 MB `.tar.part-NNN` assets. Their manifests contain an ordered `parts` list. Download those parts, concatenate in numerical order to the original `.tar` filename, and verify `archive_sha256` before extraction. Each part also has its own verified GitHub digest. Never extract an individual part as if it were a complete tar.

`evidence-NNN.json` describes bulk original diagnostic PNGs and the full CC BY 4.0 Zenodo catalogue. These follow the same repository-relative extraction and multipart rules. All 4,000 initial light curves, the 83 additional light curves, and the reviewed target-pixel inputs are indexed in the FITS shard manifests. Some completed local caches were released only after successful public publication and checksum checks; the release ledgers record exactly which files.

GitHub release: https://github.com/zczc/variable-star-discovery/releases/tag/discovery-2000-2026-11-23-data
