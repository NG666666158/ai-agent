from __future__ import annotations

from textwrap import dedent


class PromptLibrary:
    """Central store for reusable prompt templates."""

    def parse_goal_messages(self, request_payload: str, session_context: str | None = None) -> tuple[str, str]:
        system = dedent(
            """
            You are an AI agent task parser.
            Convert the user request into structured JSON with keys:
            goal, constraints, expected_output, priority, domain, deliverable_title.
            Return JSON only.
            """
        ).strip()
        user_parts = []
        if session_context:
            user_parts.append(f"Conversation context summary:\n{session_context}")
        user_parts.append(f"Parse this task request into JSON:\n{request_payload}")
        user = "\n\n".join(user_parts)
        return system, user

    def plan_messages(
        self,
        parsed_goal_payload: str,
        recalled_memories_payload: str,
        enable_web_search: bool,
        has_source: bool,
    ) -> tuple[str, str]:
        system = dedent(
            """
            You are an AI agent planner.
            Produce JSON with a top-level key "steps".
            Each step must contain: name, description, tool_name.
            Use only these step names:
            Parse Task, Recall Memory, Read Source Material, Web Research, Create Plan, Draft Deliverable, Review Output.
            Use Read Source Material only when source material exists.
            Use Web Research only when web search is allowed and useful.
            Draft Deliverable must set tool_name to generate_markdown.
            Read Source Material must set tool_name to read_local_file.
            Web Research must set tool_name to web_search.
            Always include Parse Task, Recall Memory, Create Plan, Draft Deliverable, Review Output.
            Return JSON only.
            """
        ).strip()
        user = dedent(
            f"""
            Parsed goal:
            {parsed_goal_payload}

            Recalled memories:
            {recalled_memories_payload}

            Web search allowed: {enable_web_search}
            Has source material: {has_source}
            """
        ).strip()
        return system, user

    def deliverable_messages(
        self,
        parsed_goal_payload: str,
        step_outputs_payload: str,
        recalled_memories_payload: str,
        session_context: str | None = None,
    ) -> tuple[str, str]:
        system = dedent(
            """
            You are an AI execution agent.
            Generate only the answer body in Markdown.
            Do not include the document title.
            Do not include section headings such as "回答正文", "工具调用", "来源文件", or their English equivalents.
            Do not restate tool invocation logs in the answer body.
            The runtime will assemble the outer Markdown structure for you.
            The result must be concrete, implementation-oriented, and clearly structured.
            Respond in Simplified Chinese by default unless the user explicitly requests another language.
            """
        ).strip()
        parts = []
        if session_context:
            parts.append(
                dedent(
                    f"""
                    Conversation context summary:
                    {session_context}
                    """
                ).strip()
            )
        parts.append(
            dedent(
                f"""
                Goal:
                {parsed_goal_payload}

                Step outputs:
                {step_outputs_payload}

                Relevant long-term memories:
                {recalled_memories_payload}
                """
            ).strip()
        )
        user = "\n\n".join(parts)
        return system, user

    def conversation_summary_messages(
        self,
        previous_summary: str,
        messages_payload: str,
    ) -> tuple[str, str]:
        system = dedent(
            """
            You are a conversation summarizer for a multi-turn AI agent.
            Compress the ongoing conversation into a concise working-memory summary.
            Keep user goals, constraints, decisions, unresolved items, and important outputs.
            Return plain text only.
            """
        ).strip()
        user = dedent(
            f"""
            Previous summary:
            {previous_summary or "(none)"}

            New messages to compress:
            {messages_payload}
            """
        ).strip()
        return system, user

    def review_messages(self, parsed_goal_payload: str, result_payload: str) -> tuple[str, str]:
        system = dedent(
            """
            You are an AI reviewer.
            Return JSON with keys: passed, summary, checklist.
            checklist must be an array of short strings.
            Return JSON only.
            """
        ).strip()
        user = dedent(
            f"""
            Parsed goal:
            {parsed_goal_payload}

            Deliverable:
            {result_payload}
            """
        ).strip()
        return system, user

    def memory_summary_messages(self, goal: str, result: str) -> tuple[str, str]:
        system = dedent(
            """
            You are an AI memory writer.
            Return JSON with keys: topic, summary, details, tags.
            tags must be an array of short strings.
            Return JSON only.
            """
        ).strip()
        user = dedent(
            f"""
            Goal:
            {goal}

            Result:
            {result}
            """
        ).strip()
        return system, user
