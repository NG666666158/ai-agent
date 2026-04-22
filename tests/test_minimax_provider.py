import os
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from orion_agent.core import config as config_module
from orion_agent.core.config import Settings, get_settings, load_project_env
from orion_agent.core.llm_runtime import FallbackLLMClient, MiniMaxLLMClient, build_llm_client
from orion_agent.core.repository import TaskRepository
from orion_agent.core.runtime_agent import AgentService


class MiniMaxProviderTests(unittest.TestCase):
    def _make_project_root(self) -> Path:
        root = Path("tmp") / f"test-env-{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def test_build_llm_client_uses_minimax_provider_when_configured(self) -> None:
        settings = Settings(
            llm_provider="minimax",
            minimax_api_key="test-key",
            minimax_model="MiniMax-M2.7",
            minimax_base_url="https://api.minimaxi.com/anthropic",
            minimax_max_retries=2,
        )

        fake_client = object()
        with patch("orion_agent.core.llm_runtime.MiniMaxLLMClient", return_value=fake_client) as minimax_client:
            client = build_llm_client(settings)

        self.assertIs(client, fake_client)
        minimax_client.assert_called_once()

    def test_build_llm_client_falls_back_without_provider_key(self) -> None:
        settings = Settings(llm_provider="minimax", minimax_api_key=None, openai_api_key=None)

        client = build_llm_client(settings)

        self.assertIsInstance(client, FallbackLLMClient)

    def test_minimax_client_converts_anthropic_base_url_to_openai_compatible_endpoint(self) -> None:
        settings = Settings(
            llm_provider="minimax",
            minimax_api_key="test-key",
            minimax_base_url="https://api.minimaxi.com/anthropic",
        )

        with patch("orion_agent.core.llm_runtime.OpenAI") as openai_client:
            MiniMaxLLMClient(settings)

        openai_client.assert_called_once()
        self.assertEqual(openai_client.call_args.kwargs["base_url"], "https://api.minimaxi.com/v1")

    def test_minimax_json_completion_uses_prompted_json_without_openai_response_format(self) -> None:
        settings = Settings(
            llm_provider="minimax",
            minimax_api_key="test-key",
            minimax_base_url="https://api.minimaxi.com/anthropic",
        )
        fake_response = type(
            "FakeResponse",
            (),
            {"choices": [type("FakeChoice", (), {"message": type("FakeMessage", (), {"content": "{\"ok\": true}"})()})()]},
        )()
        with patch("orion_agent.core.llm_runtime.OpenAI") as openai_client:
            openai_client.return_value.chat.completions.create.return_value = fake_response

            client = MiniMaxLLMClient(settings)
            payload = client.generate_json(system_prompt="system", user_prompt="user")

        self.assertEqual(payload, {"ok": True})
        kwargs = openai_client.return_value.chat.completions.create.call_args.kwargs
        self.assertNotIn("response_format", kwargs)

    def test_minimax_json_completion_extracts_json_from_wrapped_text(self) -> None:
        settings = Settings(
            llm_provider="minimax",
            minimax_api_key="test-key",
            minimax_base_url="https://api.minimaxi.com/anthropic",
        )
        fake_response = type(
            "FakeResponse",
            (),
            {
                "choices": [
                    type(
                        "FakeChoice",
                        (),
                        {
                            "message": type(
                                "FakeMessage",
                                (),
                                {"content": "下面是结果：\n```json\n{\"goal\": \"ok\", \"priority\": \"high\"}\n```"},
                            )()
                        },
                    )()
                ]
            },
        )()
        with patch("orion_agent.core.llm_runtime.OpenAI") as openai_client:
            openai_client.return_value.chat.completions.create.return_value = fake_response

            client = MiniMaxLLMClient(settings)
            payload = client.generate_json(system_prompt="system", user_prompt="user")

        self.assertEqual(payload, {"goal": "ok", "priority": "high"})

    def test_minimax_complete_extracts_text_from_content_parts(self) -> None:
        settings = Settings(
            llm_provider="minimax",
            minimax_api_key="test-key",
            minimax_base_url="https://api.minimaxi.com/anthropic",
        )
        fake_response = type(
            "FakeResponse",
            (),
            {
                "choices": [
                    type(
                        "FakeChoice",
                        (),
                        {
                            "message": type(
                                "FakeMessage",
                                (),
                                {"content": [{"type": "text", "text": "第一段"}, {"type": "text", "text": "第二段"}]},
                            )()
                        },
                    )()
                ]
            },
        )()
        with patch("orion_agent.core.llm_runtime.OpenAI") as openai_client:
            openai_client.return_value.chat.completions.create.return_value = fake_response

            client = MiniMaxLLMClient(settings)
            text = client.generate_text(system_prompt="system", user_prompt="user")

        self.assertEqual(text, "第一段\n第二段")

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

    def test_load_project_env_reads_deploy_env_without_overwriting_existing_env(self) -> None:
        project_root = self._make_project_root()
        deploy_dir = project_root / "deploy"
        deploy_dir.mkdir(parents=True, exist_ok=True)
        (deploy_dir / ".env").write_text(
            "\n".join(
                [
                    "LLM_PROVIDER=minimax",
                    "MINIMAX_API_KEY=test-minimax-key",
                    "ALLOW_ONLINE_SEARCH=true",
                ]
            ),
            encoding="utf-8",
        )

        with patch.dict(os.environ, {"LLM_PROVIDER": "openai"}, clear=True):
            load_project_env(project_root=project_root, force=True)

            self.assertEqual(os.environ["LLM_PROVIDER"], "openai")
            self.assertEqual(os.environ["MINIMAX_API_KEY"], "test-minimax-key")
            self.assertEqual(os.environ["ALLOW_ONLINE_SEARCH"], "true")

    def test_get_settings_loads_project_env_before_creating_settings(self) -> None:
        project_root = self._make_project_root()
        deploy_dir = project_root / "deploy"
        deploy_dir.mkdir(parents=True, exist_ok=True)
        (deploy_dir / ".env").write_text(
            "\n".join(
                [
                    "LLM_PROVIDER=minimax",
                    "MINIMAX_API_KEY=test-minimax-key",
                    "MINIMAX_MODEL=MiniMax-M2.7",
                ]
            ),
            encoding="utf-8",
        )

        with patch.object(config_module, "PROJECT_ROOT", project_root):
            with patch.dict(os.environ, {}, clear=True):
                config_module._ENV_LOADED = False
                settings = get_settings()

            self.assertEqual(settings.llm_provider, "minimax")
            self.assertEqual(settings.minimax_api_key, "test-minimax-key")


if __name__ == "__main__":
    unittest.main()
