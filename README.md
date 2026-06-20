# OneBot 协议工具箱

为 LLM 暴露 OneBot（NapCat）原生能力的 AstrBot 插件。

## 功能

为 LLM 提供五个工具，让其能够直接调用 OneBot 协议能力：

| 工具 | 说明 |
|------|------|
| `call_onebot_action` | 调用任意 OneBot Action API，支持返回数量限制与禁用动作过滤（管理员可用） |
| `get_raw_message` | 获取当前消息的原始 JSON 数据结构 |
| `send_onebot_msg` | 通过 OneBot API 发送组合/复杂消息（CQ 码字符串或消息段数组） |
| `get_group_member_list` | 获取当前群成员列表，可选返回数量上限（最大 20） |
| `get_group_member_info` | 获取当前群内指定用户的信息 |

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
| 非管理员禁用的动作 | list | 见下方 | 非管理员禁用的动作列表（白名单模式：未禁用的动作才允许调用，OneBot 新增的未列出动作默认拒绝）。管理员不受限制 |

### 可禁用的动作列表

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

### 默认禁用的动作（非管理员，即白名单中不允许的动作）

以下动作对非管理员禁用，其余动作允许。OneBot 若新增未列出的动作，默认对非管理员拒绝。

群组踢人、群组单人禁言、群组全员禁言、设置群管理员、退出群组、处理加好友请求、发送好友赞、处理加群请求/邀请、获取Cookies、获取CSRF Token、获取QQ相关凭证、重启OneBot、清理缓存、设置群名片、设置群名称、设置群专属头衔、获取合并转发消息、获取陌生人信息、获取好友列表、获取群列表、获取插件运行状态、获取版本信息

## 工具说明

### call_onebot_action

调用 OneBot 协议的任意 Action API。

- **权限**：仅机器人管理员可用（可通过配置开放给非管理员）
- **参数**：
  - `action` (string)：Action 名称，如 `get_friend_list`、`send_group_msg`
  - `params` (object)：该 Action 的参数对象，无参数时传 `{}`
  - `limit` (number, 可选)：如果结果是列表，设置返回的最大数量，防止内容过多。默认 20，传 -1 表示无限制
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

## 环境要求

- AstrBot（或兼容框架）
- OneBot 协议实现（如 NapCat）
- 平台：aiocqhttp（QQ）

## License

MIT
