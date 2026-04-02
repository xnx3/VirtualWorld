import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from genesis.chronicle import console


class ConsoleOutputMirrorTests(unittest.TestCase):
    def test_write_mirrors_output_to_console_log_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mirror_path = os.path.join(tmpdir, "console.log")
            original_path = os.environ.get("GENESIS_CONSOLE_LOG")
            os.environ["GENESIS_CONSOLE_LOG"] = mirror_path
            try:
                output = io.StringIO()
                with redirect_stdout(output):
                    console._write("first line")
                    console._write("second line")
            finally:
                if original_path is None:
                    os.environ.pop("GENESIS_CONSOLE_LOG", None)
                else:
                    os.environ["GENESIS_CONSOLE_LOG"] = original_path

            self.assertEqual(output.getvalue(), "first line\nsecond line\n")
            with open(mirror_path, "r", encoding="utf-8") as mirror:
                self.assertEqual(mirror.read(), "first line\nsecond line\n")


if __name__ == "__main__":
    unittest.main()
