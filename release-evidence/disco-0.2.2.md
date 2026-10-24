Unsigned Apple silicon testing release. Not production-qualified.

DISCO 0.2.2 polishes the sidebar, author chooser, and macOS app icon.

- The macOS app icon fills its blue tile without the white surround. DISCO preserves the native icon at startup instead of swapping to a different rendering. Native ICNS assets keep the small Finder icon correct too.
- Appearance and App Updates use evenly spaced controls, optically centered icons, and rounded hover backgrounds without borders. The update icon stays in place across update states.
- The update dialog uses matching status artwork and evenly sized actions.
- The author chooser has clearer author initials, aligned profile rows, a compact Add author form, and a visible selected-author marker. Existing tags keep their original author.

These changes preserve scientific data handling, project storage, import review, merge/Undo, and export behavior. The same UI changes were checked in the local app before release packaging, including author switching, isolated author creation and cleanup, appearance switching, real update checks, and closed-app icon rendering. Release qualification is bound to the final source and immutable archive through the repository workflows.

Use App Updates in DISCO to download and restart into 0.2.2. The release ZIP and desktop-release.json use the existing unsigned testing update channel.

This app is not Developer ID signed or notarized. Apple silicon only; Intel is unsupported. macOS 14 and later are the deployment target, not a claim that every supported OS version was tested. The native icon appearance was verified on macOS 27.0.1.
