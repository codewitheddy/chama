import io
import zipfile
import tempfile
import os
import shutil
from pathlib import Path

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.management import call_command

from accounts.models import UserProfile
from backup.models import BackupSetting, BackupLog
from backup.services import (
    build_backup_zip, validate_backup_directory,
    create_backup_file, prune_old_backups, list_local_backups,
    delete_local_backup, check_and_run_background_backup
)


class BackupAndRestoreTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username='test_backup_admin',
            password='Password123!',
            email='admin@test.com',
        )
        UserProfile.objects.get_or_create(user=self.admin_user, defaults={'role': 'admin'})
        self.client.force_login(self.admin_user)
        self.test_dir = tempfile.mkdtemp(prefix='test_bkp_')

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_build_backup_zip_contains_manifest(self):
        buf = build_backup_zip(include_media=True)
        self.assertIsInstance(buf, io.BytesIO)
        with zipfile.ZipFile(buf, 'r') as zf:
            namelist = zf.namelist()
            self.assertIn('MANIFEST.txt', namelist)
            self.assertTrue('db.sqlite3' in namelist or 'data.json' in namelist)

    def test_validate_backup_directory(self):
        valid, msg, norm_path = validate_backup_directory(self.test_dir)
        self.assertTrue(valid)
        self.assertEqual(norm_path, str(Path(self.test_dir).resolve()))

        # Empty path
        valid_empty, msg_empty, _ = validate_backup_directory('')
        self.assertFalse(valid_empty)

    def test_create_backup_file_and_logs(self):
        target_dir = Path(self.test_dir)
        success, msg, file_path = create_backup_file(trigger='scheduled', custom_dir=target_dir)
        self.assertTrue(success)
        self.assertIsNotNone(file_path)
        self.assertTrue(file_path.exists())
        self.assertTrue(file_path.name.startswith('backup_sched_'))

        # Check setting updated
        setting = BackupSetting.get_settings()
        self.assertEqual(setting.last_backup_status, 'success')
        self.assertEqual(setting.last_backup_trigger, 'scheduled')

        # Check log created
        log = BackupLog.objects.filter(file_name=file_path.name).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, 'success')
        self.assertEqual(log.trigger_type, 'scheduled')

    def test_prune_old_backups(self):
        target_dir = Path(self.test_dir)
        # Create 5 dummy backup files
        for i in range(5):
            f = target_dir / f"backup_manual_20260927_07000{i}.zip"
            f.write_text("test_data")

        # Prune to retention of 2
        pruned = prune_old_backups(target_dir, retention_limit=2)
        self.assertEqual(pruned, 3)
        remaining = list(target_dir.glob('*.zip'))
        self.assertEqual(len(remaining), 2)

    def test_list_local_backups(self):
        target_dir = Path(self.test_dir)
        f1 = target_dir / "backup_auto_20260927_071000.zip"
        f1.write_text("auto_backup_data")
        f2 = target_dir / "backup_sched_20260927_072000.zip"
        f2.write_text("sched_backup_data")

        backups = list_local_backups(target_dir)
        self.assertEqual(len(backups), 2)
        triggers = [b['trigger'] for b in backups]
        self.assertIn('automatic', triggers)
        self.assertIn('scheduled', triggers)

    def test_delete_local_backup(self):
        target_dir = Path(self.test_dir)
        f1 = target_dir / "backup_to_delete.zip"
        f1.write_text("delete_me")

        success, msg = delete_local_backup("backup_to_delete.zip", target_dir)
        self.assertTrue(success)
        self.assertFalse(f1.exists())

    def test_backup_view_get(self):
        url = reverse('backup:backup')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Backup &amp; Restore Settings')
        self.assertContains(response, 'Automatic (System Decides)')
        self.assertContains(response, 'Scheduled (Custom)')

    def test_backup_save_settings_scheduled(self):
        url = reverse('backup:backup')
        response = self.client.post(url, {
            'action': 'save_settings',
            'mode': 'scheduled',
            'custom_location': self.test_dir,
            'schedule_interval_hours': '12',
            'retention_count': '20',
            'include_media': 'on',
        })
        self.assertEqual(response.status_code, 302)

        setting = BackupSetting.get_settings()
        self.assertEqual(setting.mode, 'scheduled')
        self.assertEqual(setting.schedule_interval_hours, 12)
        self.assertEqual(setting.retention_count, 20)
        self.assertTrue(setting.include_media)

    def test_backup_save_settings_automatic(self):
        url = reverse('backup:backup')
        response = self.client.post(url, {
            'action': 'save_settings',
            'mode': 'automatic',
            'retention_count': '15',
        })
        self.assertEqual(response.status_code, 302)
        setting = BackupSetting.get_settings()
        self.assertEqual(setting.mode, 'automatic')

    def test_backup_create_local_post(self):
        url = reverse('backup:backup')
        response = self.client.post(url, {'action': 'create_local'})
        self.assertEqual(response.status_code, 302)
        setting = BackupSetting.get_settings()
        self.assertEqual(setting.last_backup_status, 'success')

    def test_backup_download_local_view(self):
        setting = BackupSetting.get_settings()
        target_dir = Path(self.test_dir)
        setting.mode = 'scheduled'
        setting.custom_location = str(target_dir)
        setting.save()

        dummy_file = target_dir / "backup_test_dl.zip"
        dummy_file.write_text("zip content")

        url = reverse('backup:download_local', kwargs={'filename': 'backup_test_dl.zip'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')

    def test_validate_directory_api(self):
        url = reverse('backup:validate_directory')
        response = self.client.post(url, {'path': self.test_dir})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['valid'])

    def test_management_command_run_backup(self):
        out = io.StringIO()
        call_command('run_backup', trigger='manual', dir=self.test_dir, stdout=out)
        self.assertIn('created successfully', out.getvalue())
