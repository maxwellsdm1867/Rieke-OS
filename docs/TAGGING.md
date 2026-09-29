# Cell and epoch tags

Tags are project annotations stored in DataJoint. Each annotation has an exact target UUID, a target kind (`cell` or `epoch`), a local author profile, and a revision. Changes are recorded in project activity. Profiles identify the claimed author; they are not authenticated accounts.

In the epoch browser, **Tags** lets you tag the focused epoch, its entire cell, or explicitly selected epochs. The whole-cell action applies to every epoch with that cell UUID, including epochs in other protocols and later imports. It does not use the visible cell label, date, tree position, or current predicate membership. Direct epoch tags and inherited cell tags are shown separately. Choose the author when opening a project or using the profile button at the bottom of the project rail. Tagging and tag import remain disabled until an author is explicitly selected; the OS username is only a suggestion.

Use **Cell tags**, **Epoch tags**, or **Effective tags** in Search predicate. Effective tags combine direct epoch and inherited cell annotations. Acquisition keywords and the older protocol-specific dataset tags remain separate fields. Tag chips can open an exact tag predicate.

## MATLAB and file exchange

In native EpicTreeGUI, use **Tags → Load tag JSON**, **Tag selected epochs** or **Tag cells of selected epochs**, then **Save tag JSON**. Unsaved tag edits prompt on close. The menu checks imported target UUIDs against the loaded tree before accepting them.

Use **Export tags** in the web app to download a portable tag JSON. It records the exact cell and epoch UUID registry and each tag's author. MATLAB uses the same identities:

```matlab
annotations = readWorkspaceTags('tags.json');
% Copy these UUIDs from the exported document; never substitute a row number.
annotations = workspaceTag(annotations, 'epoch', epochUuid, ...
    'reviewed-response', profileUuid, authorName);
writeWorkspaceTags(annotations, 'tags-reviewed.json');
```

Back in the web app, choose **Import tags**, select the JSON, review its additions, and import. Import is additive: matching existing authored tags are unchanged; missing tags in the input do not delete saved tags. Removing a tag is a separate explicit edit by its author. Reordering a MATLAB tree or exporting a subset does not change the identities.

The import preview validates target kind and UUID against the registered project. Unknown targets, duplicate targets, conflicting author identities, and stale previews are rejected. A cell label such as `Cell1` never identifies an import target. Tags from another project are matched only to the same exact registered acquisition UUIDs and are called out in the preview. Raw H5 files are not rewritten.

Samarjit hierarchical tag JSON is also supported for cell and epoch annotations. Author names in this legacy format are retained as imported claims. Tagged hierarchy levels that cannot be represented are rejected rather than silently discarded.

## Tags and inclusion masks

A MATLAB `.ugm` file is an inclusion mask, not a tag file. Use **Selection masks** in protocol inspection to import it. Inclusion decisions do not implicitly add or remove authored tags. Existing protocol-scoped curation tags stay in their original dataset scope and are not silently converted to shared annotations.

Wheeler SQLite and EpicTree MATLAB dataset exports include a frozen annotation snapshot. Later tag edits do not rewrite an earlier export.
