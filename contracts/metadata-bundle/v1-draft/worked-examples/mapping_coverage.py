"""Occurrence-level teaching-mapper coverage; no receiver query claims."""
from validate_bundle import pointer


def leaf_tokens(value,tokens=()):
    if isinstance(value,dict) and value:
        for key,child in value.items():yield from leaf_tokens(child,tokens+(key,))
    elif isinstance(value,list) and value:
        for index,child in enumerate(value):yield from leaf_tokens(child,tokens+(index,))
    else:yield tokens,value


def observed_type(value):
    return ('null' if value is None else 'boolean' if type(value) is bool else
            'integer' if type(value) is int else 'number' if type(value) is float else
            'string' if isinstance(value,str) else 'array' if isinstance(value,list) else 'object')


def inventory(source,bundle, *, raw_claim=False):
    records={}
    for tokens,value in leaf_tokens(source):
        records[tokens]={
            'source_path':'$'+pointer(tokens),'source_pointer':pointer(tokens),
            'observed_type':observed_type(value),'observed_shape':[] if not isinstance(value,(list,dict)) else {'length':len(value)},
            'unit':None,'unit_evidence':'not_applicable_or_not_declared',
            'missingness':'explicit_null_uninterpreted' if value is None else 'present',
            'retention_pointer':pointer(('extensions','demo:source_snapshot')+tokens),
            'target_pointers':[],'transformations':[],
            'query_support':'retained_only','query_execution':'unsupported_receiver',
            'test_status':'not_run','test_case':'WorkedExamples.test_typed_coverage',
        }
    def mark(src,target,transform='copy'):
        # mark is called with original token tuples; slash/tilde never parsed.
        row=records.get(src)
        if row is not None:
            dest=pointer(target)
            if dest not in row['target_pointers']:row['target_pointers'].append(dest)
            if transform not in row['transformations']:row['transformations'].append(transform)
            row['query_support']='mapped'
    def subtree(value,src,target,transform='copy'):
        for suffix,_ in leaf_tokens(value):mark(src+suffix,target+suffix,transform)
    mark(('authority_namespace_uuid',),('authority','namespace_uuid'),'canonical_uuid')
    mark(('dataset_key',),('dataset','id'),'uuid5_exact_tuple_utf8')
    mark(('revision',),('dataset','revision'));mark(('revision',),('sources',0,'metadata_revision'))
    mark(('experiment','key'),('sources',0,'id'),'uuid5_exact_tuple_utf8')
    mark(('experiment','label'),('sources',0,'label'))
    mark(('experiment','start_time'),('sources',0,'start_time','original'),'unknown_time_original_only')
    subtree(source['reviewer'],('reviewer',),('annotations','profiles',0))
    for index,(name,definition) in enumerate(source['parameter_definitions'].items()):
        for field in ('id','type','unit'):
            mark(('parameter_definitions',name,field),('field_definitions',index,field))
    def identity(obj,src,target):
        if not obj.get('uuid'):mark(src+('key',),target+('id',),'uuid5_scoped_key_tuple_utf8')
        if obj.get('uuid'):mark(src+('uuid',),target+('id',),'native_uuid_preserved')
    def tags(obj,src,kind,uid):
        for index,annotation in enumerate(bundle['annotations']['entries']):
            if annotation['target_kind']==kind and annotation['target_id']==uid:
                subtree(obj['tags'],src+('tags',),('annotations','entries',index,'tags'))
    def parameter_metadata(params,src):
        for name,value in params.items():
            definition=source['parameter_definitions'].get(name)
            for suffix,_ in leaf_tokens(value):
                row=records[src+(name,)+suffix]
                if definition:
                    row['unit']=definition['unit'];row['unit_evidence']='explicit_source_parameter_definition'
                    if value is None:row['missingness']=definition.get('null_status','explicit_null_uninterpreted')
    ai=0;ei=0;si=0;protocols={p['name']:i for i,p in enumerate(bundle['protocols'])}
    for ci,cell in enumerate(source['experiment']['cells']):
        cp=('experiment','cells',ci);identity(cell,cp,('cells',ci))
        mark(cp+('label',),('cells',ci,'label'));tags(cell,cp,'cell',bundle['cells'][ci]['id'])
        for gi,group in enumerate(cell['epochGroups']):
            gp=cp+('epochGroups',gi);identity(group,gp,('ancestry',ai));ai+=1
            for bi,block in enumerate(group['epochBlocks']):
                bp=gp+('epochBlocks',bi);identity(block,bp,('ancestry',ai));ai+=1
                mark(bp+('protocolID',),('protocols',protocols[block['protocolID']],'name'))
                parameter_metadata(block['parameters'],bp+('parameters',))
                for local_ei,epoch in enumerate(block['epochs']):
                    ep=bp+('epochs',local_ei);identity(epoch,ep,('epochs',ei));tags(epoch,ep,'epoch',bundle['epochs'][ei]['id'])
                    parameter_metadata(epoch['parameters'],ep+('parameters',))
                    for name,value in {**block['parameters'],**epoch['parameters']}.items():
                        definition=source['parameter_definitions'].get(name)
                        if not definition:continue
                        origin=ep if name in epoch['parameters'] else bp
                        src=origin+('parameters',name);target=('epochs',ei,'fields',definition['id'])
                        if value is None:
                            if 'null_status' in definition:
                                mark(src,target+('status',),'explicit_source_null_policy')
                                mark(('parameter_definitions',name,'null_status'),target+('status',),'explicit_source_null_policy')
                        else:subtree(value,src,target+('value',),'epoch_override' if origin==ep else 'inherited_block_default')
                    for device,response in epoch['responses'].items():
                        rp=ep+('responses',device)
                        for source_name,target_name in [('sampleRate','sample_rate_hz'),('sampleCount','sample_count'),('units','unit')]:mark(rp+(source_name,),('streams',si,target_name))
                        mark(rp+('sampleRateUnits',),('streams',si,'sample_rate_hz'),'assert_Hz_no_conversion')
                        if raw_claim:mark(rp+('h5path',),('streams',si,'data_reference','object_path'),'unverified_locator_claim')
                        si+=1
                    ei+=1
    for row in records.values():
        row['target_pointers'].sort();row['transformations'].sort()
        if not row['transformations']:row['transformations']=['snapshot_only']
    return [records[key] for key in sorted(records,key=pointer)]
