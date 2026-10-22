Unsigned Apple silicon testing release. Not production-qualified.

DISCO 0.1.24 fixes tree layout updates and recorded-field split controls.

- Applying or rearranging splits updates the tree automatically. Command-T / Ctrl-T retries the visible tree; preparation uses a neutral Show tree control.
- Add split and Combine into one level share a searchable recorded-field chooser, with protocol settings prioritized and recorded paths visible. Field selection does not request value summaries or display summary availability messages.
- Combined levels accept recorded fields, including History 1 + History 2 + Target and History 1 + History 2 + History 3 + Target. Additional splits can be placed above a combined level.

The affected native workflow was tested in the locally patched 0.1.23 app before this version bump: the four-field Triple History view rendered automatically with 138 total epochs; Cell1 groups summed to 21 and Cell2 groups summed to 103. Rearranging and Command-T retained a usable tree. Focused regression checks passed on the local fix; final CI and packaged evidence belong to the exact 0.1.24 source and archive, and are separate from that earlier native evidence.

This uses the existing unsigned Apple silicon testing download and update channel. It is not Developer ID signed or notarized. macOS 14 and later are the deployment target; macOS 14 runtime support remains unqualified and Intel is unsupported.
