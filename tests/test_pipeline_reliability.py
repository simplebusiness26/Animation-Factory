"""Regression tests for launch, routing, staging and controller failure paths.

All Kaggle operations/model inference are replaced at their boundaries. No test
submits a notebook, calls an image API, downloads weights or changes real state.
"""
from __future__ import annotations
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'automation')]
from pipeline import image_router as router
from pipeline import kaggle_packaging as packaging
from pipeline import production_guard as guard
import worker
import worker_v2
import episode001_orchestrator as base
import episode001_orchestrator_v2 as v2
import episode001_orchestrator_v3 as v3
import episode001_orchestrator_v4 as v4
import episode001_orchestrator_v5 as v5
import episode001_orchestrator_v6 as v6

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

runner = module('image_runner', 'kernels/reference-still-runner/main.py')
bootstrap = module('image_bootstrap', 'kernels/reference-still-runner/bootstrap.py')
EPISODE = ROOT / packaging.EPISODE
JOB = router.load_json(EPISODE / 'episode001-image-job.json')
CONFIG = router.load_json(router.CONFIG)
MANIFEST = router.load_json(ROOT / JOB['continuity_manifest'])

class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for path in packaging.image_inputs(ROOT):
            dest = self.root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / path, dest)
        self.production = self.root / packaging.EPISODE / 'production.json'
        shutil.copy2(EPISODE / 'production.json', self.production)
        self.job = copy.deepcopy(JOB)
        self.config = copy.deepcopy(CONFIG)
        self.write_state({'phase': 'awaiting_stills', 'paused_by_user': False})
        self.stdout = contextlib.redirect_stdout(io.StringIO())
        self.stdout.__enter__()
        self.addCleanup(self.stdout.__exit__, None, None, None)

    def write_state(self, state):
        (self.root / guard.STATE_PATH).parent.mkdir(parents=True, exist_ok=True)
        (self.root / guard.STATE_PATH).write_text(json.dumps(state))

    def image(self, name='imported.png', size=(256, 144)):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        pixels = np.zeros((size[1], size[0], 3), dtype=np.uint8)
        pixels[:, :, 0] = np.arange(size[0], dtype=np.uint8)
        Image.fromarray(pixels).save(path)
        return path

class RoutingTests(Fixture):
    def test_shot001_replacement_generates_only_that_shot_and_reuses_approved_stills(self):
        plan = router.plan_job(self.job, self.config, root=self.root)
        self.assertEqual(plan['status'], 'ready')
        self.assertEqual(len(plan['shots']), len(base.SHOTS))
        generated = [x for x in plan['shots'] if not x.get('reused_approved_input')]
        reused = [x for x in plan['shots'] if x.get('reused_approved_input')]
        self.assertEqual([x['id'] for x in generated], ['001'])
        self.assertEqual(len(reused), len(base.SHOTS) - 1)
        self.assertEqual(sum(x['reference_count'] for x in generated), 4)

    def test_missing_character_reference_blocks_batch(self):
        (self.root / MANIFEST['canonical_cast']['zig']['reference']).unlink()
        self.assertEqual(router.plan_job(self.job, self.config, root=self.root)['status'], 'blocked')

    def test_wrong_reference_hash_blocks_batch(self):
        path = self.root / self.job['continuity_manifest']
        manifest = copy.deepcopy(MANIFEST)
        manifest['canonical_cast']['zig']['decoded_sha256'] = '0' * 64
        path.write_text(json.dumps(manifest))
        self.assertEqual(router.plan_job(self.job, self.config, root=self.root)['status'], 'blocked')

    def test_unknown_character_does_not_generate_text_only(self):
        self.job['shots'][0]['characters'] = ['unlocked-new-character']
        self.assertEqual(router.plan_job(self.job, self.config, root=self.root)['status'], 'blocked')

    def test_hero_route_is_honoured_inside_batch(self):
        self.job['shots'][0]['purpose'] = 'hero'
        plan = router.plan_job(self.job, self.config, root=self.root)
        self.assertEqual(plan['shots'][0]['status'], 'awaiting_approved_chatgpt_image')
        self.assertEqual(plan['status'], 'blocked')

    def test_import_needs_file_hash_and_approval(self):
        shot = {'purpose': 'hero', 'approved_input_path': 'missing.png', 'qa_status': 'approved', 'approved_input_sha256': '0' * 64}
        self.assertEqual(router.choose_route(shot, self.config, root=self.root)['status'], 'blocked_invalid_import')
        path = self.image()
        shot['approved_input_path'] = path.name
        self.assertEqual(router.choose_route(shot, self.config, root=self.root)['status'], 'blocked_invalid_import')
        shot['approved_input_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        shot['qa_status'] = 'pending'
        self.assertEqual(router.choose_route(shot, self.config, root=self.root)['status'], 'awaiting_import_approval')
        shot['qa_status'] = 'approved'
        self.assertEqual(router.choose_route(shot, self.config, root=self.root)['status'], 'ready')

    def test_duplicate_empty_and_path_traversal_shots_rejected(self):
        for replacement in ([], [self.job['shots'][0]] * 2, [{**self.job['shots'][0], 'id': '../outside'}]):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                router.plan_job({**self.job, 'shots': replacement}, self.config, root=self.root)

    def test_invalid_dimensions_and_nonfinite_guidance_rejected(self):
        for fields in ({'width': 1025}, {'height': -1}, {'steps': 0}, {'guidance_scale': float('nan')}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                router.plan_job({**self.job, **fields}, self.config, root=self.root)

    def test_legacy_fallback_not_silently_run_as_flux(self):
        self.job['shots'][0]['route'] = router.SDXL_ROUTE
        plan = router.plan_job(self.job, self.config, root=self.root)
        self.assertEqual(plan['shots'][0]['status'], 'blocked_unsupported_route')

    def test_asset_escape_rejected(self):
        with self.assertRaises(ValueError):
            router.asset_path(self.root, '../other-project.png')

    def test_missing_character_declaration_fails_closed(self):
        del self.job['shots'][0]['characters']
        with self.assertRaisesRegex(ValueError, 'declare characters'):
            router.plan_job(self.job, self.config, root=self.root)


class LaunchTests(Fixture):
    def test_missing_or_corrupt_state_fails_closed(self):
        path = self.root / guard.STATE_PATH
        for value in ('broken json', '[]', '{}'):
            path.write_text(value)
            with self.assertRaises(RuntimeError):
                guard.require_launch_allowed(self.root)
        path.unlink()
        with self.assertRaises(RuntimeError):
            guard.require_launch_allowed(self.root)

    def test_paused_generic_new_runner_is_blocked_before_push(self):
        self.write_state({'phase': 'paused_by_user', 'paused_by_user': True})
        folder = ROOT / 'kernels/reference-still-runner'
        before = (folder / 'kernel-metadata.json').read_bytes()
        with patch.object(worker_v2, 'ROOT', self.root), patch.object(worker, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'paused'):
                worker_v2.execute({'action': 'run_kernel', 'path': 'kernels/reference-still-runner', 'request_id': 'image-review', 'owner': 'test'})
            run.assert_not_called()
        self.assertEqual((folder / 'kernel-metadata.json').read_bytes(), before)

    def test_paused_run_shot_cannot_bypass_worker_gate(self):
        self.write_state({'phase': 'paused_by_user'})
        job_path = self.root / 'single.json'
        job_path.write_text(json.dumps({'episode': '001'}))
        with patch.object(worker_v2, 'ROOT', self.root), patch.object(worker, 'safe_repo_file', return_value=job_path), patch.object(worker, 'execute') as execute:
            with self.assertRaisesRegex(RuntimeError, 'paused'):
                worker_v2.execute({'action': 'run_shot', 'job_path': 'shows/a/shot.json'})
            execute.assert_not_called()

    def test_read_only_status_remains_available(self):
        with patch.object(worker, 'execute', return_value=('status', [])) as execute:
            self.assertEqual(worker_v2.execute({'action': 'kernel_status'}), ('status', []))
            execute.assert_called_once()

    def test_zero_exit_push_quota_error_is_failure(self):
        response = types.SimpleNamespace(returncode=0, stdout='Kernel push error: Maximum weekly GPU quota reached')
        with patch.object(worker.subprocess, 'run', return_value=response):
            with self.assertRaisesRegex(RuntimeError, 'quota'):
                worker.run(['kaggle', 'kernels', 'push', '-p', '/tmp/prepared'])

    def test_bootstrap_reports_network_or_pause_failure_without_starting_runner(self):
        with patch.object(bootstrap, 'WORK', self.root), patch.object(bootstrap, 'SOURCE_REF', 'a' * 40), patch.object(bootstrap, 'INPUT_PATHS', ['some/input']), patch.object(bootstrap.urllib.request, 'urlopen', side_effect=OSError('offline')), patch.object(bootstrap.subprocess, 'run') as run:
            self.assertEqual(bootstrap.main(), 2)
            run.assert_not_called()
            self.assertFalse(router.load_json(self.root / 'animation-factory-image-report.json')['success'])

class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.stdout = contextlib.redirect_stdout(io.StringIO())
        self.stdout.__enter__()
        self.addCleanup(self.stdout.__exit__, None, None, None)

    def test_all_supported_controller_entrypoints_preserve_pause_and_do_no_work(self):
        state = {'phase': 'paused_by_user', 'paused_by_user': True, 'force_stills_retry': True, 'continuity_gate': 'rejected'}
        for entry in (base.main, v2.main, v3.run_controller, v4.main, v6.main):
            with self.subTest(entry=entry.__module__), patch.object(base, 'load_state', return_value=copy.deepcopy(state)), patch.object(base, 'save_state') as save, patch.object(base, 'run') as run:
                self.assertEqual(entry(), 0)
                run.assert_not_called()
                save.assert_not_called()

    def test_missing_v2_entrypoint_regression_dispatches_waiting_phase(self):
        state = {'phase': 'awaiting_stills'}
        with patch.object(base, 'load_state', return_value=state), patch.object(base, 'save_state'), patch.object(v2, 'handle_stills') as handle:
            self.assertEqual(v2.main(), 0)
            handle.assert_called_once_with(state)

    def test_retry_selects_configured_hybrid_runner(self):
        state = {'stills_attempts': 0}
        with patch.object(v2, 'push_fresh', return_value=('owner/new', 'accepted')) as push, patch.object(base, 'log'):
            v6._ORIGINAL_RETRY_STILLS(state, 'review regression')
        self.assertEqual(push.call_args.args[0], ROOT / 'kernels/reference-still-runner')
        self.assertEqual(state['stills_attempts'], 1)

    def test_confirmed_repair_retry_bypasses_stale_private_status_once(self):
        state = {'phase': 'blocked_continuity', 'force_repaired_stills_retry': True}
        with patch.object(v2, 'safe_status', return_value='STATUS_ERROR') as status, patch.object(v6, '_ORIGINAL_RETRY_STILLS') as submit:
            v6.safe_retry_stills(state, 'confirmed Pillow repair')
            submit.assert_called_once_with(state, 'confirmed Pillow repair')
            status.assert_not_called()
        self.assertNotIn('force_repaired_stills_retry', state)

    def test_running_and_unknown_status_never_submit_replacement(self):
        for status in ('RUNNING', 'API_STATUS_CHANGED', 'STATUS_ERROR'):
            state = {'phase': 'awaiting_stills'}
            with self.subTest(status=status), patch.object(v2, 'safe_status', return_value=status), patch.object(v6, '_ORIGINAL_RETRY_STILLS') as submit:
                v6.safe_retry_stills(state, 'retry')
                submit.assert_not_called()

    def test_private_status_uses_downloaded_terminal_report(self):
        with patch.object(base, 'status_of', side_effect=RuntimeError('403 Forbidden')), patch.object(v2, 'downloadable_output_status', return_value='COMPLETE'):
            self.assertEqual(v2.safe_status('owner/kernel'), 'COMPLETE')

    def test_single_status_sample_per_poll(self):
        state = {'phase': 'awaiting_stills'}
        with patch.object(v2, 'safe_status', return_value='RUNNING') as status, patch.object(v2, 'retry_stills') as retry:
            v6.hardened_handle_stills(state)
            self.assertEqual(status.call_count, 1)
            retry.assert_not_called()

    def test_approval_transition_uses_guarded_motion_submission(self):
        state = {'phase': 'awaiting_continuity_review'}
        with patch.object(base, 'load_state', return_value=state), patch.object(base, 'save_state'), patch.object(v3, 'continuity_preflight', return_value=(True, 'ok')), patch.object(v3, 'continuity_review_approved', return_value=(True, 'ok')), patch.object(v2, 'retry_motion') as retry:
            self.assertEqual(v3.run_controller(), 0)
            retry.assert_called_once()

    def test_final_review_does_not_restart_generation(self):
        state = {'phase': 'awaiting_final_review', 'final_file': 'dist/missing-final.mp4'}
        with patch.object(base, 'load_state', return_value=state), patch.object(base, 'save_state'), patch.object(v2, 'handle_stills') as stills, patch.object(v2, 'handle_motion') as motion:
            self.assertEqual(v2.main(), 0)
            self.assertEqual(state['phase'], 'awaiting_final_review')
            stills.assert_not_called()
            motion.assert_not_called()

    def test_same_failed_notebook_is_not_counted_twice(self):
        state = {'stills_last_failed_kernel': 'owner/one', 'stills_failure_repeats': 1}
        with patch.object(v6, '_diagnostic_signature') as diagnostic:
            self.assertFalse(v6._handle_error_with_repair_gate(state, 'stills', 'owner/one'))
            diagnostic.assert_not_called()
            self.assertEqual(state['stills_failure_repeats'], 1)

class RunnerTests(Fixture):
    def run_image_job(self, *, pixels=None, loader=None):
        (self.root / packaging.EPISODE / 'episode001-image-job.json').write_text(json.dumps(self.job))
        self.work = self.root / 'output'
        self.work.mkdir(exist_ok=True)
        torch = types.SimpleNamespace(cuda=types.SimpleNamespace(get_device_name=lambda _: 'test-boundary'), Generator=lambda **kw: types.SimpleNamespace(manual_seed=lambda seed: seed))
        if pixels is None:
            pixels = np.linspace(0, 1, self.job['width'] * self.job['height'] * 3).reshape(self.job['height'], self.job['width'], 3)
        pipe = Mock(return_value=types.SimpleNamespace(images=[pixels]))
        with patch.object(runner, 'SOURCE_ROOT', self.root), patch.object(runner, 'WORK', self.work), patch.object(runner, 'JOB', self.root / packaging.EPISODE / 'episode001-image-job.json'), patch.object(runner, 'REPORT', self.work / 'animation-factory-image-report.json'), patch.object(runner, 'install_runtime'), patch.object(runner, 'load_pipeline', loader or Mock(return_value=(pipe, torch, 'test'))), contextlib.redirect_stderr(io.StringIO()):
            code = runner.main()
        return code, router.load_json(self.work / 'animation-factory-image-report.json'), pipe

    def test_success_records_all_files_hashes_and_pending_qa(self):
        self.job['shots'] = self.job['shots'][:2]
        for key in ('approved_input_path', 'approved_input_sha256', 'qa_status'):
            self.job['shots'][1].pop(key, None)
        code, report, pipe = self.run_image_job()
        self.assertEqual(code, 0)
        self.assertTrue(report['success'])
        self.assertEqual(pipe.call_count, 2)
        self.assertEqual([len(call.kwargs['image']) for call in pipe.call_args_list], [4, 4])
        for row in report['shots']:
            self.assertEqual(row['qa_status'], 'pending')
            self.assertEqual(row['sha256'], hashlib.sha256((self.work / row['file']).read_bytes()).hexdigest())

    def test_bad_generated_shot_reference_prevents_entire_gpu_load(self):
        self.job['shots'][0]['characters'] = ['not-locked']
        load = Mock()
        code, report, _ = self.run_image_job(loader=load)
        self.assertEqual(code, 2)
        load.assert_not_called()
        self.assertFalse(report['success'])

    def test_blank_or_nonfinite_pixels_are_failure(self):
        self.job['shots'] = self.job['shots'][:1]
        for fill in (0.0, float('nan')):
            pixels = np.full((self.job['height'], self.job['width'], 3), fill)
            code, report, _ = self.run_image_job(pixels=pixels)
            self.assertEqual(code, 3)
            self.assertFalse(report['shots'][0]['success'])

    def test_approved_import_never_loads_model(self):
        path = self.image()
        self.job['shots'] = [{**self.job['shots'][0], 'purpose': 'hero', 'approved_input_path': path.name,
                              'approved_input_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'qa_status': 'approved'}]
        load = Mock(side_effect=AssertionError('GPU must not load'))
        code, report, _ = self.run_image_job(loader=load)
        self.assertEqual(code, 0)
        load.assert_not_called()
        self.assertTrue(report['shots'][0]['reused_approved_input'])

class StagingTests(Fixture):
    def test_bad_batch_cannot_archive_or_replace_current_images(self):
        output = self.root / 'download'
        output.mkdir()
        (output / 'animation-factory-image-report.json').write_text(json.dumps({'success': True, 'shots': []}))
        with patch.object(v4, 'archive_current_stills') as archive, patch.object(v4, '_ORIGINAL_STAGE') as stage:
            with self.assertRaises(RuntimeError):
                v4.stage_with_archive(output)
            archive.assert_not_called()
            stage.assert_not_called()

    def test_staging_replaces_legacy_shot001_and_invalidates_prior_batch_qa(self):
        output = self.root / 'download'
        output.mkdir()
        rows = []
        for shot in base.SHOTS:
            name = f"earth-needs-help-e001-s{shot['id']}.png"
            path = self.image('download/' + name)
            rows.append({'id': shot['id'], 'file': name, 'success': True, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        (output / 'animation-factory-image-report.json').write_text(json.dumps({'success': True, 'shots': rows}))
        current = self.root / 'stills'
        current.mkdir()
        legacy = self.image('stills/earth-needs-help-e001-s001.png')
        before = legacy.read_bytes()
        with patch.object(v3, 'continuity_preflight', return_value=(True, 'ok')), patch.object(base, 'STILLS_DIR', current), patch.object(v3, 'reset_continuity_review') as reset:
            staged = v3.robust_stage_generated_stills(output)
            self.assertEqual(len(staged), len(base.SHOTS))
            reset.assert_called_once()
        self.assertNotEqual(legacy.read_bytes(), before)

class SnapshotTests(Fixture):
    def commit_fixture(self):
        for args in (['git', 'init', '-q'], ['git', 'add', '.'], ['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test', 'commit', '-qm', 'fixture']):
            subprocess.run(args, cwd=self.root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_prepared_bootstrap_pins_snapshot_and_downloads_only_that_version(self):
        self.commit_fixture()
        target = self.root / 'prepared.py'
        packaging.prepare_image_bootstrap(self.root, target)
        code = target.read_text()
        self.assertNotIn('__SOURCE_COMMIT__', code)
        self.assertNotIn('__IMAGE_JOB_PATH__', code)
        compile(code, str(target), 'exec')
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=self.root, text=True).strip()
        self.assertIn(revision, code)
        path = self.root / JOB['continuity_manifest']
        path.write_text(path.read_text() + '\n')
        with self.assertRaisesRegex(RuntimeError, 'Commit'):
            packaging.prepare_image_bootstrap(self.root, target)

    def test_bootstrap_downloads_pinned_inputs_and_keeps_live_pause_separate(self):
        self.commit_fixture()
        target = self.root / 'prepared.py'
        packaging.prepare_image_bootstrap(self.root, target)
        scope = {'__name__': 'prepared_test'}
        exec(compile(target.read_text(), str(target), 'exec'), scope)
        work = self.root / 'kaggle'
        scope['WORK'] = work
        seen = []
        def fetch_url(url, **kwargs):
            seen.append(url)
            if '/main/automation/episode001-state.json' in url:
                return io.BytesIO(json.dumps({'phase': 'awaiting_stills'}).encode())
            prefix = scope['PUBLIC_ROOT'] + '/' + scope['SOURCE_REF'] + '/'
            self.assertTrue(url.startswith(prefix), url)
            return io.BytesIO((self.root / url[len(prefix):]).read_bytes())
        def run_command(args, **kwargs):
            source = Path(kwargs['env']['ANIMATION_SOURCE_ROOT'])
            plan = router.plan_job(router.load_json(source / kwargs['env']['ANIMATION_IMAGE_JOB']), router.load_json(source / 'pipeline/image-generation.json'), root=source)
            self.assertEqual(plan['status'], 'ready')
            self.assertEqual(guard.load_state(source)['phase'], 'awaiting_stills')
            self.assertTrue(Path(args[1]).is_file())
            return types.SimpleNamespace(returncode=0)
        with patch.object(bootstrap.urllib.request, 'urlopen', side_effect=fetch_url), patch.object(bootstrap.subprocess, 'run', side_effect=run_command):
            self.assertEqual(scope['main'](), 0)
        self.assertEqual(sum('/main/' in url for url in seen), 1)

    def test_motion_snapshot_refuses_unapproved_batch(self):
        shutil.copy2(EPISODE / 'continuity-qa.json', self.root / packaging.EPISODE / 'continuity-qa.json')
        shutil.copy2(EPISODE / 'episode001-motion-job.json', self.root / packaging.EPISODE / 'episode001-motion-job.json')
        with self.assertRaisesRegex(RuntimeError, 'continuity review'):
            packaging.prepare_motion_bootstrap(self.root, self.root / 'motion.py')

class PinnedModelStackTests(unittest.TestCase):
    """diffusers 0.40.0 requires safetensors>=0.8.0 and huggingface-hub>=1.23,<2;
    transformers<5 pins huggingface-hub<1.0. Pinning transformers==4.x or
    safetensors==0.7.0 alongside diffusers==0.40.0 is not pip-installable at all
    (verified: pip's resolver rejects it), and this is exactly what broke the
    2026-09-07 FLUX2 smoke test kernel on Kaggle."""

    def _pins(self, text: str) -> dict:
        import re
        return dict(re.findall(r"([a-zA-Z0-9_-]+)==([0-9][0-9.]*[0-9])", text))

    def test_still_runner_requirements_are_pip_installable_together(self):
        pins = self._pins((ROOT / 'kernels/reference-still-runner/requirements.txt').read_text())
        self.assertGreaterEqual(tuple(map(int, pins['safetensors'].split('.'))), (0, 8, 0))
        self.assertGreaterEqual(int(pins['transformers'].split('.')[0]), 5)

    def test_still_runner_installs_before_reference_preflight(self):
        source = (ROOT / 'kernels/reference-still-runner/main.py').read_text()
        main_body = source.split('def main() -> int:', 1)[1]
        self.assertLess(main_body.index('install_runtime()'), main_body.index('plan = plan_job('))
        load_body = source.split('def load_pipeline(', 1)[1].split('def main()', 1)[0]
        self.assertNotIn('install_runtime()', load_body)

    def test_smoke_test_requirements_are_pip_installable_together(self):
        pins = self._pins((ROOT / 'kernels/flux2-smoke-test/main.py').read_text())
        self.assertGreaterEqual(tuple(map(int, pins['safetensors'].split('.'))), (0, 8, 0))
        self.assertGreaterEqual(int(pins['transformers'].split('.')[0]), 5)

    def test_smoke_test_and_still_runner_share_the_same_model_stack_pins(self):
        requirements = self._pins((ROOT / 'kernels/reference-still-runner/requirements.txt').read_text())
        smoke = self._pins((ROOT / 'kernels/flux2-smoke-test/main.py').read_text())
        shared = requirements.keys() & smoke.keys()
        self.assertTrue(shared)
        for name in shared:
            self.assertEqual(requirements[name], smoke[name], name)


class ReleaseTests(unittest.TestCase):
    def test_technical_pass_alone_cannot_publish_video(self):
        from pipeline.release_gate import verify_release
        with tempfile.TemporaryDirectory() as td:
            video = Path(td) / 'episode-final.mp4'
            video.write_bytes(b'example-video-for-hash-test')
            qa = video.with_name(video.stem + '-qa.json')
            report = {'technical_pass': True, 'sha256': hashlib.sha256(video.read_bytes()).hexdigest()}
            qa.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, 'review'):
                verify_release(video)
            report.update(visual_review='approved', audio_review='approved')
            qa.write_text(json.dumps(report))
            verify_release(video)
            video.write_bytes(b'changed-video')
            with self.assertRaisesRegex(ValueError, 'match'):
                verify_release(video)


if __name__ == '__main__':
    unittest.main()
