"""Lazy shared-tag autocomplete over the existing disposable membership index.

Counts refer to distinct (kind, target UUID), never profile rows or inherited
copies. Author attribution remains keyed by profile UUID; a profile's stored
name is taken from its lexically last (kind, target) tagged record, making the
formerly unspecified SQL-row order deterministic. No acquisition data is copied.
"""
from __future__ import annotations


class SharedVocabulary:
    def __init__(self, index):
        self.index = index
        self.sequence = 0
        db = index.connection
        db.create_function('shared_casefold', 1, str.casefold, deterministic=True)
        db.executescript('''
            CREATE TABLE shared_vocabulary_counts(tag_id INTEGER PRIMARY KEY REFERENCES tag_values(tag_id) ON DELETE CASCADE, amount INTEGER NOT NULL);
            CREATE INDEX shared_vocabulary_prefix ON tag_values(shared_casefold(tag));
            CREATE TABLE shared_vocabulary_ready(tag_id INTEGER PRIMARY KEY REFERENCES tag_values(tag_id) ON DELETE CASCADE, used INTEGER NOT NULL);
            CREATE TABLE shared_vocabulary_authors(tag_id INTEGER REFERENCES tag_values(tag_id) ON DELETE CASCADE,
                profile TEXT COLLATE BINARY, author TEXT, kind TEXT COLLATE BINARY, target TEXT COLLATE BINARY,
                PRIMARY KEY(tag_id,profile)) WITHOUT ROWID;
        ''')
        with db:
            db.execute('INSERT INTO shared_vocabulary_counts SELECT tag_id,COUNT(*) FROM '
                '(SELECT m.tag_id,r.kind,r.target FROM tag_memberships m JOIN records r ON r.record_id=m.record_id '
                'GROUP BY m.tag_id,r.kind,r.target) GROUP BY tag_id')

    def discard(self):
        """Large external batches rebuild SQL aggregates lazily, without a
        Python copy of unbounded old/new target unions. Caller owns transaction.
        """
        for table in ('shared_vocabulary_counts','shared_vocabulary_authors','shared_vocabulary_ready'):
            self.index.connection.execute('DROP TABLE '+table)
        self.index.connection.execute('DROP INDEX shared_vocabulary_prefix')

    def before(self, keys):
        db = self.index.connection
        targets = {(key['target_kind'], key['target_uuid']) for key in keys}
        unions = {key: {row[0] for row in db.execute('SELECT DISTINCT m.tag_id FROM records r '
            'JOIN tag_memberships m ON m.record_id=r.record_id WHERE r.kind=? AND r.target=?', key)} for key in targets}
        records = {}
        for key in keys:
            identity = (key['target_kind'], key['target_uuid'], key['profile_uuid'])
            records[identity] = {row[0] for row in db.execute('SELECT m.tag_id FROM records r '
                'JOIN tag_memberships m ON m.record_id=r.record_id WHERE r.kind=? AND r.target=? AND r.profile=?', identity)}
        return unions, records

    def after(self, keys, previous):
        db = self.index.connection
        current, records = self.before(keys)
        old_unions, old_records = previous
        for identity, before in old_unions.items():
            after = current[identity]
            for tag_id in before - after:
                # Removing the last membership cascades the vocabulary row.
                db.execute('UPDATE shared_vocabulary_counts SET amount=amount-1 WHERE tag_id=?', (tag_id,))
            for tag_id in after - before:
                db.execute('INSERT INTO shared_vocabulary_counts VALUES (?,1) '
                    'ON CONFLICT(tag_id) DO UPDATE SET amount=amount+1', (tag_id,))
        # Only already-requested author lists need maintenance. The canonical
        # winner usually stays unchanged when the scientist edits another row.
        for identity in old_records:
            kind, target, profile = identity
            for tag_id in old_records[identity] | records[identity]:
                if not db.execute('SELECT 1 FROM shared_vocabulary_ready WHERE tag_id=?', (tag_id,)).fetchone():
                    continue
                winner = db.execute('SELECT kind,target FROM shared_vocabulary_authors WHERE tag_id=? AND profile=?', (tag_id, profile)).fetchone()
                if winner is not None and winner != (kind, target) and (tag_id not in records[identity] or winner > (kind, target)):
                    continue
                # A changed winning record may have lost the tag; resolve the
                # exact surviving winner, including other records by that UUID.
                found = db.execute('SELECT r.author,r.kind,r.target FROM tag_memberships m JOIN records r '
                    'ON r.record_id=m.record_id WHERE m.tag_id=? AND r.profile=? '
                    'ORDER BY r.kind DESC,r.target DESC LIMIT 1', (tag_id, profile)).fetchone()
                db.execute('DELETE FROM shared_vocabulary_authors WHERE tag_id=? AND profile=?', (tag_id, profile))
                if found:
                    db.execute('INSERT INTO shared_vocabulary_authors VALUES (?,?,?,?,?)', (tag_id, profile, *found))
        if db.execute('SELECT 1 FROM shared_vocabulary_counts WHERE amount<=0 LIMIT 1').fetchone():
            raise ValueError('Shared vocabulary counts no longer match annotation targets')

    def authors(self, tag_id):
        db = self.index.connection
        if not db.execute('SELECT 1 FROM shared_vocabulary_ready WHERE tag_id=?', (tag_id,)).fetchone():
            db.execute('INSERT INTO shared_vocabulary_authors SELECT ?,profile,author,kind,target FROM '
                '(SELECT r.profile,r.author,r.kind,r.target,ROW_NUMBER() OVER '
                '(PARTITION BY r.profile ORDER BY r.kind DESC,r.target DESC) AS position '
                'FROM tag_memberships m JOIN records r ON r.record_id=m.record_id WHERE m.tag_id=?) WHERE position=1', (tag_id, tag_id))
            db.execute('INSERT INTO shared_vocabulary_ready VALUES (?,0)', (tag_id,))
        self.sequence += 1
        db.execute('UPDATE shared_vocabulary_ready SET used=? WHERE tag_id=?', (self.sequence, tag_id))
        return [{'profile_uuid': profile, 'display_name': name} for profile, name in db.execute(
            'SELECT profile,author FROM shared_vocabulary_authors WHERE tag_id=? ORDER BY profile', (tag_id,))]

    def suggestions(self, query, limit):
        from workspace_curation_vocabulary import CurationVocabulary
        db = self.index.connection
        prefix = query.strip().casefold()
        where = ''; params = []
        if any(0xd800 <= ord(char) <= 0xdfff for char in prefix):
            where = ' WHERE 0'
        elif prefix:
            where = ' WHERE shared_casefold(v.tag)>=?'; params.append(prefix)
            upper = CurationVocabulary._upper_prefix(prefix)
            if upper is not None:
                where += ' AND shared_casefold(v.tag)<?'; params.append(upper)
        source = ' FROM tag_values v JOIN shared_vocabulary_counts c ON c.tag_id=v.tag_id' + where
        total = db.execute('SELECT COUNT(*)' + source, params).fetchone()[0]
        rows = db.execute('SELECT v.tag_id,v.tag,c.amount' + source +
            ' ORDER BY c.amount DESC,v.tag COLLATE TAG_ORDER LIMIT ?', (*params, limit)).fetchall()
        with db:
            tags = [{'tag': tag, 'count': count, 'authors': self.authors(tag_id)} for tag_id, tag, count in rows]
            # Retain author evidence for at most 128 requested tag names. Counts
            # remain compact per-tag integers; UUID/author lists are not copied
            # for the entire vocabulary just because many prefixes were typed.
            retired = [row[0] for row in db.execute('SELECT tag_id FROM shared_vocabulary_ready ORDER BY used DESC LIMIT -1 OFFSET 128')]
            db.executemany('DELETE FROM shared_vocabulary_authors WHERE tag_id=?', ((key,) for key in retired))
            db.executemany('DELETE FROM shared_vocabulary_ready WHERE tag_id=?', ((key,) for key in retired))
        self.index._check_generation()
        return {'tags': tags, 'scope': 'project_shared_annotations', 'query': query, 'total': total,
            'limit': limit, 'count_unit': 'distinct_annotation_targets', 'match': 'case_insensitive_prefix', 'has_more': total > limit}
