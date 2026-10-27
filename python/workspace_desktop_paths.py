"""Keep desktop project and generated data outside the immutable app bundle."""
import os
from pathlib import Path


def require_external_data_path(path, *, reject_ancestor=True):
    """Check resolved parents before any creation, lock or scientific write."""
    target = Path(path).expanduser().resolve()
    runtime = os.environ.get('RIEKE_DESKTOP_RUNTIME')
    if os.environ.get('RIEKE_DESKTOP_MODE') != '1':
        return target
    if not runtime:
        raise ValueError('Desktop runtime ownership is unavailable; project writes are disabled.')
    runtime = Path(runtime).resolve()
    resources = runtime.parent
    # Packaged resources are Resources/runtime. Protect the outer app including
    # Electron code, not only the Python application subtree. Scratch runtime
    # tests without an outer .app still protect their entire resource directory.
    bundle = resources.parent.parent
    protected = bundle if bundle.suffix == '.app' else resources
    protected_roots = [protected]
    application_store = (Path.home() / 'Library/Application Support/Rieke OS/application-versions').resolve()
    if protected.is_relative_to(application_store):
        # Generation-capable desktop sessions share an immutable application
        # store. Other generations and the stable front door are application
        # bytes too, even though this session's executable lives elsewhere.
        protected_roots.extend((application_store,
                                (Path.home() / 'Applications/Disco.app').resolve(),
                                (Path.home() / 'Applications/.Rieke OS.previous.app').resolve()))
    if any(target.is_relative_to(root) or (reject_ancestor and root.is_relative_to(target))
           for root in protected_roots):
        raise ValueError('Project data and generated files must be stored outside the application bundle. Choose a separate project folder.')
    return target
