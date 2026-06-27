# Changelog

## v1.12.0

- 新增 LLM 工具 `ai_solve`：LLM 在聊天时可调用此工具独立解答用户问题
- 使用 `tool_loop_agent` 启动独立 agent 循环，可使用搜索等工具，不影响当前对话上下文
- 参数 `return_result`（默认 false）：false 时工具自行发送结果并结束对话，降低上下文开销；true 时返回结果文本由 LLM 继续处理
- 工具集排除自身避免递归调用
- `/AI解答` 指令优化：结果改用合并转发发送，回复触发指令的消息

## v1.11.0

- 新增 `/AI解答` 指令：引用消息→以该消息为锚点获取上下文并解答；未引用→分析最近对话识别问题并解答
- 使用 `tool_loop_agent` 替代 `llm_generate`：AI解答可调用所有已注册LLM工具（网页搜索、群消息查询等），独立于主聊天上下文运行
- 新增配置项「AI解答消息条数」（默认10，范围1-100）
- 新增内部方法 `_fetch_group_messages`、`_extract_reply_id`、`_load_provider_ids`、`_tool_loop_agent_with_fallback`
- LLM调用读取 `cmd_config.json` 主模型+回退模型列表，主模型失败逐个回退

## v1.10.3

- `batch_delete_msg` 返回结果精简：成功仅提示数量，失败仅显示消息 ID

## v1.10.2

- `_conf_schema.json`：非管理员允许的动作列表增加风险提示

## v1.10.1

- 权限校验拆分：仅 `call_action` 和 `batch_delete_msg` 做管理员+白名单校验，其他工具只校验平台
- `receive_result` 描述更新

## v1.10.0

- 新增 `get_msg_content`：通过消息 ID 获取消息内容，返回带 CQ 码的 raw_message
- 统一 `max_length` 默认值为 50（`get_user_recent_msgs` 从 100 改为 50）
- 精简各工具的参数描述

## v1.9.0

- `get_group_msg_history` 新增 `minutes` 参数：与 `count` 叠加生效，哪个先达到限制就停止；`message_id` 始终可用作起始锚点
- 删除 `__init__` 中读取旧配置 key「非管理员禁用的动作」的死代码（v1.8.1）
- 修正 CHANGELOG v1.3.0 的错误描述（v1.8.1）

## v1.8.0

- **破坏性变更**：动作权限从黑名单改为白名单，配置 key 从「非管理员禁用的动作」改为「非管理员允许的动作」
- 默认白名单仅包含 12 个安全动作（消息收发、群信息查询等），管理员不受限制
- 请在插件配置中重新设置允许的动作列表

## v1.7.1

- 修复 `call_action` 的 `limit` 参数签名：默认值从 `20` 改为 `None`，消除死代码分支
- 修复 `batch_delete_msg` 的 `int(mid)` 异常处理：非数字 ID 现在返回明确错误而非泛用报错
- 修复 `get_user_recent_msgs` 锚点提取的 falsy 陷阱：`message_seq=0` 不再被错误跳过
- `get_user_recent_msgs` 新增 15 秒超时保护，防止大量 API 调用阻塞
- 提取 `_check_permission`、`_format_message_line`、`_get_group_id` 公共方法，消除重复代码
- README 补充 `get_group_msg_history` 缺失的 `show_message_id` 参数文档
- README 更新 `call_action` 的 `limit` 参数说明

## v1.7.0

- 新增 `get_user_recent_msgs`：获取群内指定用户最近 n 分钟内的发言记录，支持设置最大返回条数和每条消息最大字数
- 使用 `reverseOrder: True` + `message_seq` 分页，兼容 NapCat 的消息历史 API

## v1.6.0

- 新增 `batch_delete_msg`：批量撤回消息，传入 message_id 列表逐条撤回并返回结果
- `get_group_msg_history` 新增 `show_message_id` 参数：在每条消息前显示 message_id

## v1.5.1

- `get_group_msg_history` 新增 `max_length` 参数：每条消息最大字符数，默认 50，超出截断用省略号，传 -1 不截断

## v1.5.0

- 新增 `get_group_msg_history`：获取当前群聊近 n 条消息记录，格式化为易读的对话记录（默认 20 条，上限 100）
- CQ 码精简：图片只保留 file，回复只保留 id，其他类型保留类型名和首个参数
- 优先显示群名片，无名片则用昵称
- 支持通过 `message_id` 从指定消息往前翻查

## v1.4.0

- `call_onebot_action` 的 `limit` 参数默认值改为 20，与其他工具对齐
- `limit` 支持 -1 表示无限制
- 精简 limit 截断逻辑

## v1.3.0

- 新增「非管理员禁用的动作」配置项：非管理员调用 `call_onebot_action` 时，命中禁用列表的动作会被拦截

## v1.2.0

- 新增 `__init__` 构造函数，读取配置中的禁用动作
- `call_onebot_action` 新增 `limit` 参数：截断列表结果，防止内容过多
- `call_onebot_action` 新增禁用动作校验：命中禁用列表时拦截
- 新增配置项：`允许非管理员`、`非管理员禁用的动作`（含 34 个可选动作）

## v1.1.0

- 新增 `get_group_member_list`：获取当前群成员列表，可选返回数量上限（最大 20）
- 新增 `get_group_member_info`：获取当前群内指定用户信息

## v1.0.0

- 初始版本
- `call_onebot_action`：调用任意 OneBot Action API（管理员专用）
- `get_raw_message`：获取当前消息原始 JSON 数据
- `send_onebot_msg`：通过 OneBot API 发送组合/复杂消息（CQ 码 / 消息段数组）
