# Recorded retinal cell icons

Updated October 12, 2026. The complete recorded taxonomy extends local
next-version source `89e2c28be8ead29d94e9ae1d4303e71b1cd785d5` on
`codex/next-version-integration`. GitHub main was checked at
`8cd61822aa78bf6e9d221c90fbae6a5c8a90f66a`; the local combined work remains the
build handoff. This is a source change, not an installed or published package.

## Presentation and recorded identity

`cell-qc/cellTypes.js` maps exact recorded type aliases to an SVG shape, optional
subtype, polarity, and semantic color. `components/CellTypeIcon.jsx` owns the
schematics and `NeuronIcon.jsx` supplies the ganglion/unknown-neuron silhouette.
Recorded labels, UUIDs, grouping, counts, and QC authority remain unchanged.
Only source type metadata selects an icon; display names never classify cells.

All 19 leaf entries visible in the supplied Symphony type-picker photographs
are covered. Parent paths matter: `RGC/ON-midget` and `bipolar/ON-midget` have
different shapes, as do `photoreceptor/rod` and `bipolar/rod`. Both slash and
backslash separators, case, spaces, underscores, and hyphens are accepted.
Standalone ON/OFF midget retains its established RGC meaning. Use the bipolar
parent or an explicit label such as `ON midget bipolar` to specify a bipolar.

| Recorded category | Color | Schematic feature |
| --- | --- | --- |
| RGC / ON-parasol, OFF-parasol | shared ON teal / OFF purple | larger, wider soma and broad, fuller ganglion arbor |
| RGC / ON-midget, OFF-midget | shared ON / OFF | smaller soma and a narrow, compact tuft |
| RGC / small bistratified | neutral | smaller upper tier and broader lower tier |
| amacrine / AII | neutral | upper lobules and lower fine arbor |
| amacrine / A17 | neutral | long, sparse processes with varicosities |
| amacrine / starburst | neutral | broad, shallow arbor shown from the side |
| bipolar / ON-diffuse, OFF-diffuse | shared ON / OFF | wider dendritic and terminal fields |
| bipolar / ON-midget, OFF-midget | shared ON / OFF | compact tuft and terminal field |
| bipolar / rod | ON teal | dendritic tuft and a compact deep terminal arbor with rounded tips |
| horizontal | outer-retina blue | lateral arbor |
| photoreceptor / S cone, M cone, L cone | blue / green / coral | identical rounded cone shape |
| photoreceptor / rod | outer-retina blue | cylindrical outer segment |
| unknown | neutral | generic neuron |

Rod bipolar is a recognized ON type, not a rod photoreceptor. Small bistratified
and the amacrine subtypes remain neutral rather than acquiring a single inferred
ON/OFF assignment. Cone colors encode the recorded S/M/L category as a UI
convention, not literal cell appearance. Unspecified cones are neutral, so they
do not look identical to S cones. The established generic ON/OFF bipolar icons
remain available when polarity is recorded but the subtype is not.

Unrecognized subtypes under a recorded family use a neutral family silhouette:
ganglion, bipolar, amacrine, horizontal, or photoreceptor. An unknown family or
unqualified candidate label uses the neutral neuron. A known family never
promotes a tentative subtype to a confirmed subtype. Bare family labels and
common unspecified-family aliases are also supported.

The color palette is shared by class: `--cell-on`, `--cell-off`, and
`--cell-outer`, plus the three `--cell-cone-s/m/l` roles. Dark mode uses lighter
versions; neutral icons use the theme's muted ink. Palette literals live only in
`themes.css`. Morphology, depth, field size, branch count, and varicosity count
are schematic, not measurements or a morphology classifier. Icons use side-view schematics. Starburst uses a broad, shallow arbor instead
of a radial snowflake; this shorthand does not show its full en-face geometry.
The unspecified photoreceptor retains a rounded outer segment with two internal
lines representing stacked discs, plus a neutral basal ending. Disc and terminal
counts are schematic.

The shared mapping serves overview summaries/accordions, cell lists, incoming
chips, and selection overview. Decorative SVGs stay hidden from assistive
technology; adjacent recorded labels provide accessible identity.

## Anatomical references

These primary sources informed the original simplified SVG paths. Figure images
were inspected for bipolar and amacrine morphology; none is embedded in the app.
Species differences and within-type variability are not modeled by these icons.

- [Dacey & Petersen (1992)](https://pmc.ncbi.nlm.nih.gov/articles/PMC50193/), Figure 1: midget and parasol morphology.
- [Dacey (1993)](https://www.cambridge.org/core/journals/visual-neuroscience/article/abs/morphology-of-a-smallfield-bistratified-ganglion-cell-type-in-the-macaque-and-human-retina/803C3DAD9C4EF438835C4DDE6AF9C1D2): two-tier small bistratified morphology in macaque and human.
- [Tsukamoto & Omi (2016)](https://www.frontiersin.org/journals/neuroanatomy/articles/10.3389/fnana.2016.00104/full), Figure 1: macaque midget, diffuse, and rod bipolar reconstructions and stratification.
- [Zandt et al. (2017)](https://pmc.ncbi.nlm.nih.gov/articles/PMC5225199/), Figure 3: reconstructed AII cells in rat retinal slices; lobular and arboreal regions.
- [Grimes et al. (2010)](https://pmc.ncbi.nlm.nih.gov/articles/PMC2967021/), Figure 1: A17 neurites and varicosities in rat retina.
- [Kim et al. (2022)](https://pmc.ncbi.nlm.nih.gov/articles/PMC9126974/), Figure 6: radial macaque starburst morphology.

## Validation

An independent scientific visual review of the complete sheet identified the
radial starburst's snowflake appearance and the rod bipolar's isolated terminal
rings. Both were revised and visually re-reviewed; the rod bipolar was then simplified
to short terminal branches after the connected outline still read as a cloud.
The review also covered the generic
photoreceptor's disc lines requested by the scientist. No blocking issue remained
in these three schematics. Generic bipolar and horizontal were readable family
symbols; the shared unknown-neuron silhouette remains an abstract convention.
Fine subtype features, including A17 varicosities, cannot replace adjacent
recorded labels at 16 px.

`cellTypes.test.js` covers every photographed leaf, parent-path disambiguation,
spelling variants, generic family fallback, candidate-label refusal, and source
label preservation. `cellTypeIconsRendering.test.js` renders each category in
all four shared presentation surfaces. It checks distinct rod/bipolar and
midget/bipolar SVGs, distinct amacrine subtypes, and identical S/M/L cone geometry.
The complete preview includes all leaf types and generic fallbacks in Light,
Dark, and Fred, enlarged and at 24 and 16 px.

Run the production frontend build, architecture guard, fixed core, and both
required everyday-million comparisons. For the scientific visual review follow-up the pinned
reference is `34ce2e0`, and the previous source is `3a9957e`. Retain exact-source
receipts under `benchmarks/results/retinal-taxonomy-*` and `retinal-review-*` / `parasol-midget-*`; inspect actual results
before claiming a pass. Earlier icon iterations retain their own evidence.
These source, browser, and synthetic-query checks do not establish native,
installed, packaged, or release qualification.
