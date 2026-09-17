import unittest

from app.services.face_reference_duplicate_service import exact_duplicate_asset_ids


class ExactDuplicateFaceIdsTests(unittest.TestCase):
    def test_keeps_oldest_asset(self):
        duplicates, groups = exact_duplicate_asset_ids([
            (74, b"same-face"),
            (58, b"different-face"),
            (61, b"same-face"),
            (80, b"same-face"),
        ])

        self.assertEqual(duplicates, [74, 80])
        self.assertEqual(groups, 1)

    def test_does_not_merge_distinct_content(self):
        duplicates, groups = exact_duplicate_asset_ids([
            (1, b"face-a"),
            (2, b"face-b"),
        ])

        self.assertEqual(duplicates, [])
        self.assertEqual(groups, 0)


if __name__ == "__main__":
    unittest.main()
