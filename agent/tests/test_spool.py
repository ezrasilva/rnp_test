import tempfile
import unittest
from pathlib import Path

from pqc_agent.spool import LocalSpool


class SpoolTests(unittest.TestCase):
    def test_sequence_persists_and_ack_preserves_gaps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spool = LocalSpool(root, "run-1", "ric")
            self.assertEqual(spool.append(b"one"), 1)
            self.assertEqual(spool.append(b"two"), 2)
            self.assertEqual(spool.append(b"three"), 3)
            spool.acknowledge(3, [2])
            self.assertEqual(spool.pending(), [(2, b"two")])
            spool.close()
            reopened = LocalSpool(root, "run-1", "ric")
            self.assertEqual(reopened.append(b"four"), 4)
            reopened.close()

