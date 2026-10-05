"""Minimal response-only inverse facts. No undo journal is persisted."""
import json
MAX_UNDO_TARGETS = 1000
MAX_UNDO_BYTES = 512 * 1024


def bounded_inverse(value):
    size=len(json.dumps(value,ensure_ascii=False).encode('utf-16-le'))*2+len(value.get('targets',[]))*128+len(value.get('patterns',[]))*256+256
    if len(value.get('targets',[]))>MAX_UNDO_TARGETS or size>MAX_UNDO_BYTES:
        return {'kind':'unavailable','reason':'This gesture exceeds session undo memory limits.'}
    return value


def _pattern(changes, patterns, indexes):
    # Repeated tag text and inclusion values occur once per gesture, even for
    # 1000 targets. Each target stores only UUID, revisions and pattern index.
    key=tuple((field,tuple(value) if isinstance(value,list) else value) for field,value in sorted(changes.items()))
    if key not in indexes:indexes[key]=len(patterns);patterns.append(changes)
    return indexes[key]


def annotation_inverse(before, after):
    if len(after)>MAX_UNDO_TARGETS:
        return {'kind':'unavailable','reason':'This gesture is too large for session undo.'}
    targets=[];patterns=[];indexes={}
    for old,new in zip(before,after):
        prior,current=set(old['tags']),set(new['tags'])
        changes={'tags_add':sorted(prior-current),'tags_remove':sorted(current-prior)}
        pattern=_pattern(changes,patterns,indexes)
        targets.append([new['target_uuid'],new['revision'],old['revision'],pattern])
    first=after[0] if after else {}
    return bounded_inverse({'kind':'annotations','target_kind':first.get('target_kind'),
        'profile_uuid':first.get('profile_uuid'),'patterns':patterns,'targets':targets})


def curation_inverse(protocol_uuid, before, after, changes, inclusion_by_epoch=None):
    if len(after)>MAX_UNDO_TARGETS:
        return {'kind':'unavailable','reason':'This gesture is too large for session undo.'}
    targets=[];patterns=[];indexes={}
    for key,new in after.items():
        old=before[key];inverse={}
        if ('included' in changes or inclusion_by_epoch is not None) and old['included']!=new['included']:
            inverse['included']=old['included']
        if 'tags_add' in changes or 'tags_remove' in changes:
            added=sorted(set(old['tags'])-set(new['tags']))
            removed=sorted(set(new['tags'])-set(old['tags']))
            if added:inverse['tags_add']=added
            if removed:inverse['tags_remove']=removed
        if inverse:
            pattern=_pattern(inverse,patterns,indexes)
            targets.append([key,new['revision'],old['revision'],pattern])
    return bounded_inverse({'kind':'curation','protocol_uuid':protocol_uuid,'patterns':patterns,'targets':targets})
