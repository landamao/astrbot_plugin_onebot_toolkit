import json
from astrbot.api.event import filter
from astrbot.api.all import Star
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent

class OneBotToolkit(Star):

    @filter.llm_tool(name="call_onebot_action")
    async def call_action(self, event: AiocqhttpMessageEvent, action: str, params: dict) -> str:
        """
        调用 OneBot 协议（NapCat）的任意 Action API，获取 QQ 平台数据。

        Args:
            action (string): 要调用的 OneBot Action 名称，例如 "get_friend_list"、"send_group_msg" 等。
            params (object): 该 Action 所需的参数对象，键为参数名，值为对应值。若无参数可传空对象 {}。

        Returns:
            string: 返回该 Action 的 JSON 格式响应结果（格式化缩进 4 空格），便于后续 LLM 解析。
        """
        # 平台与权限校验（保留原逻辑）
        if not isinstance(event, AiocqhttpMessageEvent):
            return "⚠️ 当前平台非 OneBot，不可用"
        if not event.is_admin():
            return "⚠️ 仅可协助机器人管理员使用此工具，该发送者非机器人管理员"

        try:
            # 调用底层 OneBot Action
            result = await event.bot.call_action(action, **params)
            # 返回 JSON 字符串（中文保留，格式化缩进）
            return json.dumps(result, ensure_ascii=False, indent=4)
        except Exception as e:
            # 异常时返回错误信息，LLM 也能理解
            return json.dumps({
                "error": f"调用 Action 失败: {str(e)}",
                "action": action,
                "params": params
            }, ensure_ascii=False, indent=4)

    @filter.llm_tool(name="get_raw_message")
    async def get_raw_message(self, event: AiocqhttpMessageEvent) -> str:
        """获取当前消息的原始 json 信息，当你想查看消息的底层底层数据结构或详细元数据时使用。"""
        try:
            raw = dict(event.message_obj.raw_message)  # 尝试转换dict，如果平台支持
            return json.dumps(raw, ensure_ascii=False, indent=4)
        except Exception:
            return str(event.get_messages())  # 不行则返回框架消息链

    @filter.llm_tool(name="send_onebot_msg")
    async def send_onebot_msg(
            self,
            event: AiocqhttpMessageEvent,
            message_str: str = None,
            message_array: list[dict] = None,
            receive_result: bool = False
    ) -> str | None:
        """使用 OneBot API 发送组合/复杂消息到当前聊天。

        纯文本消息请直接返回，禁止使用工具。注意，视频和文件只能单独发，无法与其他混在一起。

        Args:
            message_str(string): 可选。要发送的 CQ 码字符串（如 [CQ:at,qq=xxx]这是你想要的图[CQ:image,file=/tmp/t.jpg][CQ:face,id=272]）。
            message_array(array[object]): 可选。OneBot API 的消息段数组，例如 [{"type": "face", "data": {"id": "272"}}]。
            receive_result(boolean): 可选。是否接收发送成功的反馈。默认值为 false（成功后直接结束对话，无需追加回复，建议一次性就把东西发完，减少重复请求/调用）。如果需要继续向用户汇报，才设为 true。
        """
        if not isinstance(event, AiocqhttpMessageEvent):
            return "⚠️ 当前平台非 OneBot，不可用"

        # 1. 选择参数
        if message_array:
            message = message_array
        elif message_str:
            message = message_str
        else:
            return "❌ 错误：message_str 和 message_array 不能同时为空，请至少提供一个参数。"

        # 2. 调用 OneBot API 发送
        raw = event.message_obj.raw_message
        try:
            result = await event.bot.call_action(
                "send_msg",
                group_id=raw.get("group_id"),  # 为 None 则自动发送私聊消息
                user_id=raw.get("user_id"),
                message=message
            )

            # 默认返回 None，大模型执行完该工具后直接闭嘴，不再继续回复
            if receive_result:
                return f"🚀 消息发送成功，结果：{result}"
            else:
                return None

        except Exception as e:
            # 失败时始终返回错误信息，确保大模型知情
            return f"❌ 消息发送失败，错误信息：{str(e)}"

    @filter.llm_tool(name="get_group_member_list")
    async def get_group_member_list(
            self,
            event: AiocqhttpMessageEvent,
            limit: int = 20
    ) -> str:
        """获取当前群的成员列表。仅在群聊场景下可用。

        Args:
            limit(integer): 可选。返回成员的数量上限，最大 20，默认 20。
        """
        if not isinstance(event, AiocqhttpMessageEvent):
            return "⚠️ 当前平台非 OneBot，不可用"

        raw = event.message_obj.raw_message
        group_id = raw.get("group_id")
        if not group_id:
            return "⚠️ 当前非群聊场景，无法获取群成员列表"

        limit = max(1, min(limit, 20))

        try:
            result = await event.bot.call_action("get_group_member_list", group_id=group_id)
            members = result[:limit] if isinstance(result, list) else result
            summary = {
                "group_id": group_id,
                "total": len(result) if isinstance(result, list) else None,
                "returned": len(members) if isinstance(members, list) else None,
                "members": members
            }
            return json.dumps(summary, ensure_ascii=False, indent=4)
        except Exception as e:
            return json.dumps({
                "error": f"获取群成员列表失败: {str(e)}",
                "group_id": group_id
            }, ensure_ascii=False, indent=4)

    @filter.llm_tool(name="get_group_member_info")
    async def get_group_member_info(
            self,
            event: AiocqhttpMessageEvent,
            user_id: int
    ) -> str:
        """获取当前群内指定用户的信息。

        Args:
            user_id(integer): 目标用户的 QQ 号。
        """
        if not isinstance(event, AiocqhttpMessageEvent):
            return "⚠️ 当前平台非 OneBot，不可用"

        raw = event.message_obj.raw_message
        group_id = raw.get("group_id")
        if not group_id:
            return "⚠️ 当前非群聊场景，无法获取群成员信息"

        try:
            result = await event.bot.call_action(
                "get_group_member_info",
                group_id=group_id,
                user_id=user_id,
                no_cache=False
            )
            return json.dumps(result, ensure_ascii=False, indent=4)
        except Exception as e:
            return json.dumps({
                "error": f"获取群成员信息失败: {str(e)}",
                "group_id": group_id,
                "user_id": user_id
            }, ensure_ascii=False, indent=4)