import json
import tempfile
import unittest
from pathlib import Path

from ConfigStore import config_path, load_config, save_config


class ConfigStoreTests(unittest.TestCase):
    def test_load_config_returns_default_for_missing_or_invalid_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_config(base_dir=tmp, default={"ok": True}), {"ok": True})
            path = Path(config_path(base_dir=tmp))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{bad", encoding="utf-8")

            self.assertEqual(load_config(base_dir=tmp, default={"fallback": 1}), {"fallback": 1})

    def test_save_config_writes_atomically_and_keeps_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(save_config({"old": 1}, base_dir=tmp))
            save_config({"new": 2}, base_dir=tmp)

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"new": 2})
            self.assertEqual(json.loads(Path(str(path) + ".bak").read_text(encoding="utf-8")), {"old": 1})
            self.assertFalse(Path(str(path) + ".tmp").exists())

    def test_save_config_keeps_limited_timestamp_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(save_config({"value": 0}, base_dir=tmp))
            for idx in range(1, 5):
                save_config({"value": idx}, base_dir=tmp, keep_backups=2)

            backups = sorted(path.parent.glob("SW_config_*.json.bak"))
            self.assertEqual(len(backups), 2)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"value": 4})
            self.assertEqual(json.loads(Path(str(path) + ".bak").read_text(encoding="utf-8")), {"value": 3})


if __name__ == "__main__":
    unittest.main()
