# Recorded retinal cell icons — October 11, 2026

The approved SVG design is integrated on top of local next-version source
`0dd3a9b0c83cd77ebb28c5ff6efe31e74e0d4a65` (`codex/next-version-integration`).
GitHub main was verified as `035e295ba01e648005dde24fc4cdbbc4dab412e4`.
The installed 0.1.10 application remains attributed to `31182a4`; this source-only
change does not replace it or publish a release.

## Presentation

`cell-qc/cellTypes.js` maps exact recorded type aliases to shape, ON/OFF polarity
and semantic theme colors. `components/CellTypeIcon.jsx` renders them. The shared
`NeuronIcon.jsx` now draws a side-view retinal ganglion cell, including its
shallow dendritic arbor and a descending axon. Midget arbors are narrower than
parasol arbors; OFF arbors are farther above the soma than ON arbors. Bipolar
cells have a small upper dendritic tuft and a separate lower axon terminal; the
ON terminal extends deeper than OFF. Cone and rod silhouettes retain their
approved tapered/cylindrical outer segments. All depths and sizes are schematic,
not quantitative morphology or a classifier of measured cells.

| Recorded category | Color role | Shape |
| --- | --- | --- |
| ON/OFF parasol | existing `cell-on-parasol` / `cell-off-parasol` | broad ganglion arbor |
| ON/OFF midget | existing `cell-on-midget` / `cell-off-midget` | compact ganglion arbor |
| ON/OFF bipolar | `cell-on-bipolar` / `cell-off-bipolar` | bipolar |
| Cone / cones | `cell-cone` | cone |
| Rod / rods | `cell-rod` | rod |

Exact aliases tolerate case, spaces, underscores and hyphens. RGC-prefixed
midget/parasol labels, Bipolar/BC-prefixed ON/OFF labels and Photoreceptor-prefixed
rod/cone labels are supported. Unknown and candidate labels remain neutral;
cell display names never determine type. Labels, UUIDs, grouping, distinct-cell
counts and inspection/QC actions retain their existing authority.

The shared mapping is used by project/protocol cell-type overview summaries and
accordions, bounded cell-list rows, incoming cell-type chips and individual-cell
selection overview. Decorative SVGs remain hidden from assistive technology;
adjacent recorded labels remain the accessible identity. Palette literals stay
in `themes.css` and existing ganglion colors are unchanged.

## Anatomical references

Original simplified paths were informed by inspection of these public figures:

- [Dacey & Petersen (1992), intracellularly stained midget and parasol cells](https://pmc.ncbi.nlm.nih.gov/articles/PMC50193/), Figure 1.
- [Fournel et al. (2022), multiphoton microscopy and bipolar reconstructions](https://pmc.ncbi.nlm.nih.gov/articles/PMC9310816/), Figures 2 and 4.
- [Tsukamoto & Omi (2016), macaque ON bipolar connectivity and ganglion stratification](https://www.frontiersin.org/journals/neuroanatomy/articles/10.3389/fnana.2016.00104/full), Figures 1 and 9.

## Validation

`cellTypes.test.js` exercises all eight mappings, spelling/prefix aliases,
polarity, neutral fallback and preservation of source labels. The mounted-source
SSR example `cellTypeIconsRendering.test.js` verifies the same recorded type in
all four icon-bearing surface families. Existing overview and incoming rendering
tests retain distinct-cell counts, navigation callbacks and disclosure behavior.
The approved light/dark design sheet was inspected at 44, 20 and 13 px.

Run the production frontend build, architecture guard, fixed core and both
required everyday-million comparisons. The pinned reference is `34ce2e0` and the
previous source is `0dd3a9b`; retain raw receipts under `benchmarks/results/cell-icons-*`.
Read their actual results before claiming a passing comparison. Browser drawings,
source tests and synthetic query checks do not establish installed/native or
release qualification.
