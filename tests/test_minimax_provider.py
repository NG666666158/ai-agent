import unittest

from orion_agent.core.config import Settings
from orion_agent.core.llm_runtime import FallbackLLMClient, build_llm_client
from orion_agent.core.repository import TaskRepository
from orion_agent.core.runtime_agent import AgentService


class MiniMaxProviderTests(unittest.TestCase):
    def test_build_llm_client_uses_minimax_provider_when_configured(self) -> None:
        settings = Settings(
            llm_provider="minimax",
            minimax_api_key="test-key",
            minimax_model="MiniMax-M2.7",
            minimax_base_url="https://api.minimaxi.com/anthropic",
            minimax_max_retries=2,
        )

        client = build_llm_client(settings)

        self.assertEqual(client.health()["provider"], "minimax")
        self.assertEqual(client.settings.minimax_max_retries, 2)

    def test_build_llm_client_falls_back_without_provider_key(self) -> None:
        settings = Settings(llm_provider="minimax", minimax_api_key=None, openai_api_key=None)

        client = build_llm_client(settings)

        self.assertIsInstance(client, FallbackLLMClient)

    def test_probe_reports_missing_minimax_credentials(self) -> None:
        service = AgentService(
            repository=TaskRepository(db_path=":memory:"),
            settings=Settings(
                llm_provider="minimax",
                minimax_api_key=None,
                openai_api_key=None,
            ),
        )

        probe = service.probe_llm()

        self.assertEqual(probe["provider"], "minimax")
        self.assertEqual(probe["status"], "missing_credentials")
        self.assertFalse(probe["configured"])
        service.repository.close()


if __name__ == "__main__":
    unittest.main()
