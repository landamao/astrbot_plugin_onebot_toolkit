# OneBot 协议工具箱

为 LLM 暴露 OneBot（NapCat）原生能力的 AstrBot 插件。插件类无需 `__init__` 构造函数，安装即用。

## 功能

为 LLM 提供三个工具，让其能够直接调用 OneBot 协议能力：

| 工具 | 说明 |
|------|------|
| `call_onebot_action` | 调用任意 OneBot Action API，获取 QQ 平台数据（仅管理员可用） |
| `get_raw_message` | 获取当前消息的原始 JSON 数据结构 |
| `send_onebot_msg` | 通过 OneBot API 发送组合/复杂消息（CQ 码字符串或消息段数组） |
| `get_group_member_list` | 获取当前群成员列表，可选返回数量上限（最大 20） |
| `get_group_member_info` | 获取当前群内指定用户的信息 |

## 安装

将本插件放置于 AstrBot 的插件目录下即可，无需额外配置：

```
data/plugins/onebot_toolkit/
```

重启 AstrBot 后自动加载。

## 工具说明

### call_onebot_action

调用 OneBot 协议的任意 Action API。

- **权限**：仅机器人管理员可用
- **参数**：
  - `action` (string)：Action 名称，如 `get_friend_list`、`send_group_msg`
  - `params` (object)：该 Action 的参数对象，无参数时传 `{}`
- **返回**：JSON 格式响应（缩进 4 空格，保留中文）

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
  - `limit` (integer, 可选)：返回成员数量上限，最大 20，默认 20
- **返回**：JSON 格式，包含 `group_id`、`total`（群总人数）、`returned`（实际返回数）、`members`（成员列表）

### get_group_member_info

获取当前群内指定用户的信息，仅在群聊场景下可用。

- **参数**：
  - `user_id` (integer)：目标用户的 QQ 号
- **返回**：JSON 格式，包含该用户在群内的昵称、角色、入群时间等信息

## 环境要求

- AstrBot（或兼容框架）
- OneBot 协议实现（如 NapCat）
- 平台：aiocqhttp（QQ）

## License

MIT
