import unittest

from pqc_agent.collectors.xfrm import XfrmCollector


SAMPLE = """src 10.10.0.1 dst 10.10.0.2
 proto esp spi 0x00000100 reqid 1 mode transport
 lifetime current:
   320(bytes), 5(packets)
   add 12(sec), use 1(sec)
 stats:
   replay-window 0 replay 2 failed 1
"""


class XfrmTests(unittest.TestCase):
    def test_parse_state_without_keys(self):
        states = XfrmCollector.parse(SAMPLE)
        self.assertEqual(len(states), 1)
        self.assertEqual(states[0].spi, "0x00000100")
        self.assertEqual(states[0].packets, 5)
        self.assertEqual(states[0].bytes, 320)
        self.assertEqual(states[0].lifetime_seconds, 12)
        self.assertEqual(states[0].replay_errors, 2)
        self.assertEqual(states[0].integrity_errors, 1)

