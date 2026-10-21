"""Prepared read counts and exact target deltas, without SQL or HTTP."""
import unittest
from disco.navigation.overview_projection import OverviewProjection, ProjectionUnavailable


class OverviewProjectionTests(unittest.TestCase):
    def model(self):
        rows={str(i):{'epoch_uuid':str(i),'cell_uuid':'a' if i<2 else 'b',
                     'duration_seconds':float(i+1)} for i in range(4)}
        return OverviewProjection.prepare(rows=rows, memberships={'p':['0','1','2'],'q':['1','3']},
            fingerprints={key:'fresh' for key in rows}, decisions=[], publication='pub', watermark=0)

    def test_overlap_approval_and_inclusion_are_independent(self):
        model=self.model()
        model.apply_decisions([('p','1',{'included':False,'review_state':'approved','metadata_fingerprint':'fresh'})],0,1)
        self.assertEqual(model.protocol_counts('p')['approved'],1)
        self.assertEqual(model.protocol_counts('p')['included'],2)
        self.assertEqual(model.protocol_counts('p')['approved_exportable'],0)
        self.assertEqual(model.project_counts()['approved'],0)
        model.apply_decisions([('q','1',{'included':True,'review_state':'approved','metadata_fingerprint':'fresh'})],1,2)
        self.assertEqual(model.project_counts()['approved'],1)
        self.assertEqual(model.cell_counts('a')['reviewed'],1)
        model.apply_decisions([('p','1',None)],2,3)
        self.assertEqual(model.project_counts()['approved'],0)
        self.assertEqual(model.protocol_counts('p')['included'],3)

    def test_stale_fingerprint_never_approves_and_unknown_epochs_do_not_count(self):
        model=self.model()
        model.apply_decisions([('p','0',{'included':True,'review_state':'approved','metadata_fingerprint':'old'}),
                               ('p','outside',{'included':False,'review_state':'approved','metadata_fingerprint':'fresh'})],0,1)
        self.assertEqual(model.project_counts()['approved'],0)
        self.assertEqual(model.protocol_counts('p')['included'],3)

    def test_target_delta_does_not_iterate_memberships_or_rows(self):
        model=self.model()
        class LookupOnly(dict):
            def __iter__(self):raise AssertionError('full iteration')
            def items(self):raise AssertionError('full iteration')
            def values(self):raise AssertionError('full iteration')
        model.epochs=LookupOnly(model.epochs)
        model.memberships={key:LookupOnly(dict.fromkeys(value)) for key,value in model.memberships.items()}
        model.apply_decisions([('p','0',{'included':True,'review_state':'approved','metadata_fingerprint':'fresh'})],0,1)
        self.assertEqual(model.project_counts()['approved'],1)
        self.assertEqual(model.last_work,{'decisions':1,'epochs':1})

    def test_effective_tag_counts_preserve_cell_epoch_overlap(self):
        model=self.model()
        model.apply_tags([('epoch','1',True)])
        self.assertEqual(model.project_counts()['shared_tagged_epochs'],1)
        model.apply_tags([('cell','a',True)])
        self.assertEqual(model.project_counts()['shared_tagged_epochs'],2)
        self.assertEqual(model.protocol_counts('p')['shared_tagged_epochs'],2)
        self.assertEqual(model.protocol_counts('q')['shared_tagged_epochs'],1)
        model.apply_tags([('epoch','0',True),('epoch','1',False)])
        self.assertEqual(model.project_counts()['shared_tagged_epochs'],2)
        model.apply_tags([('cell','a',False)])
        self.assertEqual(model.project_counts()['shared_tagged_epochs'],1)
        self.assertEqual(model.protocol_counts('q')['shared_tagged_epochs'],0)
        self.assertEqual(model.project_counts()['shared_tagged_cells'],0)

    def test_invalid_later_delta_cannot_apply_earlier_delta(self):
        model=self.model()
        with self.assertRaises(KeyError):
            model.apply_decisions([('p','0',{'included':False,'review_state':'approved','metadata_fingerprint':'fresh'}),
                                   ('p','1',{})],0,1)
        self.assertEqual(model.protocol_counts('p')['included'],3)
        self.assertEqual(model.watermark,0)

    def test_membership_delta_updates_exact_counts_and_marks_only_duration_pending(self):
        model=self.model()
        approved={'included':True,'review_state':'approved','metadata_fingerprint':'fresh'}
        model.apply_decisions([('p','0',approved)],0,1)
        self.assertEqual(model.project_counts()['approved'],1)
        model.apply_membership('q',added={'0':approved},removed=['1'])
        self.assertEqual(model.protocol_counts('q')['epochs'],2)
        self.assertEqual(model.protocol_counts('q')['approved'],1)
        self.assertEqual(model.project_counts()['approved'],1)
        self.assertIsNone(model.protocol_counts('q')['duration_seconds'])
        self.assertEqual(model.protocol_counts('q')['duration_status'],'pending')
        self.assertEqual(model.project_counts()['duration_seconds'],10.)
        model.apply_membership('q',added={},removed=['0'])
        self.assertEqual(model.protocol_counts('q')['cells'],1)
        self.assertEqual(model.project_counts()['approved'],1)

    def test_superseded_duration_worker_cannot_publish_old_membership(self):
        from disco.navigation.overview_durations import fold_duration
        model=self.model()
        model.apply_membership('p',added={},removed=['0'])
        version=model.duration_versions['p'];order=model.duration_orders['p']
        model.apply_membership('p',added={},removed=['1'])
        self.assertFalse(model.publish_duration('p',version,fold_duration(order,model.rows)))
        self.assertIsNone(model.protocol_counts('p')['duration_seconds'])
        current=model.duration_versions['p']
        self.assertTrue(model.publish_duration('p',current,fold_duration(model.duration_orders['p'],model.rows)))
        self.assertEqual(model.protocol_counts('p')['duration_seconds'],3.)
        self.assertNotIn('duration_status',model.protocol_counts('p'))

    def test_duration_worker_coalesces_obsolete_queued_publications(self):
        import threading
        from disco.navigation.overview_durations import DurationPreparation
        entered=threading.Event();release=threading.Event();published=threading.Event();seen=[]
        class Rows(dict):
            def __getitem__(self,key):
                if key=='old':entered.set();release.wait(2)
                seen.append(key)
                return {'cell_uuid':'a','duration_seconds':1}
        owner=DurationPreparation();self.addCleanup(owner.close)
        try:
            owner.submit(('old',),Rows(),lambda result:self.fail('obsolete running result'),key='p')
            self.assertTrue(entered.wait(2))
            owner.submit(('middle',),Rows(),lambda result:self.fail('obsolete queued result'),key='p')
            owner.submit(('new',),Rows(),lambda result:published.set(),key='p')
            release.set();self.assertTrue(published.wait(2))
            self.assertEqual(seen,['old','new'])
        finally:release.set()

    def test_stale_watermark_rejects_without_partial_changes(self):
        model=self.model()
        with self.assertRaises(ProjectionUnavailable):model.apply_decisions([('p','0',None)],4,5)
        self.assertEqual(model.watermark,0)
        self.assertEqual(model.project_counts()['approved'],0)

    def test_prepared_duration_follows_canonical_membership_order(self):
        rows={key:{'epoch_uuid':key,'cell_uuid':'a','duration_seconds':value}
              for key,value in [('a',1e16),('b',1.),('c',1.)]}
        model=OverviewProjection.prepare(rows=rows,memberships={'p':['b','c','a']},
            fingerprints=dict.fromkeys(rows,'f'),decisions=[],publication=1,watermark=0)
        self.assertEqual(model.protocol_counts('p')['duration_seconds'],sum(rows[key]['duration_seconds'] for key in ['b','c','a']))
        expected=0
        for row in rows.values():expected+=row['duration_seconds']
        self.assertEqual(model.project_counts()['duration_seconds'],expected)


if __name__=='__main__':unittest.main()
