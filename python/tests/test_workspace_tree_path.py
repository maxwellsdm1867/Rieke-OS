"""Pure row/path matching agrees with every paged branch; no native writes."""
import json
import unittest

import test_workspace_tree_pages as pages_fixture
import test_workspace_annotations as annotations_fixture
from disco.workbench.recipes import checksum
from disco.navigation.tree import joint_id
from disco.navigation.tree_pages import TreePages, TreePath, validate_tree_path


class TreePathTests(unittest.TestCase):
    def setUp(self):
        self.case=pages_fixture.TreePageTests()
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.service,self.pager=self.case.service,self.case.pager

    def assert_page_parity(self,body):
        rows,_,values,definitions,order,_=self.pager._scope(body)
        root=self.pager.page({**body,'limit':2})
        checked=0
        def walk(path):
            nonlocal checked
            matcher=TreePath(order,definitions,path)
            matched={row['epoch_uuid'] for row in rows if matcher.matches(values[row['epoch_uuid']])}
            visible=set()
            offset=0
            while True:
                page=self.pager.page({**body,'path':path,'offset':offset,'limit':2,'revision':root['revision']})
                self.assertEqual(page['selection']['count'],len(matched))
                if page['kind']=='epochs':
                    visible.update(row['epoch_uuid'] for row in page['epochs'])
                else:
                    for branch in page['branches']:
                        child=TreePath(order,definitions,branch['path'])
                        child_ids={row['epoch_uuid'] for row in rows if child.matches(values[row['epoch_uuid']])}
                        self.assertEqual(branch['count'],len(child_ids))
                        visible.update(child_ids)
                        walk(branch['path'])
                if not page['has_more']:break
                offset+=page['limit']
            self.assertEqual(visible,matched)
            checked+=1
        walk([])
        self.assertGreater(checked,0)

    def test_all_pages_scalar_sequential_and_joint_membership(self):
        for splits in ('parameters/value','cell,parameters/value',
                       joint_id(['parameters/value','parameters/other']),
                       'parameters/other,parameters/value',''):
            with self.subTest(splits=splits):self.assert_page_parity({'splits':splits})

    def test_source_predicate_and_frozen_protocol_filter_stay_in_caller_scope(self):
        self.assert_page_parity({'splits':'parameters/value','predicate':{
            'not':{'field':'parameters/value','operator':'eq','value':1}}})
        self.assert_page_parity({'protocol_uuid':self.service.protocol_id,'splits':'parameters/value',
            'filters':{'metadata_predicate':json.dumps({'field':'parameters/value','operator':'eq','value':1})}})
        self.service.set_source_state_provider(lambda:{'a'*64:{'query_excluded':True}})
        self.assert_page_parity({'splits':'parameters/value'})

    def test_scalar_keys_preserve_presence_type_signed_zero_and_nested_values(self):
        field='parameters/value'
        matcher=TreePath([field],{field:{}})
        values=[{}, {field:None}, {field:True}, {field:1}, {field:1.0},
                {field:'1'}, {field:0.0}, {field:-0.0}, {field:[1,2]},
                {field:[2,1]}, {field:{'x':None}}, {field:''}]
        keys=[matcher.key(current,field) for current in values]
        self.assertEqual(len(set(keys)),len(values))
        for current,key in zip(values,keys):
            self.assertEqual(key,checksum({'field':field,'present':field in current,
                **({'value':current[field]} if field in current else {})}))
            selected=TreePath([field],{field:{}},[key])
            self.assertEqual([row for row in values if selected.matches(row)],[current])

    def test_joint_missing_outer_presence_and_full_dependency_union(self):
        parts=['parameters/value','annotations/epoch/tags','curation/example/tags']
        field=joint_id(parts)
        definitions={part:{} for part in parts}
        definitions[field]={'components':parts}
        matcher=TreePath([field],definitions)
        self.assertEqual(matcher.fields,frozenset(parts))
        missing=matcher.key({},field)
        self.assertEqual(missing,checksum({'field':field,'present':True,
            'value':[{'present':False} for _ in parts]}))
        self.assertNotEqual(missing,matcher.key({parts[0]:None},field))
        selected=TreePath([field],definitions,[missing])
        self.assertTrue(selected.matches({}))
        self.assertFalse(selected.matches({parts[0]:None}))
        parts.append('other')  # Compiled component order cannot drift.
        self.assertEqual(matcher.key({},field),missing)

    def test_unsupported_annotation_split_fields_refuse_in_existing_scope(self):
        case=annotations_fixture.SharedAnnotationTests()
        case.setUp();self.addCleanup(case.doCleanups)
        case.edit('epoch',case.first,['direct'])
        case.edit('cell',case.other_cell,['inherited'])
        self.service=case.service
        self.pager=TreePages(case.service)
        for splits in ('annotations/epoch/tags','annotations/effective/tags',
                       joint_id(['cell','annotations/effective/tags'])):
            # Predicate annotation fields are not registered split fields in
            # this existing catalog. Never invent grouping support in a job.
            with self.subTest(splits=splits),self.assertRaises(ValueError):
                self.pager.page({'splits':splits})

    def test_malformed_excess_depth_and_unknown_joint_components_refuse(self):
        for path in ('bad',['z'*64],['a'*64]*9,[None]):
            with self.subTest(path=path),self.assertRaises(ValueError):validate_tree_path(path)
        with self.assertRaisesRegex(ValueError,'depth'):
            TreePath([],{},['a'*64])
        with self.assertRaisesRegex(ValueError,'unknown recorded field'):
            TreePath(['unknown'],{})
        with self.assertRaisesRegex(ValueError,'unknown recorded field'):
            TreePath(['joint'],{'joint':{'components':['unknown']}})
        self.assertFalse(TreePath(['cell'],{'cell':{}},['a'*64]).matches({'cell':'real'}))


if __name__=='__main__':unittest.main()
