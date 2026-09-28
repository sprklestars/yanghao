import os
import unittest

from app.core.processes import pid_alive


class PidAliveTests(unittest.TestCase):
    def test_current_process_is_alive(self):
        self.assertTrue(pid_alive(os.getpid()))

    def test_invalid_pids_are_not_alive(self):
        for pid in (None, 0, -1):
            with self.subTest(pid=pid):
                self.assertFalse(pid_alive(pid))

    def test_unused_pid_is_not_alive(self):
        # 注意：这里必须走 pid_alive —— Windows 上 os.kill(999999999, 0)
        # 会尝试 TerminateProcess，而不是安全地探测。
        self.assertFalse(pid_alive(999999999))


if __name__ == "__main__":
    unittest.main()
