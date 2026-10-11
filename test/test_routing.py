"""Deterministic routing rules; the pinned-image fixture separately tests Router."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

stub=types.ModuleType('litellm.integrations.custom_logger')
stub.CustomLogger=type('CustomLogger',(),{})
spec=importlib.util.spec_from_file_location('routing_context',Path(__file__).parents[1]/'gateway/routing_context.py')
routing=importlib.util.module_from_spec(spec)
with patch.dict(sys.modules,{'litellm.integrations.custom_logger':stub}):
    spec.loader.exec_module(routing)


class RoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_task_identity_stable_for_tools_not_new_user_turn(self):
        messages=[{'role':'user','content':'hello'}]
        tool=messages+[{'role':'assistant','content':'calling tool'},{'role':'tool','content':'result'}]
        self.assertEqual(routing.task_identity(messages),routing.task_identity(tool))
        self.assertNotEqual(routing.task_identity(messages),routing.task_identity(tool+[{'role':'user','content':'next'}]))

    async def test_media_and_schema_require_compatible_fallbacks(self):
        for kind in ('file','input_audio','video_url','image_url'):
            with self.subTest(kind=kind):
                data={'model':'asia-auto','messages':[{'role':'user','content':[{'type':kind}]}],
                      'metadata':{'audit':'preserved'}}
                result=await routing.guard.async_pre_call_hook(None,None,data,None)
                self.assertEqual(result['fallbacks'],routing.VISION_FALLBACKS)
                self.assertEqual(result['metadata']['audit'],'preserved')
                self.assertEqual(result['model'],'asia-auto' if kind=='image_url' else 'gemini-3.1-flash-lite')
        result=await routing.guard.async_pre_call_hook(None,None,{
            'model':'asia-auto','messages':[{'role':'user','content':'json'}],
            'response_format':{'type':'json_schema'},
        },None)
        self.assertEqual(result['model'],'gemini-3.1-flash-lite')
        self.assertEqual(result['fallbacks'],routing.VISION_FALLBACKS)

    async def test_text_only_explicit_model_preserved(self):
        data={'model':'asia-pro','messages':[{'role':'user','content':'hello'}]}
        result=await routing.guard.async_pre_call_hook(None,None,data,None)
        self.assertEqual(result,data)
        self.assertNotIn('fallbacks',result)

    async def test_mime_wrapped_media(self):
        for mime in ('audio/wav','video/mp4','application/pdf'):
            self.assertTrue(routing.requires_gemini([{'content':[{'type':'image_url','image_url':{'url':'data:'+mime+';base64,AA=='}}]}]))


if __name__=='__main__':
    unittest.main()
