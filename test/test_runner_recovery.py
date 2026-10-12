"""A transport outage must never turn a completed command into a retry."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'infra/training'))
import runner


class RunnerRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state=Path(self.directory.name)
        state_patch=patch.object(runner,'STATE',self.state)
        state_patch.start();self.addCleanup(state_patch.stop)
        self.request={'jobId':'a'*32,'agentId':'formation-developpement',
                      'sessionKey':'agent:formation-developpement:recovery','operation':'build'}
        self.receipt={'jobId':self.request['jobId'],'request_sha256':runner.request_digest(self.request),
                      'status':'passed','exitCode':0,'finished_at':123.0}
        self.result_path=self.state/'jobs'/(self.request['jobId']+'.result.json')
        self.marker_path=self.state/'jobs'/(self.request['jobId']+'.started.json')

    def test_unpublished_success_is_republished_exactly_without_any_command(self):
        with patch.object(runner,'remote_write',side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError):runner.publish_result(self.request,self.receipt)
        self.assertEqual(json.loads(self.result_path.read_text()),self.receipt)
        with patch.object(runner,'remote_write') as publish,patch.object(runner.subprocess,'run') as execute:
            self.assertTrue(runner.recover(self.request,True))
        execute.assert_not_called()
        self.assertEqual(json.loads(publish.call_args.args[1]),self.receipt)

    def test_a_receipt_cannot_be_reused_for_another_request(self):
        runner.durable_write(self.result_path,self.receipt)
        changed=dict(self.request,operation='node_tests')
        with patch.object(runner,'remote_write') as publish,patch.object(runner.subprocess,'run') as execute:
            with self.assertRaises(ValueError):runner.recover(changed,True)
        publish.assert_not_called();execute.assert_not_called()

    def test_local_start_without_remote_marker_is_never_replayed(self):
        runner.durable_write(self.marker_path,{'request_sha256':runner.request_digest(self.request)})
        with patch.object(runner,'remote_write'),patch.object(runner,'remove_job',return_value=False):
            self.assertTrue(runner.recover(self.request,False))
        result=json.loads(self.result_path.read_text())
        self.assertEqual(result['status'],'unknown_after_restart')
        self.assertTrue(result['cleanup_unconfirmed'])
        self.assertEqual(result['request_sha256'],runner.request_digest(self.request))

    def test_changed_started_request_and_corrupted_receipt_fail_closed(self):
        runner.durable_write(self.marker_path,{'request_sha256':'different'})
        with patch.object(runner,'remote_write') as publish,patch.object(runner,'remove_job') as remove:
            with self.assertRaises(ValueError):runner.recover(self.request,False)
            self.result_path.write_text('{corrupted')
            with self.assertRaises(ValueError):runner.recover(self.request,True)
        publish.assert_not_called();remove.assert_not_called()

    def test_existing_evidence_cannot_be_overwritten(self):
        runner.durable_write(self.result_path,self.receipt)
        with self.assertRaises(ValueError):
            runner.durable_write(self.result_path,dict(self.receipt,status='failed'))
        self.assertEqual(json.loads(self.result_path.read_text()),self.receipt)

    def test_cleanup_exception_cannot_erase_a_cancelled_receipt(self):
        with patch.object(runner,'remote_write'),patch.object(runner,'node',return_value='true'),\
             patch.object(runner.subprocess,'run',side_effect=OSError('docker unavailable')):
            result=runner.process(self.request)
        self.assertEqual(result['status'],'cancelled')
        self.assertTrue(result['cleanup_unconfirmed'])
        self.assertEqual(json.loads(self.result_path.read_text()),result)

    def test_fault_injection_refuses_an_ordinary_training_gateway(self):
        import test_outage
        journal=self.state/'journal.json'
        with patch.object(test_outage,'STATE',self.state),patch.object(test_outage,'docker') as docker:
            journal.write_text('{"kind":"training","status":"active"}')
            with self.assertRaises(RuntimeError):test_outage.require_fixture()
            docker.assert_not_called()
            journal.write_text('{"kind":"runner-fault-fixture","status":"active"}')
            docker.return_value=b'[{"Config":{"Labels":{}}}]'
            with self.assertRaises(RuntimeError):test_outage.require_fixture()
            self.assertEqual(docker.call_args.args[0],'inspect')


if __name__=='__main__':unittest.main()
