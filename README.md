# OneBot 协议工具箱

为 LLM 暴露 OneBot（NapCat）原生能力的 AstrBot 插件。

## 功能

为 LLM 提供八个工具，让其能够直接调用 OneBot 协议能力：

| 工具 | 说明 |
|------|------|
| `call_onebot_action` | 调用任意 OneBot Action API，支持返回数量限制与白名单过滤（管理员可用） |
| `get_raw_message` | 获取当前消息的原始 JSON 数据结构 |
| `send_onebot_msg` | 通过 OneBot API 发送组合/复杂消息（CQ 码字符串或消息段数组） |
| `get_group_member_list` | 获取当前群成员列表，可选返回数量上限（最大 20） |
| `get_group_member_info` | 获取当前群内指定用户的信息 |
| `get_group_msg_history` | 获取当前群聊近 n 条消息记录，格式化为易读的对话记录（支持时间范围过滤，默认 20 条，上限 100） |
| `batch_delete_msg` | 批量撤回消息，传入 message_id 列表逐条撤回并返回结果（管理员可用） |
| `get_user_recent_msgs` | 获取群内指定用户最近 n 分钟内的发言记录，支持限制返回条数和每条最大字数 |
| `get_msg_content` | 通过消息 ID 获取消息内容，返回带 CQ 码的 raw_message 字符串 |
| `ai_solve` | LLM 在聊天时调用此工具独立解答用户问题，可使用搜索等工具，不影响对话上下文 |

### 用户指令

| 指令 | 说明 |
|------|------|
| `/AI解答` | 引用消息→以该消息为锚点获取上下文并解答；未引用→分析最近对话识别问题并解答。可调用工具 |

## 安装

将本插件放置于 AstrBot 的插件目录下即可：

```
data/plugins/onebot_toolkit/
```

重启 AstrBot 后自动加载。

## 配置

在 AstrBot 管理面板中配置以下选项：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| 允许非管理员 | bool | `false` | 是否允许非管理员使用 `call_onebot_action` 工具 |
| 非管理员允许的动作 | list | 见下方 | 非管理员允许的动作列表，仅列出的动作可调用，未列出默认拒绝。管理员不受限制 |
| AI解答消息条数 | int | `10` | `/AI解答` 指令获取的上下文消息条数，范围 1-100 |

### 可允许的动作列表

| 中文名 | OneBot Action |
|--------|---------------|
| 发送私聊消息 | `send_private_msg` |
| 发送群消息 | `send_group_msg` |
| 发送消息 | `send_msg` |
| 撤回消息 | `delete_msg` |
| 获取消息 | `get_msg` |
| 获取合并转发消息 | `get_forward_msg` |
| 发送好友赞 | `send_like` |
| 群组踢人 | `set_group_kick` |
| 群组单人禁言 | `set_group_ban` |
| 群组全员禁言 | `set_group_whole_ban` |
| 设置群管理员 | `set_group_admin` |
| 设置群名片 | `set_group_card` |
| 设置群名称 | `set_group_name` |
| 退出群组 | `set_group_leave` |
| 设置群专属头衔 | `set_group_special_title` |
| 处理加好友请求 | `set_friend_add_request` |
| 处理加群请求/邀请 | `set_group_add_request` |
| 获取登录号信息 | `get_login_info` |
| 获取陌生人信息 | `get_stranger_info` |
| 获取好友列表 | `get_friend_list` |
| 获取群信息 | `get_group_info` |
| 获取群列表 | `get_group_list` |
| 获取群成员信息 | `get_group_member_info` |
| 获取群成员列表 | `get_group_member_list` |
| 获取群荣誉信息 | `get_group_honor_info` |
| 获取Cookies | `get_cookies` |
| 获取CSRF Token | `get_csrf_token` |
| 获取QQ相关凭证 | `get_credentials` |
| 获取语音 | `get_record` |
| 获取图片 | `get_image` |
| 检查是否可以发送图片 | `can_send_image` |
| 检查是否可以发送语音 | `can_send_record` |
| 获取插件运行状态 | `get_status` |
| 获取版本信息 | `get_version_info` |
| 重启OneBot | `set_restart` |
| 清理缓存 | `clean_cache` |

### 默认允许的动作（非管理员，即白名单中允许的动作）

以下动作对非管理员默认允许，其余动作默认拒绝。管理员不受限制。

发送私聊消息、发送群消息、发送消息、撤回消息、获取消息、设置群名片、设置群名称、设置群专属头衔、获取群信息、获取群成员信息、获取群成员列表、获取群荣誉信息

## 工具说明

### call_onebot_action

调用 OneBot 协议的任意 Action API。

- **权限**：仅机器人管理员可用（可通过配置开放给非管理员）
- **参数**：
  - `action` (string)：Action 名称，如 `get_friend_list`、`send_group_msg`
  - `params` (object)：该 Action 的参数对象，无参数时传 `{}`
  - `limit` (number, 可选)：如果结果是列表，设置返回的最大数量，防止内容过多。默认不截断，传 20 表示最多返回 20 条
- **返回**：JSON 格式响应（缩进 4 空格，保留中文）
- **白名单过滤**：非管理员只能调用允许列表中的 Action，OneBot 新增的未列出动作默认拒绝；管理员不受限制

### get_raw_message

获取当前消息的原始 JSON 元数据，用于查看底层消息结构。

- **参数**：无
- **返回**：原始消息的 JSON 字符串；若平台不支持则回退为框架消息链

### send_onebot_msg

通过 OneBot API 发送复杂消息到当前聊天，支持 CQ 码和消息段数组两种格式。

- **参数**：
  - `message_str` (string, 可选)：CQ 码字符串，如 `[CQ:at,qq=xxx]你好[CQ:face,id=272]`
  - `message_array` (array, 可选)：OneBot 消息段数组，如 `[{"type":"face","data":{"id":"272"}}]`
  - `receive_result` (boolean, 可选)：是否接收发送反馈，默认 `false`（发送后静默结束）
- **说明**：纯文本消息请直接返回，不要使用此工具。视频和文件只能单独发送。

### get_group_member_list

获取当前群的成员列表，仅在群聊场景下可用。

- **参数**：
  - `limit` (number, 可选)：返回成员数量上限，最大 20，默认 20
- **返回**：JSON 格式，包含 `group_id`、`total`（群总人数）、`returned`（实际返回数）、`members`（成员列表）

### get_group_member_info

获取当前群内指定用户的信息，仅在群聊场景下可用。

- **参数**：
  - `user_id` (number)：目标用户的 QQ 号
- **返回**：JSON 格式，包含该用户在群内的昵称、角色、入群时间等信息

### get_group_msg_history

获取当前群聊近 n 条消息记录，格式化为易读的对话记录，仅在群聊场景下可用。

| 参数 | 说明 |
|------|------|
| `count` (number, 可选) | 最大条数，默认 20，上限 100 |
| `minutes` (number, 可选) | 回溯时间范围（分钟），默认 0 不限制。与 count 叠加，先触限先停 |
| `msg_id` (number, 可选) | 起始消息 ID，从此往前查。默认 0 从最新开始 |
| `max_length` (number, 可选) | 单条消息最大字符数，超出截断。默认 50，-1 不截断 |
| `show_message_id` (boolean, 可选) | 是否显示 message_id。默认 false |
- **返回**：格式化的对话记录，每行一条，格式为 `昵称：消息内容`（开启 show_message_id 时为 `message_id=xxx;昵称：消息内容`）
- **CQ 码精简**：图片只保留 file 参数，回复只保留 id 参数，其他 CQ 码保留类型名和首个参数
- **昵称显示**：优先显示群名片，无名片则使用昵称

### batch_delete_msg

批量撤回消息，传入多个 message_id 逐条撤回并返回每条结果。适用于群聊和私聊。

- **权限**：仅机器人管理员可用（可通过配置开放给非管理员）
- **参数**：
  - `message_ids` (array[string])：要撤回的消息 ID 列表，如 `["123456", "789012"]`
- **返回**：汇总信息，包含成功/失败计数和每条消息的撤回结果

### get_user_recent_msgs

获取当前群内指定用户最近 n 分钟内的发言记录，仅在群聊场景下可用。自动分页回溯群消息历史直到覆盖时间范围。

- **参数**：
  - `user_id` (number)：目标用户的 QQ 号
  - `minutes` (number, 可选)：回溯的时间范围（分钟），默认 10，上限 1440（24小时）
  - `max_count` (number, 可选)：返回消息的最大条数，默认 20，上限 100
  - `max_length` (number, 可选)：单条消息最大字符数，超出截断。默认 50，-1 不截断
- **返回**：格式化的发言记录，每行格式为 `msg_id=消息ID：消息内容`，按时间倒序排列
- **分页策略**：使用 `reverseOrder: True` + `message_seq` 分页回溯，动态检测消息顺序，每轮 100 条最多 10 轮，支持去重

### get_msg_content

通过消息 ID 获取消息内容，返回带 CQ 码的 raw_message 字符串。

- **参数**：
  - `msg_id` (number)：消息 ID
- **返回**：raw_message 字符串（含 CQ 码）；若无 raw_message 则返回完整 JSON

### /AI解答（用户指令）

引用群聊消息后调用 LLM 分析解答，两种用法：

- **引用消息**：以引用的消息为锚点，向前获取 n 条消息作为上下文，LLM 解答锚点消息所涉及的问题
- **未引用**：获取最近 n 条消息，LLM 识别对话中可能的问题并解答，无明确问题时总结讨论要点

使用 `tool_loop_agent` 实现，可调用所有已注册的 LLM 工具（网页搜索、群消息查询等），独立于主聊天上下文运行，不影响对话历史。

- **配置**：消息条数通过插件配置「AI解答消息条数」调整（默认 10，范围 1-100）
- **模型**：读取 `cmd_config.json` 的主模型和回退模型列表，主模型失败逐个回退
- **仅限群聊**

### ai_solve

LLM 在聊天时可调用此工具独立解答用户问题。启动独立的 agent 循环（`tool_loop_agent`），可使用搜索等已注册工具获取信息，不影响当前对话上下文。

- **参数**：
  - `question` (string)：要解答的问题
  - `return_result` (boolean, 可选)：默认 `false`。`false` 时工具自行发送解答结果（合并转发，回复触发消息）并结束对话，LLM 不需要再回复；`true` 时返回解答结果文本，由 LLM 继续处理
- **说明**：工具集排除自身避免递归；主模型失败逐个回退

## 环境要求

- AstrBot（或兼容框架）
- OneBot 协议实现（如 NapCat）
- 平台：aiocqhttp（QQ）

## License

MIT
