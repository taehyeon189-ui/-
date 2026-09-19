from test_wallet_release import SOURCE
import base64, io, unittest
from types import SimpleNamespace
from unittest.mock import Mock
from PIL import Image
from scheduler_images import image_key, visible_rows, grouped_contents
from scheduler_image_data import IMAGES
from scheduler_ui import Panel

class SchedulerImageTests(unittest.TestCase):
    def test_names_and_specific_boss_priority(self):
        for kind,name,key in [('bosses','하드 진 힐라','verus_hilla'),('bosses','노멀 힐라','hilla'),
            ('bosses','가디언 엔젤 슬라임','slime_guardian'),('daily','소멸의 여로 일일 퀘스트','vj'),
            ('weekly','배고픈 무토','chuchu'),('daily','카르시온 일일 퀘스트','carcion')]:
            self.assertEqual(image_key(kind,name),key)
        self.assertIsNone(image_key('bosses','미등록 보스'))
        self.assertIsNone(image_key('daily','루시드'))
    def test_images_are_bundled_valid_and_uniform(self):
        self.assertEqual(len(IMAGES),40)
        for value in IMAGES.values():
            image=Image.open(io.BytesIO(base64.b64decode(value,validate=True)))
            self.assertEqual(image.size,(44,44));image.verify()
    def test_sort_and_filter_without_mutation(self):
        rows=[{'done':True},{'done':None},{'done':False}]
        self.assertEqual([r['done'] for r in visible_rows(rows)],[False,None,True])
        self.assertEqual([r['done'] for r in visible_rows(rows,True)],[False,None])
        self.assertIs(rows[0]['done'],True)
    def test_render_assigns_images_and_status_tags(self):
        tree=Mock();tree.get_children.return_value=[]
        rows=[dict(name='루시드',difficulty='노멀',cycle='주간',status='완료',done=True),
              dict(name='윌',difficulty='노멀',cycle='주간',status='미완료',done=False)]
        owner=SimpleNamespace(window=Mock(),failed=False,status_banner=Mock(),cards={},
            trees={'bosses':tree},result={'bosses':rows},hide_done=Mock(),scheduler_images=Mock())
        owner.hide_done.get.return_value=False
        Panel.render(owner)
        self.assertEqual(tree.insert.call_args_list[0].kwargs['tags'],('pending',))
        self.assertEqual(tree.insert.call_args_list[1].kwargs['tags'],('done',))
        self.assertEqual(owner.scheduler_images.get.call_count,2)

    def test_requested_groups_only_without_losing_raw_data(self):
        data={'daily':[{'name':'몬스터파크','type':'contents','done':False},
                       {'name':'몬스터파크 익스트림','type':'contents','done':None},
                       {'name':'길드 출석','type':'contents','done':True},
                       {'name':'소멸의 여로','type':'quest','done':False}],
              'weekly':[{'name':'헤이븐 주간 퀘스트','type':'quest','done':False},
                        {'name':'길드 주간 명성치','type':'contents','done':False}],
              'bosses':[{'name':'검은 마법사','done':None}]}
        grouped=grouped_contents(data)
        self.assertEqual(len(grouped['monster_park']),2)
        self.assertEqual([r['name'] for r in grouped['daily']],['소멸의 여로'])
        self.assertEqual([r['name'] for r in grouped['weekly']],['헤이븐 주간 퀘스트'])
        self.assertEqual(len(data['daily']),4)
        self.assertIsNone(grouped['bosses'][0]['done'])

    def test_added_images(self):
        for name in ['검은 마법사','아카이럼','반 레온','혼테일','카웅']:
            self.assertIn(image_key('bosses',name),IMAGES)
        self.assertIn(image_key('monster_park','몬스터파크 익스트림'),IMAGES)
