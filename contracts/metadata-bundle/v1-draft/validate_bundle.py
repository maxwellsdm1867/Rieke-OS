#!/usr/bin/env python3
"""Offline DRAFT adapter validator. No database, network or trace/path access.
Implements only the JSON Schema vocabulary used by the accompanying schema,
then checks DISCO identity and relationship semantics. Not a production importer.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import pathlib
import re
import sys
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

VERSION = '1.0.0-draft.1'
MAX_BYTES = 16 * 1024 * 1024
MAX_ERRORS = 1000
FIELD = re.compile(r'^[a-z][a-z0-9_.-]*:[a-zA-Z0-9_.-]+$')
RFC3339 = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$')
VOCABULARY = {'$schema','$id','$defs','$ref','title','description','type','enum','const','properties','required','additionalProperties','propertyNames','items','minItems','maxItems','maxProperties','minLength','maxLength','minimum','maximum','exclusiveMinimum','pattern','format','oneOf','anyOf'}

class InvalidInput(ValueError): pass

def loads(raw):
    if len(raw) > MAX_BYTES: raise InvalidInput('input exceeds 16 MiB')
    text = raw.decode('utf-8', errors='strict')
    depth = 0; in_string = False; escaped = False
    for ch in text:
        if in_string:
            if escaped: escaped = False
            elif ch == '\\': escaped = True
            elif ch == '"': in_string = False
        elif ch == '"': in_string = True
        elif ch in '[{':
            depth += 1
            if depth > 32: raise InvalidInput('JSON nesting exceeds 32')
        elif ch in ']}': depth -= 1
    def pairs(values):
        result = {}
        for key,value in values:
            if key in result: raise InvalidInput('duplicate JSON object key')
            result[key] = value
        return result
    def constant(_): raise InvalidInput('NaN/Infinity are forbidden')
    def number(value):
        value = float(value)
        if not math.isfinite(value): raise InvalidInput('nonfinite JSON number')
        return value
    data = json.loads(text, object_pairs_hook=pairs, parse_constant=constant, parse_float=number)
    pending = [data]; nodes = 0
    while pending:
        value = pending.pop(); nodes += 1
        if nodes > 1000000: raise InvalidInput('JSON exceeds one million nodes')
        if isinstance(value,str) and any(0xd800 <= ord(c) <= 0xdfff for c in value): raise InvalidInput('lone Unicode surrogate is forbidden')
        if isinstance(value,dict): pending.extend(value.keys()); pending.extend(value.values())
        if isinstance(value,list): pending.extend(value)
    return data

def instant(value):
    if not isinstance(value,str) or not RFC3339.fullmatch(value): raise ValueError('offset-aware RFC3339 required')
    parsed = dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.utcoffset() is None: raise ValueError('offset missing')
    return parsed

def json_equal(a,b):
    if isinstance(a,bool) or isinstance(b,bool): return type(a) is type(b) and a == b
    return a == b

def kind(value, name):
    return {'object':isinstance(value,dict),'array':isinstance(value,list),'string':isinstance(value,str),'number':type(value) in (int,float),'integer':type(value) is int or (type(value) is float and value.is_integer()),'boolean':type(value) is bool,'null':value is None}.get(name,False)

def check_schema(value, rule, root, path='$'):
    unknown = set(rule) - VOCABULARY
    if unknown: raise InvalidInput('validator does not implement schema keyword '+','.join(sorted(unknown)))
    errors = []
    def error(message):
        if len(errors)<MAX_ERRORS: errors.append({'code':'schema','path':path,'message':message})
    if '$ref' in rule:
        pointer=rule['$ref']
        if not pointer.startswith('#/$defs/'): raise InvalidInput('external schema references are forbidden')
        return check_schema(value,root['$defs'][pointer.split('/')[-1]],root,path)
    for keyword in ('oneOf','anyOf'):
        if keyword in rule:
            matched=sum(not check_schema(value,r,root,path) for r in rule[keyword])
            if (keyword=='oneOf' and matched!=1) or (keyword=='anyOf' and matched<1): error('value does not match '+keyword+' alternatives')
    expected=rule.get('type')
    if expected and not any(kind(value,n) for n in ([expected] if isinstance(expected,str) else expected)):
        error('wrong JSON type');return errors
    if 'const' in rule and not json_equal(value,rule['const']): error('incorrect constant')
    if 'enum' in rule and not any(json_equal(value,x) for x in rule['enum']): error('unsupported enum value')
    if isinstance(value,str):
        if len(value)<rule.get('minLength',0) or len(value)>rule.get('maxLength',sys.maxsize):error('string length outside limits')
        if 'pattern' in rule and not re.search(rule['pattern'],value):error('string does not match required pattern')
        try:
            if rule.get('format')=='date-time':instant(value)
            if rule.get('format')=='uuid':
                if str(uuid.UUID(value))!=value:raise ValueError('UUID must be canonical lowercase')
        except (ValueError,OverflowError):error('invalid '+rule['format'])
    if type(value) in (int,float):
        if not math.isfinite(value):error('nonfinite number')
        if value<rule.get('minimum',-math.inf) or value>rule.get('maximum',math.inf):error('number outside limits')
        if 'exclusiveMinimum' in rule and value<=rule['exclusiveMinimum']:error('number must exceed lower bound')
    if isinstance(value,list):
        if len(value)<rule.get('minItems',0) or len(value)>rule.get('maxItems',sys.maxsize):error('array length outside limits')
        if 'items' in rule:
            for i,item in enumerate(value):
                errors.extend(check_schema(item,rule['items'],root,f'{path}/{i}'))
                if len(errors)>=MAX_ERRORS:break
    if isinstance(value,dict):
        if len(value)>rule.get('maxProperties',sys.maxsize):error('too many object properties')
        for key in rule.get('required',[]):
            if key not in value:error('missing required property: '+key)
        props=rule.get('properties',{})
        for key,item in value.items():
            if 'propertyNames' in rule:errors.extend(check_schema(key,rule['propertyNames'],root,path+'/'+key))
            if key in props:errors.extend(check_schema(item,props[key],root,path+'/'+key))
            elif rule.get('additionalProperties') is False:error('unknown property: '+key)
            elif isinstance(rule.get('additionalProperties'),dict):errors.extend(check_schema(item,rule['additionalProperties'],root,path+'/'+key))
            if len(errors)>=MAX_ERRORS:break
    return errors[:MAX_ERRORS]

def validate(data,schema):
    errors=[]; warnings=[]
    def err(code,path,message):
        if len(errors)<MAX_ERRORS:errors.append(dict(code=code,path=path,message=message))
    if isinstance(data,dict) and data.get('schema_version')!=VERSION:err('version','$/schema_version','unsupported draft version')
    errors.extend(check_schema(data,schema,schema))
    if errors:return report(data,errors[:MAX_ERRORS],warnings)
    by_kind={k:{x['id']:x for x in data.get(k,[])} for k in ('sources','protocols','ancestry','cells','epochs','streams')}
    all_ids={}; assets={}; namespace=uuid.UUID(data['authority']['namespace_uuid'])
    entities=[('dataset',data['dataset'],'$/dataset')]
    for plural,singular in [('sources','source'),('protocols','protocol'),('ancestry','ancestor'),('cells','cell'),('epochs','epoch'),('streams','stream')]:
        for i,item in enumerate(data.get(plural,[])):
            entities.append((item.get('kind') if singular=='ancestor' else singular,item,f'$/{plural}/{i}'))
            if plural=='sources':
                for j,a in enumerate(item.get('raw_assets',[])):
                    entities.append(('raw_asset',a,f'$/{plural}/{i}/raw_assets/{j}'));assets[a['id']]=(item['id'],a)
    for entity_kind,item,path in entities:
        uid=item['id']; identity=item['identity']
        if uid in all_ids:err('duplicate_id',path+'/id','ID already used at '+all_ids[uid])
        all_ids[uid]=path
        if identity['mode']=='native_uuid':expected=identity['native_key']
        else:expected=str(uuid.uuid5(namespace,json.dumps(['disco-id-v1',entity_kind,identity['native_key']],ensure_ascii=False,separators=(',',':'))))
        if uid!=expected:err('identity',path+'/identity','ID differs from recorded native UUID or specified UUIDv5 mapping')
    def link(target,uid,path):
        item=by_kind[target].get(uid)
        if item is None:err('broken_link',path,'unresolved '+target+' ID')
        return item
    definitions={}
    for i,f in enumerate(data['field_definitions']):
        if f['id'] in definitions:err('duplicate_field',f'$/field_definitions/{i}','field definition repeated')
        definitions[f['id']]=f
        if not FIELD.fullmatch(f['id']):err('field_name',f'$/field_definitions/{i}/id','field ID must be namespaced')
        unit=f['unit']
        if unit is not None and (not unit or unit!=unit.strip() or any(ord(c)<32 for c in unit)):err('unit',f'$/field_definitions/{i}/unit','unit is a printable label or null; never an empty sentinel')
        if f['type']!='array' and 'item_type' in f:err('field_type',f'$/field_definitions/{i}/item_type','item_type only belongs to an array field')
    def typed(value,typ):
        if typ in ('number','integer','string','boolean','array','object'):return value is not None and kind(value,typ) and (typ!='integer' or abs(value)<=9007199254740991)
        if typ=='integer_string':return isinstance(value,str) and bool(re.fullmatch(r'-?(0|[1-9][0-9]*)',value))
        if typ=='decimal':return isinstance(value,str) and bool(re.fullmatch(r'-?(0|[1-9][0-9]*)(\.[0-9]+)?',value))
        return False
    def fields(item,scope,path):
        for key,v in item.get('fields',{}).items():
            definition=definitions.get(key);p=path+'/fields/'+key
            if definition is None:err('unknown_field',p,'field has no definition');continue
            if definition['scope']!=scope:err('field_scope',p,'field definition scope differs from entity scope')
            if v['status']=='present':
                if not typed(v['value'],definition['type']):err('field_type',p,'value differs from declared type; present null is forbidden')
                elif definition['type']=='array' and 'item_type' in definition and any(not typed(x,definition['item_type']) for x in v['value']):err('field_type',p,'array item differs from declared item type')
    for entity_kind,item,path in entities:
        if entity_kind not in ('dataset','raw_asset','stream'):fields(item,'ancestry' if entity_kind in ('animal','preparation','group','block') else entity_kind,path)
        for field in ('start_time','end_time'):
            time=item.get(field)
            if time and time['status']=='known' and time.get('timezone'):
                try:
                    t=instant(time['instant']); zone=ZoneInfo(time['timezone'])
                    if t.astimezone(zone).utcoffset()!=t.utcoffset():err('timezone',path+'/'+field,'IANA zone and explicit offset disagree')
                except ZoneInfoNotFoundError:err('timezone',path+'/'+field,'unknown IANA timezone')
        if entity_kind in ('cell','epoch','animal','preparation','group','block'):
            link('sources',item['source_id'],path+'/source_id')
        if entity_kind=='cell' and item.get('preparation_id'):
            p=link('ancestry',item['preparation_id'],path+'/preparation_id')
            if p and (p['kind']!='preparation' or p['source_id']!=item['source_id']):err('ownership',path,'cell preparation kind/source differs')
        if entity_kind in ('animal','preparation','group','block'):
            if entity_kind=='animal' and 'parent_id' in item:err('ancestry',path,'animal parent is implicit source; do not invent another parent')
            if entity_kind!='animal':
                if 'parent_id' not in item:err('broken_link',path+'/parent_id','recorded ancestor needs its actual parent')
                else:
                    expected_kind={'preparation':'animal','group':'cell','block':'group'}[entity_kind]
                    p=link('cells' if expected_kind=='cell' else 'ancestry',item['parent_id'],path+'/parent_id')
                    if p and (p.get('kind','cell')!=expected_kind or p['source_id']!=item['source_id']):err('ownership',path,'ancestor parent kind/source differs')
            if item.get('protocol_id'):link('protocols',item['protocol_id'],path+'/protocol_id')
        if entity_kind=='epoch':
            c=link('cells',item['cell_id'],path+'/cell_id');link('protocols',item['protocol_id'],path+'/protocol_id')
            if c and c['source_id']!=item['source_id']:err('ownership',path,'epoch and cell source differ')
            g=None;b=None
            for f,expected_kind in [('group_id','group'),('block_id','block')]:
                if f in item:
                    ancestor=link('ancestry',item[f],path+'/'+f)
                    if ancestor and (ancestor['kind']!=expected_kind or ancestor['source_id']!=item['source_id']):err('ownership',path+'/'+f,'epoch ancestry kind/source differs')
                    if f=='group_id':g=ancestor
                    else:b=ancestor
            if b:
                bg=by_kind['ancestry'].get(b.get('parent_id'))
                if not bg or bg.get('parent_id')!=item['cell_id'] or (g and bg['id']!=g['id']):err('ownership',path,'block/group chain differs from epoch cell/group')
                if b.get('protocol_id') and b['protocol_id']!=item['protocol_id']:err('ownership',path,'epoch and block protocol differ')
            if g and g.get('parent_id')!=item['cell_id']:err('ownership',path,'group differs from epoch cell')
            if all(item.get(f,{}).get('status')=='known' for f in ('start_time','end_time')):
                duration=(instant(item['end_time']['instant'])-instant(item['start_time']['instant'])).total_seconds()
                if duration<0:err('time',path,'end precedes start')
                if 'duration_seconds' in item and abs(duration-item['duration_seconds'])>0.000001:err('time',path,'recorded duration disagrees with known start/end')
        if entity_kind=='raw_asset':
            locator=item['locator']
            if locator['kind']=='managed_asset' and locator['asset_key']!=item['sha256']:err('asset',path,'managed asset key and byte checksum differ')
            hint=locator.get('relative_path',locator.get('absolute_path_hint'))
            if hint and any(p in ('.','..','') for p in hint.strip('/').split('/')):err('path',path+'/locator','path is not canonical; no traversal/empty segments')
        if entity_kind=='stream':
            e=link('epochs',item['epoch_id'],path+'/epoch_id')
            if item['trace_state']=='referenced':
                a=assets.get(item['data_reference']['asset_id'])
                if a is None:err('broken_link',path+'/data_reference','unknown raw asset ID')
                elif e and a[0]!=e['source_id']:err('ownership',path,'stream raw asset belongs to another source')
                if any(p in ('.','..','') for p in item['data_reference']['object_path'].strip('/').split('/')):err('path',path+'/data_reference','object path is not canonical')
            if item['trace_state']=='generator_only':fields({'fields':item['generator'].get('parameters',{})},'epoch',path+'/generator')
            if item.get('unit') is not None and (not item['unit'] or item['unit']!=item['unit'].strip() or any(ord(c)<32 for c in item['unit'])):err('unit',path+'/unit','stream unit must be explicit printable text or null')
    annotation=data.get('annotations',{});profiles={};seen=set()
    for i,p in enumerate(annotation.get('profiles',[])):
        if p['profile_uuid'] in profiles:err('duplicate_profile',f'$/annotations/profiles/{i}','profile UUID repeated')
        profiles[p['profile_uuid']]=p['author_name']
        if p['author_name']!=p['author_name'].strip() or any(ord(c)<32 for c in p['author_name']):err('author',f'$/annotations/profiles/{i}','author name must be trimmed and printable')
    for i,a in enumerate(annotation.get('entries',[])):
        path=f'$/annotations/entries/{i}';key=(a['target_kind'],a['target_id'],a['profile_uuid'])
        if key in seen:err('duplicate_annotation',path,'author-target entry repeated')
        seen.add(key);link('cells' if a['target_kind']=='cell' else 'epochs',a['target_id'],path+'/target_id')
        if a['profile_uuid'] not in profiles:err('broken_link',path+'/profile_uuid','unknown profile')
        if len(set(a['tags']))!=len(a['tags']):err('duplicate_tag',path,'exact tag repeated')
        for tag in a['tags']:
            if tag!=tag.strip() or any(ord(c)<32 for c in tag):err('tag',path,'tag must be trimmed and printable')
    if assets:warnings.append({'code':'unverified_raw_claims','message':'Raw checksums/locators are producer claims. This validator opens no assets and enables no traces or QC.'})
    warnings.append({'code':'draft_only','message':'Current DISCO H5 importer does not accept this draft bundle.'})
    return report(data,errors,warnings)

def report(data,errors,warnings):
    return {'valid':not errors,'contract_version':VERSION,'draft_only':True,'database_checked':False,'raw_assets_verified':0,'counts':{k:len(data.get(k,[])) for k in ('sources','protocols','cells','epochs','streams')} if isinstance(data,dict) else {},'errors':errors,'warnings':warnings}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('bundle',type=pathlib.Path);parser.add_argument('--schema',type=pathlib.Path,default=pathlib.Path(__file__).with_name('disco-metadata-bundle.schema.json'));args=parser.parse_args()
    try:
        # Input bundle and schema are explicit user-selected local files. No paths
        # found inside the bundle are ever read, resolved, opened or fetched.
        with args.bundle.open('rb') as h:raw=h.read(MAX_BYTES+1)
        data=loads(raw);schema=loads(args.schema.read_bytes());result=validate(data,schema)
        result['input_sha256']=hashlib.sha256(raw).hexdigest()
    except (OSError,ValueError,TypeError,KeyError,RecursionError,OverflowError) as e:
        result=report(None,[{'code':'input','path':'$','message':str(e)}],[])
    print(json.dumps(result,indent=2,ensure_ascii=True));return 0 if result['valid'] else 1
if __name__=='__main__':sys.exit(main())
