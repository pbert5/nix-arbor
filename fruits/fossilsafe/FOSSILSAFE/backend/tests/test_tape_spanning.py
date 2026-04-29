import os
import tempfile
import unittest

from backend.services.job_service import JobService
from backend.tape_spanning import TapeSpanningManager, _build_local_api_base_url


class _FakeDb:
    def __init__(self, available_tapes):
        self._available_tapes = available_tapes

    def get_available_tapes(self):
        return list(self._available_tapes)


class _FakeSourceManager:
    def get_source(self, source_id, include_password=True):
        return None


class _FakeSmbClient:
    def __init__(self, total_size):
        self.total_size = total_size

    def scan_directory(self, share_path, username, password, domain=None, scan_mode=None, max_files=None):
        return {
            'file_count': 1,
            'total_size': self.total_size,
            'duration_ms': 1,
            'sample_paths': ['exact-fit.bin'],
            'method': 'find',
            'dir_count': 1,
            'warnings': [],
            'partial': False,
            'scan_mode': scan_mode or 'quick',
        }


class TapeSpanningManagerTests(unittest.TestCase):
    def test_build_local_api_base_url_uses_runtime_backend_port(self):
        previous_bind = os.environ.get('FOSSILSAFE_BACKEND_BIND')
        previous_port = os.environ.get('FOSSILSAFE_BACKEND_PORT')
        try:
            os.environ['FOSSILSAFE_BACKEND_BIND'] = '0.0.0.0'
            os.environ['FOSSILSAFE_BACKEND_PORT'] = '5001'

            self.assertEqual(_build_local_api_base_url(), 'http://127.0.0.1:5001')
        finally:
            if previous_bind is None:
                os.environ.pop('FOSSILSAFE_BACKEND_BIND', None)
            else:
                os.environ['FOSSILSAFE_BACKEND_BIND'] = previous_bind

            if previous_port is None:
                os.environ.pop('FOSSILSAFE_BACKEND_PORT', None)
            else:
                os.environ['FOSSILSAFE_BACKEND_PORT'] = previous_port

    def test_tape_change_script_targets_runtime_api_url(self):
        manager = TapeSpanningManager(tape_controller=None, api_base_url='http://127.0.0.1:5001')

        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = os.path.join(tmpdir, 'tape-change.sh')
            manager._create_tape_change_script(script_path, 42)

            with open(script_path, 'r', encoding='utf-8') as handle:
                script = handle.read()

        self.assertIn('http://127.0.0.1:5001/api/spanning/42/request-change', script)
        self.assertIn('http://127.0.0.1:5001/api/spanning/42/status', script)
        self.assertNotIn('http://localhost:5000', script)


class JobServiceDryRunEstimateTests(unittest.TestCase):
    def test_dry_run_exact_native_capacity_uses_single_tape(self):
        lto5_capacity = int(1.5 * 1024**4)
        service = JobService(
            db=_FakeDb([
                {
                    'barcode': '000001L5',
                    'generation': 'LTO-5',
                    'capacity_bytes': lto5_capacity,
                }
            ]),
            backup_engine=None,
            scheduler=None,
            preflight_checker=None,
            tape_controller=None,
            source_manager=_FakeSourceManager(),
            smb_client=_FakeSmbClient(lto5_capacity),
        )

        ok, result = service.dry_run(
            {
                'source_path': '//server/share',
                'username': 'user',
                'password': 'pass',
            }
        )

        self.assertTrue(ok)
        self.assertEqual(result['estimates']['detected_generation'], 'LTO-5')
        self.assertEqual(result['estimates']['tapes_needed_native'], 1)
        self.assertEqual(result['estimates']['tapes_needed_compressed'], 1)


if __name__ == '__main__':
    unittest.main()