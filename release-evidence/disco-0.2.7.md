Unsigned Apple silicon testing release. Not production-qualified.

DISCO 0.2.7 brings together the locally tested Cell QC and clean-close changes.

- Cell QC shows recorded rig and recording duration, and separates every non-QC protocol instead of combining them as Other.
- The Bath temperature tile opens recording conditions and per-epoch readings together. Recorded units stay explicit; readings below 28 °C or equivalent are red. Missing readings show Unmeasured, and numeric readings with unknown units show Unknown. Units are never inferred.
- Pipette solution is always shown. Internal additions and external additions appear independently when recorded; explicit N/A remains N/A and missing values remain Not recorded.
- Structural tree paging reuses compact indexes while preserving exact branch counts, epoch order, scope freshness, and existing prepared-view behavior.
- Cell QC starts the first trial independently of optional summaries and avoids repeated metadata reads. H5 reader preparation starts after project activation.
- Native process ownership remains stable across macOS clock changes. Clean-close retries preserve completed preparation and expose the failing shutdown phase.
- Runtime refresh refuses reuse when dependency or build inputs no longer match; annotation acknowledgment tests hold background reads to check the actual dependency.

Existing users can open **App Updates → Download update → Restart to update**.
For manual installation, download the Apple silicon ZIP, extract it and open
**Disco.app** normally. Project folders and recordings remain separate.

The attached desktop-release.json, SHA256SUMS and qualification-summary.json
identify the exact published archive, source and completed checks. Prior local
0.2.5/0.2.6 packages and measurements do not qualify these release bytes.

This app is unsigned and unnotarized. Apple silicon only; Intel is unsupported.
macOS 14+ is the deployment target, not validation on every OS version. macOS may
require **Privacy & Security → Open Anyway**. Signed updating and universal macOS
compatibility remain outside this testing qualification.
