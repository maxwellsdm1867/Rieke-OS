#!/bin/zsh -f
# Copy beside the completed preview's home/, profile/ and tmp/ directories.
# macOS built-ins and the bundled executable are the only launch dependencies.
set -eu
umask 077
preview_root="${0:A:h}"
preview_home="$preview_root/home"
preview_bundle="$preview_home/Applications/Rieke OS.app"
preview_profile="$preview_root/profile"
preview_tmp="$preview_root/tmp"
fail() { print -u2 -- "DISCO Preview could not open: $1"; exit 1; }
for folder in "$preview_root" "$preview_home" "$preview_home/Applications" "$preview_bundle"; do
  [[ -d "$folder" && ! -L "$folder" && -O "$folder" ]] || fail "Preview folders must be real directories owned by you."
done
for folder in "$preview_profile" "$preview_tmp"; do
  [[ ! -L "$folder" ]] || fail "The profile and temporary folders cannot be links."
  /bin/mkdir -p "$folder"
  [[ -d "$folder" && -O "$folder" ]] || fail "The profile and temporary folders must belong to you."
done
preview_info="$preview_bundle/Contents/Info.plist"
preview_manifest="$preview_bundle/Contents/Resources/runtime/runtime-manifest.json"
preview_marker=$(/usr/bin/plutil -extract DiscoLocalPreview raw -o - "$preview_info")
[[ "$preview_marker" == true ]] || fail "This app is not marked as a local preview."
preview_version=$(/usr/bin/plutil -extract application_version raw -o - "$preview_manifest")
preview_commit=$(/usr/bin/plutil -extract source_commit raw -o - "$preview_manifest")
print -- "DISCO Preview · $preview_version · source $preview_commit"
print -- "Using this preview folder's isolated settings and copied projects."
exec /usr/bin/env -i HOME="$preview_home" TMPDIR="$preview_tmp" LANG=en_US.UTF-8 \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin \
  "$preview_bundle/Contents/MacOS/Rieke OS" "--user-data-dir=$preview_profile"
