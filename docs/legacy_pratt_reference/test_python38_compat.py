import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

class Python38CompatibilityTests(unittest.TestCase):
    def test_import_package(self):
        import ntable
        self.assertTrue(hasattr(ntable, "NTableBuilder"))

if __name__ == "__main__":
    unittest.main()
