"""Tests pour sync_service."""
import os
import shutil
import tempfile
import pytest
from unittest.mock import patch


# ── Helpers ──────────────────────────────────────────────────────────────────

def _write_file(path: str, content: bytes = b"db_content"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)


# ── Configuration ─────────────────────────────────────────────────────────────

class TestSyncConfig:

    def test_set_and_get_sync_folder(self, tmp_path):
        from services.sync_service import set_sync_folder, get_sync_folder
        with patch("services.sync_service.settings_service") as mock_svc:
            mock_svc.get.return_value = str(tmp_path)
            set_sync_folder(str(tmp_path))
            mock_svc.set.assert_called_once_with("sync_folder", str(tmp_path))

    def test_get_sync_folder_none_when_empty(self):
        from services.sync_service import get_sync_folder
        with patch("services.sync_service.settings_service") as mock_svc:
            mock_svc.get.return_value = ""
            assert get_sync_folder() is None

    def test_set_auto_sync(self):
        from services.sync_service import set_auto_sync
        with patch("services.sync_service.settings_service") as mock_svc:
            set_auto_sync(True)
            mock_svc.set.assert_called_once_with("sync_auto", True)

    def test_is_auto_sync(self):
        from services.sync_service import is_auto_sync
        with patch("services.sync_service.settings_service") as mock_svc:
            mock_svc.get.return_value = True
            assert is_auto_sync() is True
            mock_svc.get.return_value = False
            assert is_auto_sync() is False


# ── get_status ────────────────────────────────────────────────────────────────

class TestGetStatus:

    def test_not_configured(self):
        from services.sync_service import get_status
        with patch("services.sync_service.settings_service") as mock_svc:
            mock_svc.get.return_value = ""
            st = get_status()
        assert st == {"configured": False}

    def test_ahead_when_no_remote(self, tmp_path):
        from services.sync_service import get_status
        db = tmp_path / "local.db"
        db.write_bytes(b"data")
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        with patch("services.sync_service.settings_service") as mock_svc, \
             patch("services.sync_service.DB_PATH", str(db)):
            mock_svc.get.return_value = str(sync_dir)
            st = get_status()
        assert st["configured"] is True
        assert st["ahead"] is True
        assert st["behind"] is False
        assert st["remote_exists"] is False

    def test_behind_when_no_local(self, tmp_path):
        from services.sync_service import get_status, SYNC_FILENAME
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        remote = sync_dir / SYNC_FILENAME
        remote.write_bytes(b"remote")
        fake_db = str(tmp_path / "nonexistent.db")
        with patch("services.sync_service.settings_service") as mock_svc, \
             patch("services.sync_service.DB_PATH", fake_db):
            mock_svc.get.return_value = str(sync_dir)
            st = get_status()
        assert st["behind"] is True
        assert st["ahead"] is False

    def test_up_to_date_same_content(self, tmp_path):
        from services.sync_service import get_status, SYNC_FILENAME
        import time
        db = tmp_path / "local.db"
        db.write_bytes(b"same")
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        remote = sync_dir / SYNC_FILENAME
        shutil.copy2(str(db), str(remote))
        # Même timestamp (copy2 préserve)
        with patch("services.sync_service.settings_service") as mock_svc, \
             patch("services.sync_service.DB_PATH", str(db)):
            mock_svc.get.return_value = str(sync_dir)
            st = get_status()
        assert st["up_to_date"] is True


# ── push ──────────────────────────────────────────────────────────────────────

class TestPush:

    def test_push_no_folder_configured(self):
        from services.sync_service import push
        with patch("services.sync_service.settings_service") as mock_svc:
            mock_svc.get.return_value = ""
            result = push()
        assert result["ok"] is False
        assert "configuré" in result["error"]

    def test_push_no_local_db(self, tmp_path):
        from services.sync_service import push
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        with patch("services.sync_service.settings_service") as mock_svc, \
             patch("services.sync_service.DB_PATH", str(tmp_path / "missing.db")):
            mock_svc.get.return_value = str(sync_dir)
            result = push()
        assert result["ok"] is False
        assert "introuvable" in result["error"]

    def test_push_folder_not_exists(self, tmp_path):
        from services.sync_service import push
        db = tmp_path / "local.db"
        db.write_bytes(b"data")
        with patch("services.sync_service.settings_service") as mock_svc, \
             patch("services.sync_service.DB_PATH", str(db)):
            mock_svc.get.return_value = str(tmp_path / "nonexistent_dir")
            result = push()
        assert result["ok"] is False

    def test_push_copies_file(self, tmp_path):
        from services.sync_service import push, SYNC_FILENAME
        db = tmp_path / "local.db"
        db.write_bytes(b"my_database_content")
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        with patch("services.sync_service.settings_service") as mock_svc, \
             patch("services.sync_service.DB_PATH", str(db)):
            mock_svc.get.return_value = str(sync_dir)
            result = push()
        assert result["ok"] is True
        remote = sync_dir / SYNC_FILENAME
        assert remote.exists()
        assert remote.read_bytes() == b"my_database_content"

    def test_push_returns_path(self, tmp_path):
        from services.sync_service import push, SYNC_FILENAME
        db = tmp_path / "local.db"
        db.write_bytes(b"data")
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        with patch("services.sync_service.settings_service") as mock_svc, \
             patch("services.sync_service.DB_PATH", str(db)):
            mock_svc.get.return_value = str(sync_dir)
            result = push()
        assert result["path"] == str(sync_dir / SYNC_FILENAME)


# ── pull ──────────────────────────────────────────────────────────────────────

class TestPull:

    def test_pull_no_folder_configured(self):
        from services.sync_service import pull
        with patch("services.sync_service.settings_service") as mock_svc:
            mock_svc.get.return_value = ""
            result = pull()
        assert result["ok"] is False

    def test_pull_no_remote_file(self, tmp_path):
        from services.sync_service import pull
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        with patch("services.sync_service.settings_service") as mock_svc, \
             patch("services.sync_service.DB_PATH", str(tmp_path / "local.db")):
            mock_svc.get.return_value = str(sync_dir)
            result = pull()
        assert result["ok"] is False
        assert "Aucun fichier" in result["error"]

    def test_pull_replaces_local_db(self, tmp_path):
        from services.sync_service import pull, SYNC_FILENAME
        import time
        db = tmp_path / "local.db"
        db.write_bytes(b"old_local")
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        remote = sync_dir / SYNC_FILENAME
        remote.write_bytes(b"new_remote")
        # Remote 30s plus récent que local
        old_ts = time.time() - 30
        os.utime(str(db), (old_ts, old_ts))
        with patch("services.sync_service.settings_service") as mock_svc, \
             patch("services.sync_service.DB_PATH", str(db)), \
             patch("services.sync_service.BACKUP_DIR", str(tmp_path / "backups")):
            mock_svc.get.return_value = str(sync_dir)
            result = pull()
        assert result["ok"] is True
        assert db.read_bytes() == b"new_remote"

    def test_pull_creates_backup(self, tmp_path):
        from services.sync_service import pull, SYNC_FILENAME
        import time
        db = tmp_path / "local.db"
        db.write_bytes(b"old")
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        remote = sync_dir / SYNC_FILENAME
        remote.write_bytes(b"new")
        # Remote 30s plus récent
        old_ts = time.time() - 30
        os.utime(str(db), (old_ts, old_ts))
        backup_dir = tmp_path / "backups"
        with patch("services.sync_service.settings_service") as mock_svc, \
             patch("services.sync_service.DB_PATH", str(db)), \
             patch("services.sync_service.BACKUP_DIR", str(backup_dir)):
            mock_svc.get.return_value = str(sync_dir)
            result = pull()
        assert result["ok"] is True
        assert result["backup"] is not None
        assert os.path.exists(result["backup"])

    def test_pull_conflict_without_force(self, tmp_path):
        from services.sync_service import pull, SYNC_FILENAME
        import time
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        remote = sync_dir / SYNC_FILENAME
        remote.write_bytes(b"old_remote")
        db = tmp_path / "local.db"
        db.write_bytes(b"newer_local")
        # Forcer local 30s plus récent que remote
        old_ts = time.time() - 30
        os.utime(str(remote), (old_ts, old_ts))
        with patch("services.sync_service.settings_service") as mock_svc, \
             patch("services.sync_service.DB_PATH", str(db)), \
             patch("services.sync_service.BACKUP_DIR", str(tmp_path / "backups")):
            mock_svc.get.return_value = str(sync_dir)
            result = pull(force=False)
        assert result["ok"] is False
        assert result.get("conflict") is True

    def test_pull_force_overwrites_newer_local(self, tmp_path):
        from services.sync_service import pull, SYNC_FILENAME
        import time
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        remote = sync_dir / SYNC_FILENAME
        remote.write_bytes(b"old_remote")
        db = tmp_path / "local.db"
        db.write_bytes(b"newer_local")
        # Remote 30s plus ancien
        old_ts = time.time() - 30
        os.utime(str(remote), (old_ts, old_ts))
        backup_dir = tmp_path / "backups"
        with patch("services.sync_service.settings_service") as mock_svc, \
             patch("services.sync_service.DB_PATH", str(db)), \
             patch("services.sync_service.BACKUP_DIR", str(backup_dir)):
            mock_svc.get.return_value = str(sync_dir)
            result = pull(force=True)
        assert result["ok"] is True
        assert db.read_bytes() == b"old_remote"
