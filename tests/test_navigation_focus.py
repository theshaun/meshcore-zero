"""Launcher-letter navigation follows focus; credentials and drafts stay literal."""
import json
import tempfile
import unittest
from unittest.mock import patch
from meshcore_zero.store import Store
from meshcore_zero.ui import UI
from meshcore_zero.preset_catalog import catalog

LETTERS='fzxcFZXC'

class NavigationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.addCleanup(self.store.db.close)
        self.store.join('#testing');self.ui=UI(self.store)
        self.chat=next(c for c in self.store.chats() if c['id']=='#testing')

    async def type_letters(self):
        for key in LETTERS:await self.ui.key(key)

    async def test_lists_and_nested_menus_accept_letters_and_arrows(self):
        u=self.ui
        for screen in ('inbox','settings','regions','nodes'):
            if screen=='nodes':
                with self.store.db:
                    for char in ('a','b'):
                        self.store.db.execute('INSERT INTO nodes VALUES(?,?)',(char*64,json.dumps(dict(public_key=char*64,name='Fixture',adv_type=1))))
            u.screen=screen;u.selected=0
            await u.key('x');self.assertEqual(u.selected,1,screen)
            await u.key('F');self.assertEqual(u.selected,0,screen)
            await u.key('down');self.assertEqual(u.selected,1,screen)
            await u.key('up');self.assertEqual(u.selected,0,screen)
        u.channel_ui.open(self.chat);await u.key('x');self.assertEqual(u.channel_ui.selected,1)
        await u.key('f');self.assertEqual(u.channel_ui.selected,0)
        u.identity_ui.open();await u.key('x');self.assertEqual(u.identity_ui.selected,1)
        await u.key('f');self.assertEqual(u.identity_ui.selected,0)
        u.backup_ui.open();await u.key('x');self.assertEqual(u.backup_ui.selected,1)
        await u.key('f');self.assertEqual(u.backup_ui.selected,0)
        u.protocol_ui.open();await u.key('x');self.assertEqual(u.protocol_ui.selected,1)
        await u.key('c');self.assertEqual(self.store.get('path_bytes_US'),'2')
        await u.key('z');self.assertEqual(self.store.get('path_bytes_US'),'1')

    async def test_join_selectors_and_map_controls_use_all_four_directions(self):
        u=self.ui;u.switch_tab(1)
        await u.key('c');self.assertEqual(u.join_ui.type,1)
        await u.key('Z');self.assertEqual(u.join_ui.type,0)
        await u.key('x');self.assertEqual(u.join_ui.field,1)
        await u.key('f');self.assertEqual(u.draft,'#f')  # Focus moved into text.
        await u.key('down');self.assertEqual(u.join_ui.field,2)
        await u.key('f');self.assertEqual(u.join_ui.field,1)
        u.screen='map';u.map_ui.scale_index=5
        dots=[{'node':{'public_key':char*64}} for char in ('a','b')]
        with patch.object(u.map_ui,'model',return_value=((0,0),'Fixture',dots,0)):
            await u.key('f');self.assertEqual(u.map_ui.zoom,4)
            await u.key('x');self.assertEqual(u.map_ui.zoom,6)
            await u.key('c');self.assertEqual(u.map_ui.selected_key,'b'*64)
            await u.key('z');self.assertEqual(u.map_ui.selected_key,'a'*64)

    async def test_every_editable_field_preserves_letters_or_its_existing_validation(self):
        u=self.ui
        u.open_chat(self.chat);await self.type_letters();self.assertEqual(u.draft,LETTERS)
        self.assertEqual(self.store.history('#testing'),[])
        u.screen='name';u.draft='';await self.type_letters();self.assertEqual(u.draft,LETTERS)
        for kind,field,attr in ((0,1,'draft'),(1,1,'private_name'),(1,2,'secret')):
            u.screen='join';u.join_ui.type=kind;u.join_ui.field=field
            target=u if attr=='draft' else u.join_ui;setattr(target,attr,'')
            await self.type_letters();self.assertEqual(getattr(target,attr),LETTERS)
        u.channel_ui.open(self.chat);u.channel_ui.state='scope';await self.type_letters()
        self.assertEqual(u.channel_ui.input,LETTERS)
        u.protocol_ui.open();u.protocol_ui.state='scope';await self.type_letters()
        self.assertEqual(u.protocol_ui.input,LETTERS)
        for state in ('password','repeat','path'):
            u.screen='backup';u.backup_ui.state=state;u.backup_ui.input=''
            await self.type_letters();self.assertEqual(u.backup_ui.input,LETTERS,state)
        u.screen='identity';u.identity_ui.state='input';u.identity_ui.input=''
        await self.type_letters();self.assertEqual(u.identity_ui.input,'fcFC')
        u.identity_ui.state='file';u.identity_ui.input='';await self.type_letters()
        self.assertEqual(u.identity_ui.input,LETTERS)
        u.screen='repeater';u.repeater_state='password';await self.type_letters()
        self.assertEqual(u.repeater_password,LETTERS)
        u.screen='update';u.update_state='password';await self.type_letters()
        self.assertEqual(u.password,LETTERS)
        u.screen='map_position';u.map_ui.input='12';await self.type_letters()
        self.assertEqual(u.map_ui.input,'12');self.assertEqual(u.screen,'map_position')

    async def test_confirmations_override_hidden_text_focus_without_executing_actions(self):
        u=self.ui;u.screen='chat';u.draft='keep'
        u.leave_target=dict(self.chat);u.leave_choice=1
        await u.key('c');self.assertEqual(u.leave_choice,0)
        await u.key('z');self.assertEqual(u.leave_choice,1)
        await u.key('escape');self.assertIsNone(u.leave_target);self.assertEqual(u.draft,'keep')
        u.experimental_entry=catalog(self.store)['US_SOCAL'];u.experimental_choice=0
        await u.key('x');self.assertEqual(u.experimental_choice,1)
        await u.key('f');self.assertEqual(u.experimental_choice,0)
        await u.key('escape');self.assertIsNone(u.experimental_entry)
        u.startup_release=('99.0.0',);u.startup_update_choice=0
        await u.key('c');self.assertEqual(u.startup_update_choice,1)
        await u.key('escape');self.assertIsNone(u.startup_release)
        u.screen='gps_sharing';u.map_ui.share_choice=1
        await u.key('z');self.assertEqual(u.map_ui.share_choice,0)
        await u.key('escape');self.assertEqual(self.store.get('gps_broadcast','off'),'off')
        for screen,child,state in (('identity',u.identity_ui,'export_confirm'),('backup',u.backup_ui,'confirm'),('channel_options',u.channel_ui,'clear')):
            u.screen=screen;child.state=state;child.choice=1
            await u.key('c');self.assertEqual(child.choice,0,screen)
            await u.key('z');self.assertEqual(child.choice,1,screen)
            await u.key('escape')
        u.screen='repeater';u.repeater_state='confirm';u.repeater_choice=0
        await u.key('c');self.assertEqual(u.repeater_choice,1)
        await u.key('z');self.assertEqual(u.repeater_choice,0)
        self.assertFalse(u.tasks);self.assertFalse(u.pending_restore)

    async def test_unknown_screens_preserve_letter_input_until_focus_is_defined(self):
        self.ui.screen='future_text_form';await self.type_letters()
        self.assertEqual(self.ui.draft,LETTERS)
