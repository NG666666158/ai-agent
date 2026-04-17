import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from orion_agent.api.routes import memories as memories_routes
from orion_agent.api.routes import sessions as sessions_routes
from orion_agent.api.routes import system as system_routes
from orion_agent.api.routes import tasks as tasks_routes
from orion_agent.core.llm_runtime import FallbackLLMClient
from orion_agent.core.repository import TaskRepository
from orion_agent.core.runtime_agent import AgentService
from orion_agent.dependencies import agent_service
from orion_agent.main import app


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_service = agent_service
        self.service = AgentService(
            repository=TaskRepository(db_path=":memory:"),
            llm_client=FallbackLLMClient(),
        )
        tasks_routes.agent_service = self.service
        sessions_routes.agent_service = self.service
        memories_routes.agent_service = self.service
        system_routes.agent_service = self.service
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        self.service.repository.close()
        tasks_routes.agent_service = self.original_service
        sessions_routes.agent_service = self.original_service
        memories_routes.agent_service = self.original_service
        system_routes.agent_service = self.original_service

    def test_healthz(self) -> None:
        response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_root_ui_renders(self) -> None:
        response = self.client.get("/")
        tasks_page = self.client.get("/tasks")
        sessions_page = self.client.get("/sessions")
        memories_page = self.client.get("/memories")
        settings_page = self.client.get("/settings")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Orion Agent", response.text)
        self.assertEqual(tasks_page.status_code, 200)
        self.assertEqual(sessions_page.status_code, 200)
        self.assertEqual(memories_page.status_code, 200)
        self.assertEqual(settings_page.status_code, 200)

    def test_task_and_system_endpoints(self) -> None:
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
        self.assertIn("citation_sources", task)
        self.assertIn("paragraph_citations", task)
        if task["recalled_memories"]:
            first_memory = task["recalled_memories"][0]
            self.assertIn("memory_type", first_memory)
            self.assertIn("retrieval_score", first_memory)
            self.assertIn("retrieval_reason", first_memory)
            self.assertIn("retrieval_channels", first_memory)

        task_id = task["id"]
        detail_response = self.client.get(f"/api/tasks/{task_id}")
        trace_response = self.client.get(f"/api/tasks/{task_id}/trace")
        tools_response = self.client.get("/api/tools")
        memory_response = self.client.get("/api/memories/search", params={"query": "mvp"})
        evaluation_response = self.client.get(f"/api/tasks/{task_id}/evaluation")
        runtime_response = self.client.get("/api/system/runtime")
        health_response = self.client.get("/api/system/health")
        probe_response = self.client.get("/api/system/llm-probe")
        metrics_response = self.client.get("/api/system/metrics")

        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(trace_response.status_code, 200)
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
        self.assertIn("tool_count", trace_response.json())

    def test_session_and_memory_endpoints(self) -> None:
        session_response = self.client.post("/api/sessions", json={"title": "接口会话"})
        self.assertEqual(session_response.status_code, 200)
        session = session_response.json()

        for index in range(5):
            task_response = self.client.post(
                "/api/tasks",
                json={
                    "goal": f"Create session answer round {index + 1}",
                    "expected_output": "markdown",
                    "enable_web_search": False,
                    "session_id": session["id"],
                },
            )
            self.assertEqual(task_response.status_code, 200)

        sessions_response = self.client.get("/api/sessions")
        detail_response = self.client.get(f"/api/sessions/{session['id']}")
        memories_response = self.client.get("/api/memories")
        refresh_response = self.client.post(f"/api/sessions/{session['id']}/refresh-summary", json={"force": True})

        self.assertEqual(sessions_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(memories_response.status_code, 200)
        self.assertEqual(refresh_response.status_code, 200)
        self.assertTrue(any(item["id"] == session["id"] for item in sessions_response.json()))
        self.assertGreaterEqual(len(detail_response.json()["messages"]), 2)
        self.assertTrue(detail_response.json()["session"]["context_summary"])
        self.assertEqual(refresh_response.json()["session"]["id"], session["id"])

        memories = memories_response.json()
        if memories:
            update_response = self.client.put(
                f"/api/memories/{memories[0]['id']}",
                json={
                    "topic": "Updated via API",
                    "summary": "Updated summary",
                    "details": "Updated details",
                    "tags": ["api", "edited"],
                },
            )
            self.assertEqual(update_response.status_code, 200)
            self.assertEqual(update_response.json()["topic"], "Updated via API")
            self.assertIn("versions", update_response.json())
            self.assertGreaterEqual(len(update_response.json()["versions"]), 2)

            delete_response = self.client.delete(f"/api/memories/{memories[0]['id']}")
            self.assertEqual(delete_response.status_code, 200)
            self.assertTrue(delete_response.json()["deleted"])

            remaining_memories = self.client.get("/api/memories")
            self.assertEqual(remaining_memories.status_code, 200)
            self.assertTrue(all(item["id"] != memories[0]["id"] for item in remaining_memories.json()))

    def test_session_branch_endpoint_copies_parent_session_context(self) -> None:
        parent_response = self.client.post("/api/sessions", json={"title": "父会话"})
        self.assertEqual(parent_response.status_code, 200)
        parent = parent_response.json()

        task_response = self.client.post(
            "/api/tasks",
            json={
                "goal": "为父会话生成一轮上下文",
                "expected_output": "markdown",
                "enable_web_search": False,
                "session_id": parent["id"],
            },
        )
        self.assertEqual(task_response.status_code, 200)

        branch_response = self.client.post(
            "/api/sessions",
            json={
                "title": "子分支",
                "source_session_id": parent["id"],
                "seed_prompt": "沿用父会话结论，继续展开方案。",
            },
        )

        self.assertEqual(branch_response.status_code, 200)
        branch = branch_response.json()
        self.assertEqual(branch["source_session_id"], parent["id"])

        detail_response = self.client.get(f"/api/sessions/{branch['id']}")
        self.assertEqual(detail_response.status_code, 200)
        detail = detail_response.json()
        self.assertGreaterEqual(len(detail["messages"]), 3)
        self.assertEqual(detail["messages"][0]["role"], "SYSTEM")

    def test_profile_endpoint_and_profile_hits_work_across_sessions(self) -> None:
        first_session = self.client.post("/api/sessions", json={"title": "偏好采集"})
        self.assertEqual(first_session.status_code, 200)
        first_session_id = first_session.json()["id"]

        create_response = self.client.post(
            "/api/tasks",
            json={
                "goal": "我想学java，告诉我学习路线",
                "expected_output": "markdown",
                "enable_web_search": False,
                "session_id": first_session_id,
            },
        )
        self.assertEqual(create_response.status_code, 200)

        profile_response = self.client.get("/api/system/profile")
        self.assertEqual(profile_response.status_code, 200)
        self.assertTrue(any(item["value"] == "Java" for item in profile_response.json()))

        second_session = self.client.post("/api/sessions", json={"title": "新会话"})
        self.assertEqual(second_session.status_code, 200)
        second_session_id = second_session.json()["id"]

        second_task = self.client.post(
            "/api/tasks",
            json={
                "goal": "你知道我最想学的语言是什么吗",
                "expected_output": "markdown",
                "enable_web_search": False,
                "session_id": second_session_id,
            },
        )
        self.assertEqual(second_task.status_code, 200)
        self.assertTrue(any(item["value"] == "Java" for item in second_task.json()["profile_hits"]))

    def test_async_launch_endpoint_returns_early_and_task_completes(self) -> None:
        launch_response = self.client.post(
            "/api/tasks/launch",
            json={
                "goal": "Show streaming progress in Chinese UI",
                "constraints": ["Use markdown"],
                "expected_output": "markdown",
                "enable_web_search": False,
            },
        )

        self.assertEqual(launch_response.status_code, 200)
        task = launch_response.json()
        self.assertIn(task["status"], {"CREATED", "PARSED", "PLANNED", "RUNNING"})
        self.assertIn("progress_updates", task)
        self.assertIn("live_result", task)

        task_id = task["id"]
        deadline = time.time() + 5
        latest = task
        while time.time() < deadline:
            latest = self.client.get(f"/api/tasks/{task_id}").json()
            if latest["status"] in {"COMPLETED", "FAILED"}:
                break
            time.sleep(0.05)

        self.assertEqual(latest["status"], "COMPLETED")
        self.assertGreaterEqual(len(latest["progress_updates"]), 3)
        self.assertIn("live_result", latest)

    def test_resume_endpoint_can_continue_cancelled_task(self) -> None:
        original_run = self.service.executor.run

        def delayed_run(*args, **kwargs):
            time.sleep(0.2)
            return original_run(*args, **kwargs)

        with patch.object(self.service.executor, "run", side_effect=delayed_run):
            launch_response = self.client.post(
                "/api/tasks/launch",
                json={
                    "goal": "Resume task through API after cancellation",
                    "expected_output": "markdown",
                    "enable_web_search": False,
                },
            )
            self.assertEqual(launch_response.status_code, 200)
            task = launch_response.json()

            time.sleep(0.05)
            cancel_response = self.client.post(f"/api/tasks/{task['id']}/cancel")
            self.assertEqual(cancel_response.status_code, 200)
            self.assertEqual(cancel_response.json()["status"], "CANCELLED")

            resume_response = self.client.post(
                f"/api/tasks/{task['id']}/resume",
                json={"reason": "continue"},
            )
            self.assertEqual(resume_response.status_code, 200)

        deadline = time.time() + 5
        latest = resume_response.json()
        while time.time() < deadline:
            latest = self.client.get(f"/api/tasks/{task['id']}").json()
            if latest["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
                break
            time.sleep(0.05)

        self.assertEqual(latest["status"], "COMPLETED")
        self.assertEqual(latest["checkpoint"]["current_stage"], "completed")
        self.assertEqual(latest["checkpoint"]["phase"], "COMPLETED")
        self.assertTrue(latest["checkpoint"]["last_completed_step_name"])

    def test_confirmation_endpoint_resumes_waiting_task(self) -> None:
        source_file = Path("tests/.tmp_api_approval.txt")
        source_file.write_text("api approval test", encoding="utf-8")
        try:
            launch_response = self.client.post(
                "/api/tasks/launch",
                json={
                    "goal": "读取本地文件并继续执行任务",
                    "expected_output": "markdown",
                    "source_path": str(source_file),
                    "enable_web_search": False,
                },
            )

            self.assertEqual(launch_response.status_code, 200)
            task = launch_response.json()

            deadline = time.time() + 5
            latest = task
            while time.time() < deadline:
                latest = self.client.get(f"/api/tasks/{task['id']}").json()
                if latest["status"] == "WAITING_APPROVAL":
                    break
                time.sleep(0.05)

            self.assertEqual(latest["status"], "WAITING_APPROVAL")
            self.assertEqual(len(latest["pending_approvals"]), 1)

            confirm_response = self.client.post(
                f"/api/tasks/{task['id']}/confirm",
                json={
                    "approval_id": latest["pending_approvals"][0]["id"],
                    "approved": True,
                },
            )
            self.assertEqual(confirm_response.status_code, 200)

            deadline = time.time() + 5
            latest_after_confirm = confirm_response.json()
            while time.time() < deadline:
                latest_after_confirm = self.client.get(f"/api/tasks/{task['id']}").json()
                if latest_after_confirm["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
                    break
                time.sleep(0.05)

            self.assertEqual(latest_after_confirm["status"], "COMPLETED")
            self.assertIn("pending_approvals", latest_after_confirm)
            self.assertTrue(any(item["approved"] is True for item in latest_after_confirm["pending_approvals"]))
        finally:
            if source_file.exists():
                source_file.unlink()

    def test_profile_update_and_merge_endpoints(self) -> None:
        self.client.post(
            "/api/tasks",
            json={
                "goal": "我想学 java，告诉我学习路线",
                "expected_output": "markdown",
                "enable_web_search": False,
            },
        )
        self.client.post(
            "/api/tasks",
            json={
                "goal": "我现在更想学 python，请给我建议",
                "expected_output": "markdown",
                "enable_web_search": False,
            },
        )

        profile_response = self.client.get("/api/system/profile", params={"include_inactive": True})
        self.assertEqual(profile_response.status_code, 200)
        facts = profile_response.json()
        java_fact = next(item for item in facts if item["value"] == "Java")
        python_fact = next(item for item in facts if item["value"] == "Python")

        update_response = self.client.put(
            f"/api/system/profile/{java_fact['id']}",
            json={
                "value": "TypeScript",
                "summary": "用户手动编辑为 TypeScript 偏好",
            },
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["value"], "TypeScript")

        merge_response = self.client.post(
            f"/api/system/profile/{python_fact['id']}/merge",
            json={
                "target_fact_id": update_response.json()["id"],
                "summary": "保留 TypeScript 作为主画像",
            },
        )
        self.assertEqual(merge_response.status_code, 200)
        self.assertEqual(merge_response.json()["id"], update_response.json()["id"])

        final_profile = self.client.get("/api/system/profile", params={"include_inactive": True}).json()
        merged_source = next(item for item in final_profile if item["id"] == python_fact["id"])
        self.assertEqual(merged_source["status"], "MERGED")
        self.assertEqual(merged_source["superseded_by"], update_response.json()["id"])


if __name__ == "__main__":
    unittest.main()
