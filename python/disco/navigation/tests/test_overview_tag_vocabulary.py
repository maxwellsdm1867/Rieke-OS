import unittest
from disco.navigation.overview_tag_vocabulary import TagVocabulary


class VocabularyTests(unittest.TestCase):
    def test_cell_and_epoch_union_overlapping_protocols_and_rank(self):
        owner=TagVocabulary({'0':('a',('p',)),'1':('a',('p','q')),'2':('b',('q',))},
                            {None:{'a':2,'b':1},'p':{'a':2},'q':{'a':1,'b':1}})
        self.addCleanup(owner.close)
        owner.update('epoch','0',{'red'})
        owner.update('cell','a',{'red','blue'})
        self.assertEqual(owner.summary()['tags'],[{'tag':'blue','epoch_count':2,'cell_count':1},{'tag':'red','epoch_count':2,'cell_count':1}])
        self.assertEqual(owner.summary('q')['tags'][0]['epoch_count'],1)
        owner.update('cell','a',set())
        self.assertEqual(owner.summary()['tags'],[{'tag':'red','epoch_count':1,'cell_count':1}])
        self.assertEqual(owner.summary('q')['tags'],[])
        owner.update('epoch','2',{'red'})
        self.assertEqual(owner.summary()['tags'],[{'tag':'red','epoch_count':2,'cell_count':2}])
        owner.update('epoch','0',set());owner.update('epoch','2',set())
        self.assertEqual(owner.summary(),{'tags':[],'total_tags':0,'truncated':False})

    def test_membership_added_and_removed_preserve_local_vocabulary(self):
        owner=TagVocabulary({'0':('a',('p',)),'1':('a',('q',))},{None:{'a':2},'p':{'a':1},'q':{'a':1}})
        self.addCleanup(owner.close)
        owner.update('cell','a',{'cell'});owner.update('epoch','0',{'direct'})
        owner.membership('q','0',True)
        self.assertEqual(owner.summary('q')['tags'],[{'tag':'cell','epoch_count':2,'cell_count':1},{'tag':'direct','epoch_count':1,'cell_count':1}])
        owner.membership('q','0',False)
        self.assertEqual(owner.summary('q')['tags'],[{'tag':'cell','epoch_count':1,'cell_count':1}])


if __name__=='__main__':unittest.main()
