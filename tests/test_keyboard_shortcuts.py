import unittest

from chirp.keyboard_shortcuts import modifier_vk_groups


class TestKeyboardShortcuts(unittest.TestCase):
    def test_modifier_vk_groups_for_modifier_only_shortcut(self):
        self.assertEqual(
            modifier_vk_groups("ctrl+shift"),
            [(0x11, 0xA2, 0xA3), (0x10, 0xA0, 0xA1)],
        )

    def test_modifier_vk_groups_rejects_non_modifier_shortcut(self):
        self.assertEqual(modifier_vk_groups("ctrl+shift+space"), [])


if __name__ == "__main__":
    unittest.main()
