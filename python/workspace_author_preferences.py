"""The selected tag author is a preference of this local OS user, across projects."""
import fcntl
import json
import os
from pathlib import Path
import uuid
from recording_workspace import write_json


def preference_path():
    return Path(os.environ.get('RIEKE_PREFERENCES_DIR', Path.home() / '.rieke-os')).expanduser() / 'annotation-author.json'


def validate_profile(profile):
    if not isinstance(profile, dict):
        raise ValueError('Choose a valid tag author')
    identity = str(uuid.UUID(profile.get('profile_uuid', '')))
    name = profile.get('display_name')
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120 or any(ord(char) < 32 for char in name):
        raise ValueError('Tag author names require 1–120 printable characters')
    return {'profile_uuid': identity, 'display_name': name.strip()}


def author_preferences():
    path = preference_path()
    if path.is_symlink():
        raise ValueError('Tag author preference cannot be a symbolic link')
    if not path.exists():
        return {'profiles': [], 'selected': None}
    if path.stat().st_size > 131072:
        raise ValueError('Tag author preference is unexpectedly large')
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or value.get('format') != 'rieke-tag-author' or type(value.get('version')) is not int or value['version'] != 1:
        raise ValueError('Tag author preference is invalid')
    selected = validate_profile(value.get('profile'))
    profiles = value.get('profiles', [selected])
    if not isinstance(profiles, list) or len(profiles) > 100:
        raise ValueError('Use at most 100 master author profiles')
    profiles = [validate_profile(profile) for profile in profiles]
    if len({profile['profile_uuid'] for profile in profiles}) != len(profiles) or selected not in profiles:
        raise ValueError('Master author profile identities are inconsistent')
    return {'profiles': profiles, 'selected': selected}


def selected_author():
    return author_preferences()['selected']


def author_profiles():
    return author_preferences()['profiles']


def remember_author(profile):
    profile = validate_profile(profile)
    path = preference_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix('.lock')
    if path.is_symlink() or lock_path.is_symlink():
        raise ValueError('Tag author preference cannot be a symbolic link')
    with lock_path.open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        profiles = author_profiles()
        existing = next((saved for saved in profiles if saved['profile_uuid'] == profile['profile_uuid']), None)
        if existing and existing != profile:
            raise ValueError('This author identity already has another name')
        if not existing:
            if len(profiles) >= 100:
                raise ValueError('Use at most 100 master author profiles')
            profiles.append(profile)
        write_json(path, {'format': 'rieke-tag-author', 'version': 1, 'profile': profile, 'profiles': profiles})
    return profile
