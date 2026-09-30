"""Prepare discardable tag indexes during project/import preparation.

Canonical SQL records are never rewritten here. Cell annotations remain one
record per author and cell; the prepared index derives inheritance through the
source's exact epoch-to-cell links. Unsupported authority contracts retain the
ordinary canonical readers instead of declaring an unverified cache ready.
"""
from __future__ import annotations

import contextlib
import time

from workspace_annotations import SharedAnnotations
from workspace_shared_tag_index import SharedTagsChanged


def _ordered_rows(service):
    return sorted(service.rows.values(),key=lambda row:(row['date'],row['start_time'],row['epoch_uuid']))


def _links(rows):
    return tuple((row['epoch_uuid'],row['cell_uuid']) for row in rows)


def prepare_annotation_indexes(service,store,shared,*,protocol_state=None,progress=None):
    """Warm authoritative projections; caller owns the workspace database lock.

    This runs after a verified startup checkpoint or successful metadata import,
    before readiness is published. Failure discards derived work and reports the
    failed phase; callers may surface a preparation warning and retry safely.
    """
    started=time.perf_counter()
    report={'status':'preparing','phases':{},'project_uuid':service.project['project_uuid']}
    service.annotation_preparation=report
    shared_index=None;curation_index=None
    def phase(name,operation):
        report['phase']=name
        if progress:progress(name)
        before=time.perf_counter();result=operation()
        report['phases'][name]={'seconds':round(time.perf_counter()-before,6)}
        return result
    try:
        service._ready()
        metadata=getattr(service,'disk_index',None)
        if metadata is None or type(shared) is not SharedAnnotations:
            report.update(status='unavailable',reason='Verified source metadata and native shared annotations are required')
            return report
        metadata._check();generation=metadata.generation
        before=shared.generation_token()
        if before is None:
            report.update(status='unavailable',reason='Native annotation generation authority is unavailable')
            return report
        rows=_ordered_rows(service);links=_links(rows)
        report.update(epochs=len(rows),cells=len(service.cells),metadata_generation=generation)
        shared_index=phase('indexing_shared_annotations',lambda:shared._membership_index(rows))
        if shared_index is None:
            report.update(status='unavailable',reason='Native annotation generation authority could not be verified')
            return report
        phase('preparing_tag_filters',lambda:shared_index.matching(rows,{}))
        phase('preparing_tag_summary',lambda:shared_index.summary(rows))
        phase('preparing_tag_suggestions',lambda:shared_index.suggestions('',30))
        report['shared_index']=dict(shared_index.stats)

        recovery=getattr(service,'_recovery_tracker',None)
        if recovery is not None and recovery.ready:
            store.recovery_tracker=recovery
            phase('indexing_dataset_tags',lambda:store.tag_suggestions('',30))
            curation_index=getattr(store,'_curation_vocabulary_index',None)
            if curation_index is not None:report['dataset_index']=dict(curation_index.stats)
        if protocol_state is not None:
            from workspace_protocol_state import STATE_CACHE_SCOPES
            protocols=list(service.protocols)[:STATE_CACHE_SCOPES]
            def prepare_protocols():
                return sum(protocol_state.native_context(identity) is not None for identity in protocols)
            report['protocols_prepared']=phase('preparing_protocol_reads',prepare_protocols)
            report['protocols_deferred']=max(0,len(service.protocols)-len(protocols))

        metadata._check()
        if (service.disk_index is not metadata or metadata.generation!=generation
                or service.project['project_uuid']!=report['project_uuid'] or _links(_ordered_rows(service))!=links):
            raise ValueError('Source epoch/cell identities changed during annotation preparation')
        if shared.generation_token()!=before:
            raise SharedTagsChanged('Shared annotations changed during preparation; retry before using the prepared indexes')
        report.update(status='ready',phase='complete')
        return report
    except BaseException as error:
        for index in (shared_index,curation_index):
            if index is not None:
                with contextlib.suppress(Exception):index.close()
        report.update(status='failed',reason=str(error))
        raise
    finally:
        report['seconds']=round(time.perf_counter()-started,6)


def prepare_project_annotations(service,store,shared,*,protocol_state=None,reuse=False,progress=None):
    """Prepare the persistent SQL lookup at lifecycle boundaries, not each edit.

    No SQLite membership/vocabulary snapshot is opened for ordinary native tag
    filtering. A fresh canonical content proof permits unchanged reopen reuse.
    """
    from workspace_native_tag_lookup import bootstrap
    from workspace_recovery_store import verified_table_content
    from workspace_state_snapshot import save as save_app_state
    started=time.perf_counter()
    report={'status':'preparing','storage':'native_sql','phases':{},'project_uuid':service.project['project_uuid']}
    service.annotation_preparation=report
    try:
        service._ready()
        if type(shared) is not SharedAnnotations or getattr(service.dj.conn(),'_conn',None) is None:
            report.update(status='unavailable',reason='Native SQL annotations are required')
            return report
        before=shared.generation_token()
        if before is None:
            report.update(status='unavailable',reason='Native annotation authority is unavailable')
            return report
        def fresh_proof():
            tracker=getattr(service,'_recovery_tracker',None)
            proof=verified_table_content(service.project_dir,tracker,tables=('shared_annotation',)) if tracker else None
            if proof is None:
                save_app_state(service.project_dir,service.dj.conn(),service=service)
                tracker=getattr(service,'_recovery_tracker',None)
                proof=verified_table_content(service.project_dir,tracker,tables=('shared_annotation',)) if tracker else None
            if proof is None:raise ValueError('Fresh canonical annotation content proof is unavailable')
            return proof
        proof=fresh_proof()
        expected=[before]
        def locked_guard():
            shared.state_generation.assert_current_locked(expected[0])
            return True
        def proof_after_installation():
            # Lookup DDL intentionally changes authority. Capture a new exact
            # authority and content proof after installation, then compare that
            # same token under the source lock before publishing the marker.
            opening=shared.generation_token()
            if opening is None:raise SharedTagsChanged('Native authority is unavailable after lookup installation')
            current=fresh_proof()
            if shared.generation_token()!=opening:
                raise SharedTagsChanged('Annotations changed while preparing the lookup content proof')
            expected[0]=opening
            return current
        if progress:progress('preparing_native_tag_lookup')
        lookup=getattr(shared,'native_tag_lookup',None)
        same=lookup is not None and lookup.ready and getattr(lookup,'authority',None)==before.authority
        if same:
            lookup.checkpoint(proof,guard=locked_guard)
            report['reused']=True
        else:
            # If this session observed a schema change, never checkpoint the old
            # lookup blindly: missed source writes may have occurred in a gap.
            lookup=bootstrap(service.dj.conn(),service.project['project_uuid'],proof,force=lookup is not None,
                guard=locked_guard,proof_provider=proof_after_installation)
            if not lookup.ready:raise ValueError(lookup.reason)
            report['reused']=lookup.reused
        if protocol_state is not None:
            from workspace_protocol_state import STATE_CACHE_SCOPES
            metadata=getattr(service,'disk_index',None)
            metadata_generation=getattr(metadata,'generation',None)
            if metadata is not None:metadata._check()
            if progress:progress('preparing_protocol_reads')
            phase_started=time.perf_counter()
            protocols=list(service.protocols)[:STATE_CACHE_SCOPES]
            report['protocols_prepared']=sum(protocol_state.native_context(identity) is not None for identity in protocols)
            report['protocols_deferred']=max(0,len(service.protocols)-len(protocols))
            report['phases']['preparing_protocol_reads']={'seconds':round(time.perf_counter()-phase_started,6)}
            if metadata is not None:
                metadata._check()
                if service.disk_index is not metadata or metadata.generation!=metadata_generation:
                    raise ValueError('Source metadata changed during protocol preparation')
        after=shared.generation_token()
        lookup.validate_current()
        final=shared.generation_token()
        if after is None or final!=after or after!=expected[0]:
            raise SharedTagsChanged('Annotations changed during lookup preparation; retry')
        lookup.authority=after.authority
        shared.native_tag_lookup=lookup
        report.update(status='ready',phase='complete')
        return report
    except Exception as error:
        old=getattr(shared,'native_tag_lookup',None)
        if old is not None:old.ready=False
        report.update(status='failed',reason=str(error))
        return report
    finally:
        report['seconds']=round(time.perf_counter()-started,6)
