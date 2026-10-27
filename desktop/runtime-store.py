"""Private, short runtime-store transactions. Never operates on project data.

The process holding flock performs the mutation itself: losing the lock holder
cannot leave a second process continuing a transaction without exclusion.
"""
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid


HASH = re.compile(r"[a-f0-9]{64}\Z")
TOKEN = re.compile(r"[a-f0-9-]{36}\Z")


def private(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022 or path.resolve() != path:
        raise ValueError("Runtime directory must be physically located and user-owned")


def read(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022 or info.st_size > 10485760:
        raise ValueError("Invalid runtime record")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("Runtime record must be an object")
    return value


def write(path, value):
    temporary = path.with_name(path.name + "." + str(uuid.uuid4()) + ".tmp")
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def generation(root, identifier):
    if not isinstance(identifier, str) or not HASH.fullmatch(identifier):
        raise ValueError("Invalid runtime identity")
    directory = root / "generations" / identifier
    record = read(directory / "generation.json")
    if record.get("format") != "disco-runtime-generation" or record.get("version") != 1 or record.get("id") != identifier or not isinstance(record.get("manifest"), dict):
        raise ValueError("Invalid generation record")
    manifest = record["manifest"]
    if manifest.get("format") != "rieke-desktop-runtime" or manifest.get("version") != 1 or manifest.get("platform") != "darwin" or manifest.get("architecture") != "arm64" or not isinstance(manifest.get("mysql_version"), str) or type(manifest.get("database_compatibility")) is not int or not isinstance(manifest.get("workspace_formats"), list):
        raise ValueError("Invalid generation compatibility record")
    version(manifest)
    bundle = directory / "Disco.app"
    if bundle.resolve() != bundle or not bundle.is_dir():
        raise ValueError("Invalid generation bundle")
    return dict(record, bundle=str(bundle))


def current(root):
    value = read(root / "current.json")
    if value.get("format") != "disco-current-runtime" or value.get("version") != 1 or not isinstance(value.get("revision"), str):
        raise ValueError("Invalid current runtime pointer")
    return dict(value, generation=generation(root, value["id"]))


def version(manifest):
    value = manifest["application_version"]
    if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise ValueError("Invalid runtime version")
    return tuple(map(int, value.split(".")))


def compatible(candidate, previous):
    return all(candidate[key] == previous[key] for key in (
        "format", "version", "platform", "architecture", "mysql_version", "database_compatibility", "workspace_formats"))


def hold_profile_witnesses(ticket, held, application):
    """Read-only backend ownership exclusion for an interrupted GUI lease.

    Hold the existing root lock while retirement inspects descendants. Project
    liveness uses the backend's owning read-only port, never a second MySQL
    ownership interpretation or a requirement for a clean database receipt.
    """
    import psutil
    profile = ticket.get("selected_profile")
    if not profile:
        # Admission precedes final profile binding, which precedes backend spawn.
        return True
    backend = Path(profile) / "backend"
    if not backend.exists():
        return True
    if backend.resolve() != backend or not backend.is_dir():
        return False
    lock = backend / "desktop-session.lock"
    registry_path = backend / "desktop-services.json"
    try:
        info = lock.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            return False
        fd = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            os.close(fd)
            return False
        held.append(fd)
    except FileNotFoundError:
        return not registry_path.exists()
    try:
        registry = read(registry_path)
    except FileNotFoundError:
        return True
    if registry.get("version") != 1:
        return False
    records = []
    for key in ("services", "database_operations", "recovery_required"):
        values = registry.get(key, [])
        if not isinstance(values, list) or any(not isinstance(value, dict) for value in values):
            return False
        records.extend(values)
    for record in records:
        witness = record.get("service_owner", record)
        if "pid" in witness:
            if type(witness["pid"]) is not int or witness["pid"] <= 0:
                return False
            try:
                owner = psutil.Process(witness["pid"])
                if owner.status() != psutil.STATUS_ZOMBIE and (not isinstance(witness.get("created_at"), (int, float)) or owner.create_time() == witness["created_at"]):
                    return False
            except (psutil.NoSuchProcess, psutil.ZombieProcess):
                pass
            except psutil.AccessDenied:
                return False
        project = record.get("project_path")
        if not isinstance(project, str) or not Path(project).is_absolute() or not application:
            return False
        if application not in sys.path:
            sys.path.insert(0, application)
        from disco.projects.runtime_state import project_runtime_state, RUNNING
        if project_runtime_state(project)["state"] in RUNNING:
            return False
    return True


def execute(root, request):
    operation = request["operation"]
    def release_preparation():
        token = request.get("preparation")
        if token:
            if not TOKEN.fullmatch(token):
                raise ValueError("Invalid runtime preparation")
            file = root / "preparations" / (token + ".json")
            if read(file)["pid"] != os.getppid():
                raise ValueError("Runtime preparation belongs to another process")
            file.unlink()
    if operation == "prepare":
        selected = generation(root, request["id"])
        private(root / "preparations")
        token = str(uuid.uuid4())
        write(root / "preparations" / (token + ".json"), dict(id=selected["id"], pid=os.getppid()))
        return dict(selected, preparation=token)
    if operation == "pin-current":
        selected = current(root)
        private(root / "maintenance")
        token = str(uuid.uuid4())
        write(root / "maintenance" / (token + ".json"), dict(id=selected["id"], pid=os.getppid()))
        return dict(selected, pin=token)
    if operation == "unpin":
        if not TOKEN.fullmatch(request["token"]):
            raise ValueError("Invalid runtime maintenance pin")
        file = root / "maintenance" / (request["token"] + ".json")
        if read(file)["pid"] != os.getppid():
            raise ValueError("Runtime maintenance belongs to another process")
        file.unlink()
        return dict(ready=True)
    if operation == "restart-handoff":
        selected = generation(root, request["id"])
        private(root / "handoffs")
        token = str(uuid.uuid4())
        receipt = dict(format="disco-generation-restart", version=1, nonce=token, root=str(root), id=selected["id"],
                       profile=request["profile"], identity=request["identity"], expires_at=time.time() + 150)
        file = root / "handoffs" / (token + ".json")
        write(file, receipt)
        release_preparation()
        return dict(file=str(file), nonce=token)
    if operation == "claim-handoff":
        import psutil
        token = request["token"]
        if not TOKEN.fullmatch(token):
            raise ValueError("Invalid runtime restart")
        file = root / "handoffs" / (token + ".json")
        receipt = read(file)
        helper = psutil.Process(os.getppid())
        if receipt.get("helper_pid") or receipt.get("expires_at", 0) < time.time() or helper.exe() != receipt["identity"]["executable"] or helper.ppid() != receipt["identity"]["pid"]:
            raise ValueError("Runtime restart helper does not match its parent")
        receipt.update(helper_pid=helper.pid, helper_created_at=helper.create_time())
        write(file, receipt)
        return dict(ready=True)
    if operation == "publish":
        staging = Path(request["staging"])
        if staging.parent != root or not staging.name.startswith("staging-") or staging.resolve() != staging:
            raise ValueError("Invalid staging directory")
        record = read(staging / "generation.json")
        if not HASH.fullmatch(record["id"]):
            raise ValueError("Invalid staged identity")
        destination = root / "generations" / record["id"]
        if not destination.exists():
            os.rename(staging, destination)
        return execute(root, dict(operation="prepare", id=record["id"]))
    if operation == "activate":
        candidate = generation(root, request["id"])
        try:
            prior = current(root)
        except FileNotFoundError:
            prior = None
        except (ValueError, KeyError):
            os.rename(root / "current.json", root / ("invalid-current-" + str(uuid.uuid4()) + ".json"))
            prior = None
        expected = request.get("rollbackRevision")
        if expected and (not prior or prior["revision"] != expected):
            raise ValueError("A newer activation superseded this rollback")
        def finish(value):
            # Keep the selected target pinned through the caller's asynchronous
            # drain. Reserve/restart-handoff replaces this pin atomically.
            prepared = execute(root, dict(operation="prepare", id=value["id"]))
            release_preparation()
            return dict(value, generation=prepared)
        if prior:
            if not compatible(candidate["manifest"], prior["generation"]["manifest"]):
                raise ValueError("Runtime formats are incompatible")
            order = (version(candidate["manifest"]) > version(prior["generation"]["manifest"])) - (version(candidate["manifest"]) < version(prior["generation"]["manifest"]))
            if order < 0 and not expected:
                return finish(prior)
            if order == 0 and candidate["id"] != prior["id"]:
                raise ValueError("Different runtime contents claim the same application version")
            if candidate["id"] == prior["id"]:
                return finish(prior)
        pointer = dict(format="disco-current-runtime", version=1, id=candidate["id"], revision=str(uuid.uuid4()), previous=prior["id"] if prior else None)
        write(root / "current.json", pointer)
        return finish(dict(pointer, generation=candidate))
    if operation == "reserve":
        handoff_file = None
        if request.get("handoff"):
            import psutil
            token = request["handoff"]
            if not TOKEN.fullmatch(token):
                raise ValueError("Invalid runtime restart")
            handoff_file = root / "handoffs" / (token + ".json")
            handoff = read(handoff_file)
            helper = psutil.Process(os.getppid())
            if handoff.get("helper_pid") != helper.pid or handoff.get("helper_created_at") != helper.create_time() or handoff["id"] != request.get("id") or handoff["profile"] != request.get("profile"):
                raise ValueError("Runtime restart helper identity changed")
        selected = generation(root, request["id"]) if request.get("id") else current(root)["generation"]
        profile = request["profile"]
        if not Path(profile).is_absolute():
            raise ValueError("An exact session profile is required")
        private(root / "admissions")
        token = str(uuid.uuid4())
        ticket = dict(format="disco-runtime-admission", version=1, id=selected["id"], profile=profile,
                      recover=bool(request.get("recover")), fresh=bool(request.get("fresh")), token=token, expires_at=time.time() + 300)
        file = root / "admissions" / (token + ".json")
        write(file, ticket)
        release_preparation()
        if handoff_file:
            handoff_file.unlink()
        args = ["/usr/bin/open", "-n", "-a", selected["bundle"], "--args", "--user-data-dir=" + profile, "--disco-runtime-admission=" + token]
        if ticket["recover"]:
            args.append("--disco-recover-session")
        elif ticket["fresh"]:
            args.append("--disco-new-session")
        return dict(bundle=selected["bundle"], args=args, generation=selected["id"])
    if operation in ("admit", "bind-profile", "retire"):
        import psutil
        token = request["token"]
        if not TOKEN.fullmatch(token):
            raise ValueError("Invalid runtime admission")
        file = root / "admissions" / (token + ".json")
        ticket = read(file)
        selected = generation(root, ticket["id"])
        owner = psutil.Process(request["pid"])
        executable = str(Path(selected["bundle"]) / "Contents/MacOS/Disco")
        if owner.exe() != executable or owner.pid != os.getppid():
            raise ValueError("Runtime admission belongs to another executable")
        if operation == "admit":
            if ticket.get("pid") or ticket.get("retired") or ticket.get("expires_at", 0) < time.time() or ticket["profile"] != request["profile"] or ticket["fresh"] != request["fresh"] or ticket["recover"] != request["recover"]:
                raise ValueError("Runtime admission does not match this session")
            ticket.update(pid=owner.pid, created_at=owner.create_time())
        else:
            if ticket.get("pid") != owner.pid or ticket.get("created_at") != owner.create_time():
                raise ValueError("Runtime lease owner changed")
            if operation == "bind-profile":
                if not Path(request["profile"]).is_absolute():
                    raise ValueError("Invalid session profile")
                ticket["selected_profile"] = request["profile"]
            else:
                ticket["retired"] = True
        write(file, ticket)
        return selected
    if operation == "collect":
        held = []
        try:
            return collect(root, request, held)
        finally:
            for fd in held:
                os.close(fd)
    raise ValueError("Unknown runtime transaction")


def collect(root, request, held):
    import psutil
    def lease_live(ticket):
        if ticket.get("retired"):
            return False
        if not ticket.get("pid"):
            return ticket.get("expires_at", float("inf")) >= time.time()
        try:
            owner = psutil.Process(ticket["pid"])
            return owner.create_time() == ticket.get("created_at") and owner.status() != psutil.STATUS_ZOMBIE
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            return False
        except psutil.AccessDenied:
            return True
    pointer = current(root)
    keep = {pointer["id"], pointer.get("previous")}
    tickets = []
    for file in (root / "admissions").glob("*.json"):
        ticket = read(file)
        if not HASH.fullmatch(ticket.get("id", "")):
            raise ValueError("Uncertain admission evidence")
        tickets.append((file, ticket))
    for file in (root / "handoffs").glob("*.json"):
        receipt = read(file)
        helper_live = False
        if receipt.get("helper_pid"):
            try:
                helper = psutil.Process(receipt["helper_pid"])
                helper_live = helper.create_time() == receipt.get("helper_created_at") and helper.status() != psutil.STATUS_ZOMBIE
            except (psutil.NoSuchProcess, psutil.ZombieProcess):
                pass
            except psutil.AccessDenied:
                helper_live = True
        if helper_live or (not receipt.get("helper_pid") and receipt.get("expires_at", float("inf")) >= time.time()):
            keep.add(receipt["id"])
        else:
            private(root / "outcomes")
            os.replace(file, root / "outcomes" / file.name)
    pins = list((root / "maintenance").glob("*.json")) + list((root / "preparations").glob("*.json"))
    # A user may pin a physical application's Dock tile. Keep that entry
    # executable; opening it routes to current rather than resurrecting it.
    import plistlib
    try:
        dock = plistlib.loads(subprocess.run(["/usr/bin/defaults", "export", "com.apple.dock", "-"], check=True, capture_output=True, timeout=10).stdout)
        dock_text = json.dumps(dock.get("persistent-apps", []), default=str)
        for directory in (root / "generations").iterdir():
            if directory.name in dock_text:
                keep.add(directory.name)
    except Exception:
        return dict(removed=[], retained="Dock references could not be inspected")
    # Any inspection failure conservatively retains all generations. Check
    # executables and mappings, including helpers whose GUI has disappeared.
    snapshot = subprocess.run(["/bin/ps", "-axww", "-o", "pid=,command="], check=True, capture_output=True, text=True, timeout=10)
    rows = snapshot.stdout.strip().splitlines()
    if not rows or any(not re.match(r"\s*\d+\s+\S", row) for row in rows):
        return dict(removed=[], retained="Process inspection unavailable")
    paths = [re.sub(r"^\s*\d+\s+", "", row) for row in rows]
    for directory in (root / "front-doors").glob("launch-*"):
        if directory.resolve() != directory or not directory.is_dir():
            continue
        try:
            owner = read(directory / "owner.json")
            if owner.get("format") != "disco-front-door-profile" or type(owner.get("pid")) is not int or owner["pid"] <= 0:
                continue
            try:
                os.kill(owner["pid"], 0)
                continue
            except ProcessLookupError:
                pass
            except PermissionError:
                continue
            if not any(str(directory) in value for value in paths):
                shutil.rmtree(directory)
        except (OSError, ValueError):
            continue
    for staging in root.glob("staging-*"):
        if staging.resolve() != staging or not staging.is_dir():
            continue
        try:
            owner = read(staging / "stage-owner.json")
            if owner.get("format") != "disco-runtime-staging" or type(owner.get("pid")) is not int or owner["pid"] <= 0:
                continue
            try:
                os.kill(owner["pid"], 0)
                continue
            except ProcessLookupError:
                pass
            except PermissionError:
                continue
            if not any(str(staging) in value for value in paths):
                shutil.rmtree(staging)
        except (OSError, ValueError):
            # Never sweep unknown contents as an inferred abandoned copy.
            continue
    for file in pins:
        pin = read(file)
        try:
            os.kill(pin["pid"], 0)
            keep.add(pin["id"])
        except ProcessLookupError:
            # A reused PID conservatively retains the pin. Detached copy
            # commands are separately caught by the command-path snapshot.
            file.unlink()
        except PermissionError:
            keep.add(pin["id"])
    for file, ticket in tickets:
        if ticket.get("retired"):
            continue
        live = lease_live(ticket)
        bundle = generation(root, ticket["id"])["bundle"]
        if live or any(bundle in value for value in paths):
            keep.add(ticket["id"])
        else:
            same_profile = ticket.get("selected_profile")
            if same_profile and any(other is not ticket and same_profile in (other.get("profile"), other.get("selected_profile")) and lease_live(other) for _, other in tickets):
                keep.add(ticket["id"])
                continue
            try:
                independent_absence = hold_profile_witnesses(ticket, held, request.get("runtime_application"))
            except Exception:
                independent_absence = False
            if not independent_absence:
                keep.add(ticket["id"])
                continue
            # Stop admitting the expired reservation before considering its
            # bytes. The framework check below independently guards mappings.
            ticket["retired"] = True
            ticket["retirement_reason"] = "Exact session process exited; no generation executables remain"
            write(file, ticket)
    removed = []
    for directory in (root / "generations").iterdir():
        identifier = directory.name
        if not HASH.fullmatch(identifier) or identifier in keep:
            continue
        selected = generation(root, identifier)
        if any(selected["bundle"] in value for value in paths):
            continue
        framework = Path(selected["bundle"]) / "Contents/Frameworks/Electron Framework.framework/Versions/A/Electron Framework"
        if not framework.is_file():
            continue
        opened = subprocess.run(["/usr/sbin/lsof", "-t", str(framework)], capture_output=True, text=True, timeout=10)
        if opened.returncode != 1 or opened.stdout.strip() or opened.stderr.strip():
            continue
        # No new admission or activation can race this removal under flock.
        shutil.rmtree(directory)
        for file, ticket in tickets:
            if ticket["id"] == identifier:
                file.unlink()
        removed.append(identifier)
    return dict(removed=removed)


def main():
    request = json.load(sys.stdin)
    root = Path(request.pop("root"))
    private(root)
    fd = os.open(root / "transaction.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        print(json.dumps(execute(root, request)))
    finally:
        os.close(fd)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps(dict(error=str(error))))
        sys.exit(1)
