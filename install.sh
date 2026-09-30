#!/bin/sh
# Bootstrap only application-local tools; no sudo, Docker, or global installs.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
case "$(uname -s)-$(uname -m)" in
  Darwin-arm64) platform=osx-arm64 ;;
  Darwin-x86_64) platform=osx-64 ;;
  Linux-x86_64) platform=linux-64 ;;
  Linux-aarch64) platform=linux-aarch64 ;;
  *) echo 'Supported: macOS and Linux on Intel/AMD or ARM64.' >&2; exit 1 ;;
esac
runtime="$PWD/.rieke-runtime"
mkdir -p "$runtime/tools"
if [ ! -x "$runtime/tools/bin/micromamba" ]; then
  archive="$runtime/tools/micromamba.tar.bz2"
  curl --fail --location --silent --show-error "https://micro.mamba.pm/api/micromamba/$platform/2.3.2" -o "$archive"
  tar -xjf "$archive" -C "$runtime/tools" bin/micromamba
  rm "$archive"
fi
export MAMBA_ROOT_PREFIX="$runtime/mamba"
export UV_PYTHON_INSTALL_DIR="$runtime/python"
export UV_CACHE_DIR="$runtime/uv-cache"
operation=create
if [ -d "$runtime/native/conda-meta" ]; then operation=install; fi
if [ -f "packaging/native-$platform.lock" ]; then
  "$runtime/tools/bin/micromamba" "$operation" --yes --prefix "$runtime/native" \
    --file "packaging/native-$platform.lock"
else
  "$runtime/tools/bin/micromamba" "$operation" --yes --prefix "$runtime/native" \
    --channel conda-forge --override-channels mysql-server=8.4.2 nodejs=22 uv git cxx-compiler
fi
# Bootstrap Python outside the compiler environment. conda-forge's
# install_name_tool can invalidate the relocated Python dylib signature on macOS.
# Apple's system tool preserves/replaces the signature correctly.
python_tools_path="/usr/bin:/bin:/usr/sbin:/sbin"
PATH="$python_tools_path" "$runtime/native/bin/uv" python install --no-bin 3.11.13
if [ "$(uname -s)" = Darwin ]; then
  for library in "$runtime"/python/cpython-3.11.13-*/lib/libpython3.11.dylib; do
    if [ -f "$library" ] && ! /usr/bin/codesign --verify "$library" 2>/dev/null; then
      PATH="$python_tools_path" "$runtime/native/bin/uv" python install --no-bin --reinstall 3.11.13
      /usr/bin/codesign --verify "$library"
    fi
  done
fi
export PATH="$runtime/native/bin:$PATH"
# Execute inside the tool environment to activate its compiler and SDK settings.
"$runtime/tools/bin/micromamba" run --prefix "$runtime/native" \
  uv run --no-project --python 3.11.13 python rieke.py setup
printf '\nInstalled. Start Disco with: ./start.sh\n'
