"""Discardable Overview aggregates prepared at explicit publication boundaries.

This module owns no SQL or membership authority. Callers fence the frozen source
publication and a complete recovery capture before publishing target deltas.
Read work follows the requested cell window; preparation is deliberately O(rows
+ protocol memberships + saved decisions). Canonical ordered duration folds are
never approximated by subtracting and adding membership deltas.
"""
from __future__ import annotations

from collections import Counter


class ProjectionUnavailable(ValueError):
    """Explicit preparation is required before an exact overview is available."""


def _counts():
    return {'epochs':0,'duration_seconds':0,'included':0,'approved':0,'approved_exportable':0,
            'exported':0,'shared_tagged_epochs':0,'shared_tagged_cells':0}


def _finish(value):
    result=dict(value)
    result.update(reviewed=result['approved'],unreviewed=result['epochs']-result['approved'],
                  excluded=result['epochs']-result['included'],exportable=result['included'])
    return result


class OverviewProjection:
    @classmethod
    def prepare(cls, *, rows, memberships, fingerprints, decisions, publication, watermark,
                exports=None, tagged_cells=(), tagged_epochs=()):
        self=cls()
        self.publication=publication;self.watermark=watermark;self.ready=True
        self.epochs={};self.memberships={};self.protocols={};self.cells={};self.protocol_cells={}
        self.protocol_order={protocol:position for position,protocol in enumerate(memberships)}
        self.cell_protocols={};self.rows=rows;self.exported_by_protocol={};self.attributes={};self.cell_attributes={}
        self.duration_versions={};self.duration_results={};self.duration_orders={};self.duration_serial=0;self.duration_failures={}
        self.retained_durations={}
        self.decisions={};self.total=_counts();self.tagged_cells=set(tagged_cells);self.tagged_epochs=set(tagged_epochs)
        self.direct_counts={};self.last_work={}
        exported=exports or {}
        for identity,row in rows.items():
            cell=row['cell_uuid'];duration=row['duration_seconds']
            self.epochs[identity]=(cell,fingerprints[identity],[],0)
            entry=self.cells.setdefault(cell,_counts());entry['epochs']+=1;entry['included']+=1;entry['duration_seconds']+=duration
            self.total['epochs']+=1;self.total['included']+=1;self.total['duration_seconds']+=duration
            if identity in exported:entry['exported']+=1;self.total['exported']+=1
        for protocol,identities in memberships.items():
            identities=tuple(identities)
            self.duration_orders[protocol]=identities;self.duration_versions[protocol]=0
            members=self.memberships[protocol]=set(identities)
            if len(members)!=len(identities):raise ValueError('Duplicate prepared membership')
            self.exported_by_protocol[protocol]={key for key,links in exported.items() if any(link['protocol_uuid']==protocol for link in links)}
            self.attributes[protocol]={field:Counter() for field in ('cell_type','group_label','source_sha256')}
            self.cell_attributes[protocol]={}
            count=self.protocols[protocol]=_counts();bins=self.protocol_cells[protocol]={}
            for identity in identities:
                if identity not in self.epochs:raise ValueError('Prepared membership contains an unknown epoch')
                cell,fp,owners,blocked=self.epochs[identity]
                owners.append(protocol);self.epochs[identity]=(cell,fp,owners,blocked+1)
                entry=bins.setdefault(cell,_counts());duration=rows[identity]['duration_seconds']
                self.cell_protocols.setdefault(cell,set()).add(protocol)
                self._metadata_delta(protocol,identity,1)
                for target in (count,entry):target['epochs']+=1;target['included']+=1;target['duration_seconds']+=duration
                if any(link['protocol_uuid']==protocol for link in exported.get(identity,())):
                    count['exported']+=1;entry['exported']+=1;self.exported_by_protocol[protocol].add(identity)
            count['cells']=len(bins)
            # Preserve the canonical retained-summary builtin sum separately:
            # Python 3.12+ may differ from the counts/cell ordered += folds.
            self.retained_durations[protocol]=sum(rows[key]['duration_seconds'] for key in identities)
        self.total['cells']=len(self.cells);self.total['protocols']=len(self.protocols)
        self.apply_decisions([(row['protocol_uuid'],row['epoch_uuid'],row) for row in decisions],watermark,watermark)
        # Effective shared tags are a union, not a count of author records.
        initial_cells=self.tagged_cells;initial_epochs=self.tagged_epochs
        self.tagged_cells=set();self.tagged_epochs=set()
        self.apply_tags([(kind,key,True) for kind,keys in (('epoch',initial_epochs),('cell',initial_cells)) for key in keys])
        self.last_work={'prepared_epochs':len(self.epochs),'prepared_memberships':sum(map(len,self.memberships.values()))}
        return self

    def protocols_for_epochs(self, identities):
        """Exact prepared owners for at most fifty displayed epochs, in protocol order.

        The caller supplies publication, recovery and binding fences. This reads
        existing reverse membership only; it never constructs a new member set.
        """
        self._check()
        if (type(identities) not in (list,tuple) or len(identities)>50
                or any(type(identity) is not str for identity in identities)
                or len(set(identities))!=len(identities)):
            raise ValueError('Epoch owner lookup requires at most fifty distinct identities')
        return {identity:tuple(sorted(self.epochs[identity][2],key=self.protocol_order.__getitem__))
                for identity in identities}

    def invalidate(self):
        self.ready=False

    def _check(self):
        if not self.ready:raise ProjectionUnavailable('Overview preparation is pending')

    def apply_decisions(self, changes, expected_watermark, next_watermark):
        self._check()
        if expected_watermark!=self.watermark:raise ProjectionUnavailable('Overview change feed no longer continues')
        # Validate/normalize the complete batch before touching any aggregate.
        updates={}
        for protocol,identity,row in changes:
            if protocol not in self.memberships or identity not in self.memberships[protocol]:continue
            if row is None:state=(True,False)
            else:
                if type(row['included']) not in (bool,int):raise ValueError('Invalid inclusion state')
                state=(bool(row['included']),row['review_state']=='approved' and row['metadata_fingerprint']==self.epochs[identity][1])
            updates[(protocol,identity)]=state
        touched=set()
        for (protocol,identity),(included,approved) in updates.items():
            before_included,before_approved=self.decisions.get((protocol,identity),(True,False))
            cell,fp,owners,blocked=self.epochs[identity]
            delta_included=int(included)-int(before_included);delta_approved=int(approved)-int(before_approved)
            for target in (self.protocols[protocol],self.protocol_cells[protocol][cell]):
                target['included']+=delta_included;target['approved']+=delta_approved
                target['approved_exportable']+=int(included and approved)-int(before_included and before_approved)
            before_project=blocked==0
            blocked-=delta_approved
            after_project=blocked==0
            delta=int(after_project)-int(before_project)
            self.total['approved']+=delta;self.cells[cell]['approved']+=delta
            self.epochs[identity]=(cell,fp,owners,blocked)
            self.decisions[(protocol,identity)]=(included,approved)
            touched.add(identity)
        self.watermark=next_watermark
        self.last_work={'decisions':len(updates),'epochs':len(touched)}

    def _metadata_delta(self, protocol, identity, delta):
        row=self.rows[identity];cell=row['cell_uuid']
        bins=self.cell_attributes[protocol].setdefault(cell,{field:Counter() for field in ('group_label','source_sha256')})
        for field,counts in self.attributes[protocol].items():
            value=row.get(field)
            counts[value]+=delta
            if counts[value]==0:del counts[value]
        for field,counts in bins.items():
            value=row.get(field);counts[value]+=delta
            if counts[value]==0:del counts[value]

    def protocol_values(self, protocol, field):
        self._check();return list(self.attributes[protocol][field])

    def cell_values(self, protocol, cell, field):
        self._check();return list(self.cell_attributes[protocol][cell][field])

    def apply_membership(self, protocol, *, added, removed):
        """Publish an admitted membership delta, retaining exact integer counts.

        The caller proves the old/new binding and reads saved decisions for all
        added UUIDs. Ordered durations are explicitly pending until preparation.
        Source publication must be unchanged; new source epochs require prepare.
        """
        self._check()
        members=self.memberships[protocol];removed=tuple(removed);removed_set=set(removed)
        if (len(removed_set)!=len(removed) or any(key not in members for key in removed)
                or any((key in members and key not in removed_set) or key not in self.epochs for key in added)):
            raise ValueError('Membership delta does not continue this publication')
        normalized={}
        for key,row in added.items():
            if row is None:normalized[key]=(True,False)
            else:
                if type(row['included']) not in (bool,int):raise ValueError('Invalid inclusion state')
                normalized[key]=(bool(row['included']),row['review_state']=='approved'
                    and row['metadata_fingerprint']==self.epochs[key][1])
        bins=self.protocol_cells[protocol];count=self.protocols[protocol]
        for identity,adding in [(key,False) for key in removed]+[(key,True) for key in added]:
            cell,fp,owners,blocked=self.epochs[identity]
            before_project=bool(owners) and blocked==0
            included,approved=(normalized[identity] if adding else self.decisions.get((protocol,identity),(True,False)))
            delta=1 if adding else -1
            self._metadata_delta(protocol,identity,delta)
            if adding:
                members.add(identity);owners.append(protocol)
                entry=bins.setdefault(cell,_counts());self.cell_protocols.setdefault(cell,set()).add(protocol)
                self.decisions[(protocol,identity)]=(included,approved)
            else:
                members.remove(identity);owners.remove(protocol);entry=bins[cell]
                self.decisions.pop((protocol,identity),None)
            blocked+=delta*int(not approved)
            self.epochs[identity]=(cell,fp,owners,blocked)
            project_delta=int(bool(owners) and blocked==0)-int(before_project)
            self.total['approved']+=project_delta;self.cells[cell]['approved']+=project_delta
            effective=identity in self.tagged_epochs or cell in self.tagged_cells
            exported=identity in self.exported_by_protocol[protocol]
            for target in (count,entry):
                target['epochs']+=delta;target['included']+=delta*int(included)
                target['approved']+=delta*int(approved);target['approved_exportable']+=delta*int(included and approved)
                target['exported']+=delta*int(exported);target['shared_tagged_epochs']+=delta*int(effective)
                target['duration_seconds']=None;target['duration_status']='pending'
            if identity in self.tagged_epochs:
                key=(protocol,cell);self.direct_counts[key]=self.direct_counts.get(key,0)+delta
            if adding and entry['epochs']==1:
                if cell in self.tagged_cells:count['shared_tagged_cells']+=1;entry['shared_tagged_cells']=1
            elif not adding and entry['epochs']==0:
                if cell in self.tagged_cells:count['shared_tagged_cells']-=1
                del bins[cell];self.cell_protocols[cell].discard(protocol)
                self.cell_attributes[protocol].pop(cell,None)
                self.direct_counts.pop((protocol,cell),None)
        count['cells']=len(bins)
        from disco.navigation.overview_durations import MembershipOrder
        self.duration_orders[protocol]=MembershipOrder(self.duration_orders[protocol],tuple(added),frozenset(removed))
        self.duration_versions[protocol]+=1;self.duration_results.pop(protocol,None);self.duration_failures.pop(protocol,None)
        count['duration_seconds']=None;count['duration_status']='pending'
        self.last_work={'membership_added':len(added),'membership_removed':len(removed)}

    def apply_tags(self, changes):
        self._check()
        changes=list(changes)
        if any(kind not in ('cell','epoch') or not isinstance(identity,str) or type(present) is not bool for kind,identity,present in changes):
            raise ValueError('Invalid shared tag target')
        for kind,identity,present in changes:
            collection=self.tagged_cells if kind=='cell' else self.tagged_epochs
            prior=identity in collection
            if prior==present:continue
            if kind=='epoch':
                if identity not in self.epochs:continue
                cell,_,owners,_=self.epochs[identity]
                delta=int(present)-int(prior)
                for protocol in [None,*owners]:
                    key=(protocol,cell);self.direct_counts[key]=self.direct_counts.get(key,0)+delta
                    if cell not in self.tagged_cells:
                        target=self.total if protocol is None else self.protocols[protocol]
                        target['shared_tagged_epochs']+=delta
                        (self.cells[cell] if protocol is None else self.protocol_cells[protocol][cell])['shared_tagged_epochs']+=delta
            else:
                if identity not in self.cells:continue
                delta=int(present)-int(prior)
                # Visit only protocols containing this cell; never enumerate epochs.
                for protocol in [None,*self.cell_protocols.get(identity,())]:
                    bins=self.cells if protocol is None else self.protocol_cells[protocol]
                    if identity not in bins:continue
                    entry=bins[identity];target=self.total if protocol is None else self.protocols[protocol]
                    amount=delta*(entry['epochs']-self.direct_counts.get((protocol,identity),0))
                    target['shared_tagged_epochs']+=amount;entry['shared_tagged_epochs']+=amount
                    target['shared_tagged_cells']+=delta;entry['shared_tagged_cells']+=delta
            if present:collection.add(identity)
            else:collection.discard(identity)

    def project_counts(self):
        self._check();return _finish(self.total)

    def protocol_counts(self, protocol):
        self._check();value=_finish(self.protocols[protocol])
        if protocol in self.duration_results:
            value['duration_seconds']=self.duration_results[protocol][0];value.pop('duration_status',None)
        if protocol in self.duration_failures:value['duration_seconds']=None;value['duration_status']='failed'
        return value

    def retained_counts(self, protocol):
        """Canonical total_counts, including its distinct builtin duration sum."""
        value=self.protocol_counts(protocol)
        if value['duration_seconds'] is not None:
            value['duration_seconds']=(self.duration_results[protocol][2] if protocol in self.duration_results
                                       else self.retained_durations[protocol])
        return value

    def cell_counts(self, cell, protocol=None):
        self._check();value=_finish((self.cells if protocol is None else self.protocol_cells[protocol])[cell])
        if protocol is not None and self.duration_versions[protocol]>0:
            value['duration_seconds']=None;value['duration_status']='pending'
        if protocol in self.duration_results:
            value['duration_seconds']=self.duration_results[protocol][1][cell];value.pop('duration_status',None)
        if protocol in self.duration_failures:value['duration_seconds']=None;value['duration_status']='failed'
        return value

    def publish_duration(self, protocol, version, value):
        if self.ready and self.duration_versions.get(protocol)==version:
            self.duration_results[protocol]=value;self.duration_failures.pop(protocol,None);self.duration_serial+=1;return True
        return False

    def fail_duration(self, protocol, version):
        if self.ready and self.duration_versions.get(protocol)==version:
            self.duration_failures[protocol]=True;self.duration_serial+=1;return True
        return False
