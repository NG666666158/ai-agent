import unittest

from fastapi.testclient import TestClient

from orion_agent.main import app


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()

    def test_healthz(self) -> None:
        response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_root_ui_renders(self) -> None:
        response = self.client.get("/")
        tasks_page = self.client.get("/tasks")
        memories_page = self.client.get("/memories")
        settings_page = self.client.get("/settings")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Orion Agent", response.text)
        self.assertEqual(tasks_page.status_code, 200)
        self.assertEqual(memories_page.status_code, 200)
        self.assertEqual(settings_page.status_code, 200)

    def test_task_and_tools_endpoints(self) -> None:
        create_response = self.client.post(
            "/api/tasks",
            json={
                "goal": "Implement AI Agent MVP",
                "constraints": ["Use markdown"],
                "expected_output": "markdown",
                "source_text": "Implement planning, execution, tool use, and memory.",
                "enable_web_search": False,
            },
        )

        self.assertEqual(create_response.status_code, 200)
        task = create_response.json()
        self.assertEqual(task["status"], "COMPLETED")

        task_id = task["id"]
        detail_response = self.client.get(f"/api/tasks/{task_id}")
        tools_response = self.client.get("/api/tools")
        memory_response = self.client.get("/api/memories/search", params={"query": "mvp"})
        evaluation_response = self.client.get(f"/api/tasks/{task_id}/evaluation")
        runtime_response = self.client.get("/api/system/runtime")
        health_response = self.client.get("/api/system/health")
        probe_response = self.client.get("/api/system/llm-probe")
        metrics_response = self.client.get("/api/system/metrics")

        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(tools_response.status_code, 200)
        self.assertEqual(memory_response.status_code, 200)
        self.assertEqual(evaluation_response.status_code, 200)
        self.assertEqual(runtime_response.status_code, 200)
        self.assertEqual(health_response.status_code, 200)
        self.assertEqual(probe_response.status_code, 200)
        self.assertEqual(metrics_response.status_code, 200)
        self.assertGreaterEqual(len(tools_response.json()), 4)
        self.assertGreaterEqual(evaluation_response.json()["score"], 0.8)
        self.assertIn("vector_backend", runtime_response.json())
        self.assertIn("llm_provider", runtime_response.json())
        self.assertIn("status", probe_response.json())
        self.assertIn("orion_tasks_total", metrics_response.text)


if __name__ == "__main__":
    unittest.main()
