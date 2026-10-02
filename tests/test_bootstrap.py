"""Bootstrap previews offline and applies every table file before the procedure."""

import contextlib
import io
import unittest
from unittest.mock import MagicMock, patch

from scripts.pipeline import bootstrap


class BootstrapTest(unittest.TestCase):
    def test_every_table_file_exists_and_only_creates_missing_tables(self):
        for name in bootstrap.TABLE_FILES:
            sql = (bootstrap.SETUP_DIR / name).read_text()
            self.assertIn("CREATE TABLE IF NOT EXISTS", sql, name)

    def test_preview_does_not_connect(self):
        with patch.object(bootstrap, "connect_project") as connect, \
                contextlib.redirect_stdout(io.StringIO()) as out:
            bootstrap.preview()
        connect.assert_not_called()
        self.assertIn("setup/03_update_watermark.sql", out.getvalue())

    def test_execute_applies_tables_then_procedure(self):
        cursor = MagicMock()
        connection = MagicMock()
        connection.__enter__.return_value.cursor.return_value.__enter__.return_value = cursor
        order = []
        with patch.object(bootstrap, "connect_project", return_value=connection), \
                patch.object(bootstrap, "build_bundle", return_value="digest"), \
                patch.object(bootstrap, "run_sql_file", side_effect=lambda _c, p: order.append(p.name) or 1), \
                patch.object(bootstrap, "upload_and_create_procedure",
                             side_effect=lambda *_: order.append("procedure")):
            result = bootstrap.execute()
        self.assertEqual(order, [*bootstrap.TABLE_FILES, "procedure"])
        self.assertEqual(result["procedure_bundle_sha256"], "digest")


if __name__ == "__main__":
    unittest.main()
