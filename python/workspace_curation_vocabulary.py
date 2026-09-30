"""Exact, incremental dataset-tag suggestions backed by the bounded SQL feed.

Tag strings and record/tag links use the same normalized disposable index as
shared annotations. Counts are unions by epoch UUID across protocol records;
changing one record updates only the affected epochs' vocabulary contributions.
"""
from __future__ import annotations

import json

from workspace_shared_tag_index import SharedTagIndex, _serialized


class CurationVocabulary(SharedTagIndex):
    def __init__(self, store, tracker):
        self.store,self.tracker=store,tracker
        self.previous_unions={}
        if store.project_uuid!=tracker.project_uuid or store.dj.conn() is not tracker.connection:
            raise ValueError('Curation vocabulary and recovery authority must share one project connection')
        super().__init__(generation=tracker.token,changes=self._changes,
            records=self._records,validate=self._validated_tags)

    def _open(self):
        opened=self.connection is not None
        db=super()._open()
        if not opened:
            db.create_function('casefold',1,lambda value:value.casefold(),deterministic=True)
            db.executescript('''
                CREATE TABLE vocabulary_counts(tag_id INTEGER PRIMARY KEY REFERENCES tag_values(tag_id) ON DELETE CASCADE,
                    epoch_count INTEGER NOT NULL);
                CREATE INDEX vocabulary_rank ON vocabulary_counts(epoch_count DESC);
                CREATE INDEX vocabulary_prefix ON tag_values(casefold(tag));
                CREATE TEMP TABLE vocabulary_changed_epochs(epoch TEXT COLLATE BINARY PRIMARY KEY) WITHOUT ROWID;
            ''')
        return db

    @staticmethod
    def _validated_tags(row):
        values=row['tags']
        if not isinstance(values,list) or any(not isinstance(tag,str) or not tag.strip()
                or tag!=tag.strip() or len(tag)>255 for tag in values):
            raise ValueError('Saved tag vocabulary contains an invalid tag record')
        # The existing vocabulary endpoint counts duplicate saved tag strings
        # once, and permits more than the shared-annotation100-tag limit.
        return list(dict.fromkeys(values))

    def _unions(self, keys):
        db=self._open()
        db.execute('DELETE FROM vocabulary_changed_epochs')
        db.executemany('INSERT OR IGNORE INTO vocabulary_changed_epochs VALUES (?)',
            ((key['target_uuid'],) for key in keys))
        result={key['target_uuid']:set() for key in keys}
        for epoch,tag in db.execute("SELECT r.target,v.tag FROM vocabulary_changed_epochs e "
                "JOIN records r ON r.kind='epoch' AND r.target=e.epoch "
                'JOIN tag_memberships m ON m.record_id=r.record_id JOIN tag_values v ON v.tag_id=m.tag_id '
                'GROUP BY r.target,v.tag'):
            result[epoch].add(tag)
        return result

    def _changes(self, previous):
        with self.tracker.capture(previous) as plan:
            if plan is None or not plan.complete:return None
            names=plan.primary_keys.get('curation',[])
            if names!=['project_uuid','protocol_uuid','epoch_uuid']:
                raise ValueError('Unsupported curation identity layout')
            keys=[{'target_kind':'epoch','target_uuid':key[2],'profile_uuid':key[1]}
                for key in plan.keys.get('curation',[])]
            current=plan.watermark
            plan.verify()
        self.previous_unions=self._unions(keys)
        return keys,current

    def _records(self, keys):
        connection=self.tracker.connection
        def translated(row):
            values=row['tags']
            if isinstance(values,(str,bytes,bytearray)):values=json.loads(values)
            return {'target_kind':'epoch','target_uuid':row['epoch_uuid'],'profile_uuid':row['protocol_uuid'],
                'author_name':'','revision':0,'tags':values}
        if keys is None:
            last=None
            while True:
                restriction=' AND (protocol_uuid>%s OR (protocol_uuid=%s AND epoch_uuid>%s))' if last else ''
                args=(self.store.project_uuid,*((last[0],last[0],last[1]) if last else ()))
                rows=connection.query('SELECT protocol_uuid,epoch_uuid,tags FROM recording_workspace.curation '
                    'WHERE project_uuid=%s'+restriction+' ORDER BY protocol_uuid,epoch_uuid LIMIT 500',
                    args,as_dict=True,reconnect=False).fetchall()
                if not rows:return
                for row in rows:yield translated(row)
                last=(rows[-1]['protocol_uuid'],rows[-1]['epoch_uuid'])
        else:
            for start in range(0,len(keys),200):
                batch=keys[start:start+200]
                if not batch:continue
                restriction=' OR '.join('(protocol_uuid=%s AND epoch_uuid=%s)' for _ in batch)
                args=(self.store.project_uuid,*(value for key in batch for value in (key['profile_uuid'],key['target_uuid'])))
                rows=connection.query('SELECT protocol_uuid,epoch_uuid,tags FROM recording_workspace.curation '
                    'WHERE project_uuid=%s AND ('+restriction+')',args,as_dict=True,reconnect=False).fetchall()
                for row in rows:yield translated(row)

    def _update_summary(self, keys):
        db=self.connection
        if keys is None:
            db.execute('DELETE FROM vocabulary_counts')
            db.execute('INSERT INTO vocabulary_counts SELECT m.tag_id,COUNT(DISTINCT r.target) '
                'FROM records r JOIN tag_memberships m ON m.record_id=r.record_id GROUP BY m.tag_id')
            self.previous_unions={}
            return
        if not keys:return
        current=self._unions(keys)
        delta={}
        for epoch in self.previous_unions.keys()|current.keys():
            before=self.previous_unions.get(epoch,set());after=current.get(epoch,set())
            for tag in before-after:delta[tag]=delta.get(tag,0)-1
            for tag in after-before:delta[tag]=delta.get(tag,0)+1
        for tag,amount in delta.items():
            if not amount:continue
            found=db.execute('SELECT tag_id FROM tag_values WHERE tag=?',(tag,)).fetchone()
            if found is None:
                # Removing the last record for a tag already removed its count
                # through the tag_values foreign-key cascade.
                if amount>0:raise ValueError('Tag vocabulary is missing a new tag identity')
                continue
            tag_id=found[0]
            db.execute('INSERT OR IGNORE INTO vocabulary_counts VALUES (?,0)',(tag_id,))
            db.execute('UPDATE vocabulary_counts SET epoch_count=epoch_count+? WHERE tag_id=?',(amount,tag_id))
        if db.execute('SELECT 1 FROM vocabulary_counts WHERE epoch_count<=0 LIMIT 1').fetchone():
            raise ValueError('Tag vocabulary aggregate no longer matches exact memberships')
        self.previous_unions={}

    @staticmethod
    def _upper_prefix(prefix):
        for index in range(len(prefix)-1,-1,-1):
            if ord(prefix[index])<0x10ffff:
                following=ord(prefix[index])+1
                if 0xd800<=following<=0xdfff:following=0xe000
                return prefix[:index]+chr(following)
        return None

    @_serialized
    def suggestions(self, query, limit):
        if not self.refresh():return None
        prefix=query.casefold();where='';params=[]
        if any(0xd800<=ord(character)<=0xdfff for character in prefix):
            where=' WHERE 0'
            prefix=''  # Canonical MySQL UTF-8 tags cannot contain surrogates.
        if prefix:
            where=' WHERE casefold(v.tag)>=?';params.append(prefix)
            upper=self._upper_prefix(prefix)
            if upper is not None:where+=' AND casefold(v.tag)<?';params.append(upper)
        source=' FROM tag_values v JOIN vocabulary_counts c ON c.tag_id=v.tag_id'+where
        total=self.connection.execute('SELECT COUNT(*)'+source,params).fetchone()[0]
        rows=self.connection.execute('SELECT v.tag,c.epoch_count'+source+
            ' ORDER BY c.epoch_count DESC,v.tag COLLATE TAG_ORDER LIMIT ?',(*params,limit)).fetchall()
        self._check_generation()
        return {'tags':[{'tag':tag,'count':count} for tag,count in rows],'q':query,'limit':limit,
            'total':total,'has_more':total>limit,'project_uuid':self.store.project_uuid,
            'scope':'project_saved_curation','count_unit':'distinct_epochs',
            'match':'case_insensitive_prefix','history_included':False}
