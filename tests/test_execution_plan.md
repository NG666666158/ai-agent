# AI Agent MVP 测试执行计划

## 1. 本轮梳理结论

结合 `test_spec.md` 与当前代码实现，四个核心测试对象对应关系如下：

- Parser：
  入口在 `src/orion_agent/core/runtime_agent.py::_parse_goal`
  依赖 `src/orion_agent/core/prompts.py::parse_goal_messages`
  实际解析行为由 `src/orion_agent/core/llm_runtime.py` 中各类 `generate_json()` 及 `FallbackLLMClient._extract_goal/_extract_constraints` 决定
- Planner：
  核心在 `src/orion_agent/core/planner.py::Planner.build_plan`
  负责把解析后的目标、记忆、是否有 source、是否允许 web search，映射成步骤列表
- Tool Caller：
  工具注册与调用在 `src/orion_agent/core/tools.py::ToolRegistry`
  执行期调用与调用记录在 `src/orion_agent/core/execution_engine.py::_call_tool`
- State Machine：
  状态流转规则在 `src/orion_agent/core/state_machine.py`
  真实任务状态推进由 `runtime_agent.py` 和 `execution_engine.py` 驱动

## 2. 当前代码与规范的对齐说明

- `test_spec.md` 中的 Parser、Planner、Tool Caller、State Machine 都能在当前项目中找到明确落点，适合编写单元测试。
- 项目已经存在部分测试文件与目录骨架，但需要按本规范继续补齐、重构或复用，不建议把逻辑继续堆在已有顶层旧文件中。
- 当前后端测试框架仍应保持为 `unittest`，并优先使用 Mock 或自定义 Stub 隔离外部 LLM / 网络请求。
- 前端当前更适合作为集成/黑盒链路的观察面；本轮重点会先落在后端单元测试、集成测试与数据驱动黑盒测试。

## 3. 计划生成的测试文件与测试函数

### 3.1 单元测试

#### `tests/unit/test_parser_runtime_agent.py`

- `test_parse_goal_success_with_valid_llm_json`
- `test_parse_goal_rejects_invalid_llm_schema`
- `test_task_create_request_rejects_empty_or_short_goal`
- `test_fallback_parser_extracts_goal_and_constraints_from_request_payload`
- `test_fallback_parser_handles_garbled_or_semantic_noise_input`
- `test_fallback_parser_handles_missing_json_payload`

#### `tests/unit/test_planner.py`

- `test_build_plan_maps_known_step_names_to_expected_tools`
- `test_build_plan_includes_source_step_only_when_source_available`
- `test_build_plan_includes_web_step_only_when_search_enabled`
- `test_build_plan_supports_single_step_like_goal`
- `test_build_plan_raises_on_missing_required_step_fields`
- `test_build_plan_handles_ambiguous_goal_with_fallback_steps`

#### `tests/unit/test_tool_registry.py`

- `test_invoke_unknown_tool_raises_value_error`
- `test_read_local_file_returns_content`
- `test_read_local_file_missing_path_raises_exception`
- `test_summarize_text_truncates_long_text`
- `test_extract_keywords_deduplicates_and_limits_count`
- `test_web_search_returns_empty_when_disabled`
- `test_web_search_returns_empty_on_timeout`
- `test_web_search_returns_empty_on_http_error`
- `test_generate_markdown_builds_expected_structure`

#### `tests/unit/test_execution_engine_tool_calls.py`

- `test_call_tool_records_success_invocation`
- `test_call_tool_records_error_invocation`
- `test_resolve_source_material_from_source_text`
- `test_resolve_source_material_from_source_path`
- `test_generate_deliverable_records_markdown_tool_invocation`

#### `tests/unit/test_state_machine.py`

- `test_valid_state_transition_updates_status_and_timestamp`
- `test_invalid_state_transition_raises_exception`
- `test_terminal_states_do_not_allow_further_transition`
- `test_running_waiting_tool_roundtrip_is_valid`
- `test_reflecting_can_only_finish_to_completed_failed_or_cancelled`

### 3.2 集成测试

#### `tests/integration/test_pipeline_fixture.py`

- `test_fixture_runs_parse_plan_execute_end_to_end`
- `test_fixture_propagates_tool_output_between_steps`
- `test_fixture_preserves_context_between_parse_plan_and_execution`

#### `tests/integration/test_pipeline_ddt.py`

- `test_scenarios_from_dataset`
- `test_mock_file_read_success`
- `test_mock_file_read_not_found`
- `test_mock_summarize_success`
- `test_mock_tool_timeout`

### 3.3 测试夹具与数据

#### `tests/integration/fixture_utils.py`

- 提供统一的 AgentService 构造器
- 提供 Mock LLM、Mock ToolRegistry、测试任务请求构造器
- 提供从“输入 -> 任务执行 -> 输出” 的可复用 fixture

#### `tests/mocks/tool_mocks.py`

- `mock_file_read_success`
- `mock_file_read_not_found`
- `mock_summarize_success`
- `mock_tool_timeout`

#### `tests/fixtures/test_cases.yaml`

- 存放 `test_spec.md` 中 20 个业务/鲁棒性场景
- 每条场景至少包含：
  `id`
  `persona`
  `input`
  `expected_steps`
  `expected_tools`
  `expected_output_keywords`
  `mock_mode`

### 3.4 报告与执行脚本

#### `tests/scripts/run_all_tests_and_report.py`

- 一键运行全部 `unittest`
- 汇总总数、通过数、失败数、错误数
- 输出 Markdown 格式报告

## 4. 第二步将优先落地的内容

进入第二步后，我会优先处理以下单元测试模块：

1. `test_parser_runtime_agent.py`
2. `test_planner.py`
3. `test_tool_registry.py`
4. `test_execution_engine_tool_calls.py`
5. `test_state_machine.py`

原因：

- 这五类直接对应规范中的四个核心模块与工具参数边界
- 最容易通过 Mock 隔离外部依赖
- 能尽早暴露解析、规划、参数映射与状态流转中的逻辑缺陷

## 5. 风险与说明

- `test_spec.md` 文本存在编码乱码，但结构和测试意图仍可清晰识别，当前不构成阻塞。
- 仓库中已经存在部分测试实现与目录骨架；第二步我会先复用已有结构，再补齐遗漏，不会无意义重复造轮子。
- 如果在第二步发现规范要求与当前业务实现严重冲突，我会按你的要求暂停并向你确认，不会擅自改动核心业务逻辑。
