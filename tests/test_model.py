import unittest

from steps.model import Pin, PinLine


def make_pin():
    return Pin(
        id="20261113-100000",
        name="Cloudflare setup",
        folder="/home/u/myapp",
        source="claude",
        agent="claude",
        session_id="abc",
        created_at="2026-11-13T10:00:00",
        lines=[
            PinLine("user", "> how do I deploy?"),
            PinLine("step", "1. Create project", 0),
            PinLine("step", "2. Connect repo", 1),
        ],
        checked={1},
    )


class ModelTest(unittest.TestCase):
    def test_pin_roundtrip(self):
        p = make_pin()
        self.assertEqual(Pin.from_dict(p.to_dict()), p)

    def test_checked_serialized_as_sorted_list(self):
        p = make_pin()
        p.checked = {1, 0}
        self.assertEqual(p.to_dict()["checked"], [0, 1])

    def test_progress(self):
        self.assertEqual(make_pin().progress, (1, 2))

    def test_progress_no_steps(self):
        p = make_pin()
        p.lines = [PinLine("text", "hello")]
        p.checked = set()
        self.assertEqual(p.progress, (0, 0))


if __name__ == "__main__":
    unittest.main()
