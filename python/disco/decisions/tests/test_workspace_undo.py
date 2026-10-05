import unittest
from disco.decisions.undo import annotation_inverse,curation_inverse

class InverseBoundsTests(unittest.TestCase):
    def test_oversized_gesture_returns_before_allocating_or_reading_states(self):
        class Oversized:
            def __len__(self):return 1001
            def items(self):raise AssertionError('Oversized inverse cannot iterate targets')
            def __iter__(self):raise AssertionError('Oversized inverse cannot iterate targets')
        self.assertEqual(curation_inverse('protocol',None,Oversized(),{})['kind'],'unavailable')
        self.assertEqual(annotation_inverse(None,Oversized())['kind'],'unavailable')

    def test_shared_change_patterns_admit_full_1000_target_gesture(self):
        before=[{'target_uuid':f'00000000-0000-0000-0000-{i:012d}','revision':0,'tags':[]} for i in range(1000)]
        after=[{**row,'revision':1,'tags':['keep'],'target_kind':'epoch','profile_uuid':'00000000-0000-0000-0000-000000000001'} for row in before]
        value=annotation_inverse(before,after)
        self.assertEqual(value['kind'],'annotations');self.assertEqual(len(value['targets']),1000)
        self.assertEqual(value['patterns'],[{'tags_add':[],'tags_remove':['keep']}])
        self.assertNotIn('tags',value['targets'][0])

if __name__=='__main__':unittest.main()
