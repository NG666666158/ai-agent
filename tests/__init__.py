"""Test package for Orion Agent."""

import unittest


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str):
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromName("tests.test_agent_service_v3"))
    suite.addTests(loader.loadTestsFromName("tests.test_api_v1"))
    suite.addTests(loader.loadTestsFromName("tests.test_minimax_provider"))
    return suite
