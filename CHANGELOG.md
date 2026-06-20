# Changelog

## v1.3.0

- 权限模型从黑名单改为白名单：非管理员只能调用允许列表中的动作，OneBot 新增的未列出动作默认拒绝
- 配置 key 对齐为「非管理员禁用的动作」，与 schema 一致

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
