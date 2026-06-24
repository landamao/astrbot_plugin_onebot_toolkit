import json
import re
import time as _time
from astrbot.api.event import filter
from astrbot.api.all import Star, Context, AstrBotConfig, logger
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent


def _simplify_cq_codes(raw_message: str) -> str:
    """Simplify CQ codes: keep only key params per type, drop url/file_size etc."""

    def _replace(match: re.Match) -> str:
        cq_type = match.group(1)
        params_str = match.group(2) or ""

        params = {}
        if params_str.startswith(","):
            params_str = params_str[1:]
        for part in params_str.split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                params[k] = v

        if cq_type == "image":
            return f"[CQ:image,file={params['file']}]" if "file" in params else "[CQ:image]"
        elif cq_type == "reply":
            return f"[CQ:reply,id={params['id']}]" if "id" in params else "[CQ:reply]"
        elif params:
            first_key = next(iter(params))
            return f"[CQ:{cq_type},{first_key}={params[first_key]}]"
        return f"[CQ:{cq_type}]"

    return re.sub(r"\[CQ:(\w+)([^\]]*?)\]", _replace, raw_message)

class OneBotToolkit(Star):

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)

        禁用的动作 = config.get('非管理员禁用的动作', [])  # 与 _conf_schema.json 的 key 一致

        动作映射 = {
            "发送私聊消息": "send_private_msg",
            "发送群消息": "send_group_msg",
            "发送消息": "send_msg",
            "撤回消息": "delete_msg",
            "获取消息": "get_msg",
            "获取合并转发消息": "get_forward_msg",
            "发送好友赞": "send_like",
            "群组踢人": "set_group_kick",
            "群组单人禁言": "set_group_ban",
            "群组全员禁言": "set_group_whole_ban",
            "设置群管理员": "set_group_admin",
            "设置群名片": "set_group_card",
            "设置群名称": "set_group_name",
            "退出群组": "set_group_leave",
            "设置群专属头衔": "set_group_special_title",
            "处理加好友请求": "set_friend_add_request",
            "处理加群请求/邀请": "set_group_add_request",
            "获取登录号信息": "get_login_info",
            "获取陌生人信息": "get_stranger_info",
            "获取好友列表": "get_friend_list",
            "获取群信息": "get_group_info",
            "获取群列表": "get_group_list",
            "获取群成员信息": "get_group_member_info",
            "获取群成员列表": "get_group_member_list",
            "获取群荣誉信息": "get_group_honor_info",
            "获取Cookies": "get_cookies",
            "获取CSRF Token": "get_csrf_token",
            "获取QQ相关凭证": "get_credentials",
            "获取语音": "get_record",
            "获取图片": "get_image",
            "检查是否可以发送图片": "can_send_image",
            "检查是否可以发送语音": "can_send_record",
            "获取插件运行状态": "get_status",
            "获取版本信息": "get_version_info",
            "重启OneBot": "set_restart",
            "清理缓存": "clean_cache"
        }

        self.允许的列表 = set(动作映射.values())
        for k in 禁用的动作:
            if k in 动作映射:
                self.允许的列表.discard(动作映射[k])
            else:
                logger.warning(f"配置中的禁用动作「{k}」不是有效动作，已忽略")
        self.仅管理员可用 = not bool(config.get('允许非管理员', False))

    @filter.llm_tool(name="call_onebot_action")
    async def call_action(self, event: AiocqhttpMessageEvent, action: str, params: dict, limit: int = 20) -> str:
        """
        调用 OneBot 协议（NapCat）的任意 Action API，获取 QQ 平台数据。

        Args:
            action (string): 要调用的 OneBot Action 名称，例如 "get_friend_list"、"send_group_msg" 等。
            params (object): 该 Action 所需的参数对象，键为参数名，值为对应值。若无参数可不填或传空对象 {}。
            limit(number): 可选，如果结果是列表，设置返回的最大数量，防止内容过多。默认 20，传 -1 表示无限制。
        Returns:
            string: 返回该 Action 的 JSON 格式响应结果（格式化缩进 4 空格）
        """
        if not isinstance(event, AiocqhttpMessageEvent):
            return "⚠️ 当前平台非 OneBot，不可用"
        if not event.is_admin() and self.仅管理员可用:
            return "⚠️ 管理员设置了权限，当前用户无权限"
        if not isinstance(action, str):
            return "❌️ action参数的类型不正确"
        if not event.is_admin() and action not in self.允许的列表:
            return "⚠️ 管理员未允许该动作请求"
        if limit is not None:
            try:
                limit = int(limit)
            except (ValueError, TypeError):
                return "❌️ limit 参数的类型不正确"

        try:
            result = await event.bot.call_action(action, **params)

            # 处理长度限制：兼容三种常见结果形态（-1 表示无限制）
            if limit is not None and limit != -1:
                # 1. 结果本身直接是列表
                if isinstance(result, list):
                    return json.dumps(result[:limit], ensure_ascii=False, indent=4)
                # 2. 标准 OneBot 响应：{status, retcode, data}
                elif isinstance(result, dict) and 'data' in result and isinstance(result['data'], list):
                    truncated = result.copy()
                    truncated['data'] = truncated['data'][:limit]
                    return json.dumps(truncated, ensure_ascii=False, indent=4)
            return json.dumps(result, ensure_ascii=False, indent=4)

        except Exception as e:
            return json.dumps({
                "error": f"调用 Action 失败: {str(e)}",
                "action": action,
                "params": params or {}
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
            limit(number): 可选。返回成员的数量上限，最大 20，默认 20。
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
            user_id(number): 目标用户的 QQ 号。
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

    @filter.llm_tool(name="get_group_msg_history")
    async def get_group_msg_history(
            self,
            event: AiocqhttpMessageEvent,
            count: int = 20,
            message_id: int = 0,
            max_length: int = 50,
            show_message_id: bool = False
    ) -> str:
        """获取当前群聊近 n 条消息记录，格式化为易读的对话记录。仅在群聊场景下可用。

        Args:
            count(number): 可选。获取消息的最大条数，默认 20。
            message_id(number): 可选。起始消息 ID，从此消息往前查。默认 0 表示从最新消息开始。
            max_length(number): 可选。每条消息内容的最大字符数，超出截断并用省略号表示。默认 50，传 -1 表示不截断。建议保持默认值以防止单条消息过长导致输出臃肿。
            show_message_id(boolean): 可选。是否在每条消息前显示其 message_id。默认 false。
        """
        if not isinstance(event, AiocqhttpMessageEvent):
            return "⚠️ 当前平台非 OneBot，不可用"

        raw = event.message_obj.raw_message
        group_id = raw.get("group_id")
        if not group_id:
            return "⚠️ 当前非群聊场景，无法获取群消息记录"

        count = max(1, min(int(count), 100))
        max_length = int(max_length) if max_length is not None else 50

        try:
            params = {"group_id": group_id, "count": count}
            if message_id:
                params["message_id"] = message_id
            result = await event.bot.call_action("get_group_msg_history", **params)
        except Exception as e:
            return f"❌ 获取群消息记录失败: {str(e)}"

        messages = result.get("messages", []) if isinstance(result, dict) else []

        if not messages:
            return "ℹ️ 没有获取到消息记录"

        lines = []
        for msg in messages:
            nickname = msg.get("sender", {}).get("nickname", "未知")
            card = msg.get("sender", {}).get("card", "")
            display_name = card or nickname
            raw_msg = msg.get("raw_message", "")
            simplified = _simplify_cq_codes(raw_msg)
            if max_length != -1 and len(simplified) > max_length:
                simplified = simplified[:max_length] + "…"
            if show_message_id:
                lines.append(f"message_id={msg['message_id']};{display_name}：{simplified}")
            else:
                lines.append(f"{display_name}：{simplified}")

        return "\n".join(lines)

    @filter.llm_tool(name="batch_delete_msg")
    async def batch_delete_msg(
            self,
            event: AiocqhttpMessageEvent,
            message_ids: list[str]
    ) -> str:
        """批量撤回消息。传入多个 message_id，逐条撤回并返回每条的结果。适用于群聊和私聊。

        Args:
            message_ids(array[string]): 要撤回的消息 ID 列表，例如 ["123456", "789012"]。
        """
        if not isinstance(event, AiocqhttpMessageEvent):
            return "⚠️ 当前平台非 OneBot，不可用"
        if not event.is_admin() and self.仅管理员可用:
            return "⚠️ 管理员设置了权限，当前用户无权限"
        if not event.is_admin() and "delete_msg" not in self.允许的列表:
            return "⚠️ 管理员未允许该动作请求"
        if not isinstance(message_ids, list) or not message_ids:
            return "❌ message_ids 必须是非空数组"

        results = []
        success = 0
        for mid in message_ids:
            try:
                await event.bot.call_action("delete_msg", message_id=int(mid))
                results.append(f"✅ message_id={mid} 撤回成功")
                success += 1
            except Exception as e:
                results.append(f"❌ message_id={mid} 撤回失败: {str(e)}")

        summary = f"批量撤回完成：成功 {success}/{len(message_ids)} 条\n" + "\n".join(results)
        return summary

    @filter.llm_tool(name="get_user_recent_msgs")
    async def get_user_recent_msgs(
            self,
            event: AiocqhttpMessageEvent,
            user_id: int,
            minutes: int = 10,
            max_count: int = 20,
            max_length: int = 100
    ) -> str:
        """获取当前群内指定用户最近 n 分钟内的发言记录。仅在群聊场景下可用。

        Args:
            user_id(number): 目标用户的 QQ 号。
            minutes(number): 可选。回溯的时间范围（分钟），默认 10。
            max_count(number): 可选。返回消息的最大条数，默认 20，上限 100。
            max_length(number): 可选。每条消息内容的最大字符数，超出截断用省略号表示。默认 100，传 -1 表示不截断。
        """
        if not isinstance(event, AiocqhttpMessageEvent):
            return "⚠️ 当前平台非 OneBot，不可用"

        raw = event.message_obj.raw_message
        group_id = raw.get("group_id")
        if not group_id:
            return "⚠️ 当前非群聊场景，无法获取群消息记录"

        minutes = max(1, min(int(minutes), 1440))
        max_count = max(1, min(int(max_count), 100))
        max_length = int(max_length) if max_length is not None else 100

        cutoff = int(_time.time()) - minutes * 60
        collected = {}  # 用 dict 去重，key=message_id
        current_anchor = None

        for _ in range(10):
            params = {"group_id": group_id, "count": 100, "reverseOrder": True}
            if current_anchor is not None:
                params["message_seq"] = current_anchor

            try:
                result = await event.bot.call_action("get_group_msg_history", **params)
            except Exception as e:
                if not collected:
                    return f"❌ 获取群消息记录失败: {str(e)}"
                break

            messages = result.get("messages", []) if isinstance(result, dict) else []
            if not messages:
                break

            # 动态检测顺序：比较首尾时间戳
            first_time = messages[0].get("time", 0)
            last_time = messages[-1].get("time", 0)
            if first_time > last_time:
                # 逆序：最新在前
                chunk_earliest = messages[-1]
            else:
                # 正序：最旧在前
                chunk_earliest = messages[0]

            chunk_earliest_time = chunk_earliest.get("time", 0)

            for msg in messages:
                msg_time = msg.get("time", 0)
                if msg_time < cutoff:
                    continue

                sender_id = msg.get("sender", {}).get("user_id") or msg.get("user_id")
                if str(sender_id) != str(user_id):
                    continue

                msg_id = msg.get("message_id")
                if msg_id in collected:
                    continue

                raw_msg = msg.get("raw_message", "")
                simplified = _simplify_cq_codes(raw_msg)
                if max_length != -1 and len(simplified) > max_length:
                    simplified = simplified[:max_length] + "…"
                collected[msg_id] = {
                    "message_id": msg_id,
                    "time": msg_time,
                    "content": simplified
                }

            # 已到达时间边界，停止回溯
            if chunk_earliest_time < cutoff:
                break

            # 提取锚点：message_seq > real_id > seq > message_id
            new_anchor = (
                chunk_earliest.get("message_seq")
                or chunk_earliest.get("real_id")
                or chunk_earliest.get("seq")
                or chunk_earliest.get("message_id")
            )
            if new_anchor is None or (current_anchor is not None and str(new_anchor) == str(current_anchor)):
                break
            current_anchor = new_anchor

        items = sorted(collected.values(), key=lambda x: x["time"], reverse=True)[:max_count]

        if not items:
            return f"ℹ️ 该用户在最近 {minutes} 分钟内没有发言记录"

        lines = [f"[{it['message_id']}] {it['content']}" for it in items]
        header = f"用户 {user_id} 最近 {minutes} 分钟内的发言（共 {len(items)} 条）：\n"
        return header + "\n".join(lines)