"""Prepared exact tag unions with indexed top-12 reads and target-local updates."""
import sqlite3


class TagVocabulary:
    def __init__(self, epochs, sizes):
        self.epochs={key:(cell,set(protocols)) for key,(cell,protocols) in epochs.items()}
        self.sizes={scope:dict(cells) for scope,cells in sizes.items()}
        self.cell_protocols={}
        for scope,cells in sizes.items():
            if scope is not None:
                for cell in cells:self.cell_protocols.setdefault(cell,set()).add(scope)
        self.targets={};self.direct={};self.totals={}
        self.db=sqlite3.connect(':memory:',check_same_thread=False)
        self.db.create_collation('TAG_ORDER',lambda a,b:((a.casefold(),a)>(b.casefold(),b))-((a.casefold(),a)<(b.casefold(),b)))
        self.db.executescript('''CREATE TABLE tags(scope TEXT,tag TEXT,epochs INTEGER,cells INTEGER,PRIMARY KEY(scope,tag)) WITHOUT ROWID;
            CREATE INDEX ranking ON tags(scope,epochs DESC,tag COLLATE TAG_ORDER);''')

    def close(self):self.db.close()

    def _amount(self,scope,cell,tag):
        return (self.sizes[scope].get(cell,0) if tag in self.targets.get(('cell',cell),())
                else self.direct.get((scope,cell,tag),0))

    def _delta(self,scope,tag,before,after):
        if before==after:return
        key='' if scope is None else scope
        found=self.db.execute('SELECT epochs,cells FROM tags WHERE scope=? AND tag=?',(key,tag)).fetchone()
        epochs,cells=found or (0,0)
        epochs+=after-before;cells+=int(after>0)-int(before>0)
        if epochs<0 or cells<0:raise ValueError('Tag union counts lost continuity')
        if epochs:
            self.db.execute('INSERT OR REPLACE INTO tags VALUES (?,?,?,?)',(key,tag,epochs,cells))
            if found is None:self.totals[scope]=self.totals.get(scope,0)+1
        elif found is not None:
            self.db.execute('DELETE FROM tags WHERE scope=? AND tag=?',(key,tag))
            self.totals[scope]-=1

    def update(self,kind,identity,tags):
        if kind not in ('cell','epoch') or not isinstance(identity,str):raise ValueError('Invalid tag target')
        tags=set(tags)
        if any(not isinstance(tag,str) for tag in tags):raise ValueError('Invalid tag')
        before=self.targets.get((kind,identity),set())
        changed=before^tags
        if not changed:return
        if kind=='epoch':
            if identity not in self.epochs:return
            cell,protocols=self.epochs[identity];scopes=[None,*protocols]
        else:
            if identity not in self.sizes[None]:return
            cell=identity;scopes=[None,*self.cell_protocols.get(cell,())]
        previous={(scope,tag):self._amount(scope,cell,tag) for scope in scopes for tag in changed}
        if kind=='epoch':
            for scope in scopes:
                for tag in changed:
                    key=(scope,cell,tag)
                    value=self.direct.get(key,0)+(1 if tag in tags else -1)
                    if value:self.direct[key]=value
                    else:self.direct.pop(key,None)
        if tags:self.targets[(kind,identity)]=tags
        else:self.targets.pop((kind,identity),None)
        with self.db:
            for scope in scopes:
                for tag in changed:self._delta(scope,tag,previous[(scope,tag)],self._amount(scope,cell,tag))

    def membership(self,scope,identity,adding):
        cell,owners=self.epochs[identity]
        if (scope in owners)==adding:raise ValueError('Tag membership delta does not continue')
        direct=self.targets.get(('epoch',identity),set());inherited=self.targets.get(('cell',cell),set())
        tags=direct|inherited
        before={tag:self._amount(scope,cell,tag) for tag in tags}
        delta=1 if adding else -1
        size=self.sizes[scope].get(cell,0)+delta
        if size:self.sizes[scope][cell]=size;self.cell_protocols.setdefault(cell,set()).add(scope)
        else:self.sizes[scope].pop(cell,None);self.cell_protocols[cell].discard(scope)
        if adding:owners.add(scope)
        else:owners.remove(scope)
        for tag in direct:
            key=(scope,cell,tag);value=self.direct.get(key,0)+delta
            if value:self.direct[key]=value
            else:self.direct.pop(key,None)
        with self.db:
            for tag in tags:self._delta(scope,tag,before[tag],self._amount(scope,cell,tag))

    def summary(self,scope=None):
        rows=self.db.execute('SELECT tag,epochs,cells FROM tags WHERE scope=? ORDER BY epochs DESC,tag COLLATE TAG_ORDER LIMIT 12',
                             ('' if scope is None else scope,)).fetchall()
        total=self.totals.get(scope,0)
        return {'tags':[{'tag':tag,'epoch_count':epochs,'cell_count':cells} for tag,epochs,cells in rows],
                'total_tags':total,'truncated':total>12}
