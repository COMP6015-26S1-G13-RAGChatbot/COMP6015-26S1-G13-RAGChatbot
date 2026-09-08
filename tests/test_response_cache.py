import time
import unittest

from backend.services.response_cache import TTLCache


class ResponseCacheTests(unittest.TestCase):
    def test_cache_expires_and_returns_an_independent_copy(self):
        cache = TTLCache(max_entries=2, ttl_seconds=0.02)
        original = {"citations": ["source"]}
        cache.set("question", original)
        cached = cache.get("question")
        cached["citations"].append("changed")
        self.assertEqual(cache.get("question"), original)
        time.sleep(0.03)
        self.assertIsNone(cache.get("question"))

    def test_cache_evicts_least_recently_used_entry(self):
        cache = TTLCache(max_entries=2, ttl_seconds=60)
        cache.set("first", 1)
        cache.set("second", 2)
        self.assertEqual(cache.get("first"), 1)
        cache.set("third", 3)
        self.assertIsNone(cache.get("second"))
        self.assertEqual(len(cache), 2)


if __name__ == "__main__":
    unittest.main()
