import json
import re
import time as _time
from pathlib import Path
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

        self._动作映射 = {
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

        允许的动作 = config.get('非管理员允许的动作', [])  # 与 _conf_schema.json 的 key 一致

        self._允许的列表 = set()
        for k in 允许的动作:
            if k in self._动作映射:
                self._允许的列表.add(self._动作映射[k])
            else:
                logger.warning(f"配置中的允许动作「{k}」不是有效动作，已忽略")
        self._仅管理员可用 = not bool(config.get('允许非管理员', False))
        self._ai解答消息条数 = max(1, min(int(config.get('AI解答消息条数', 10)), 100))

    def _check_permission(self, event: AiocqhttpMessageEvent, action: str = None) -> str | None:
        """校验平台和权限。通过返回 None，失败返回错误消息。"""
        if not isinstance(event, AiocqhttpMessageEvent):
            return "⚠️ 当前平台非 OneBot，不可用"
        if action is not None:
            if not event.is_admin() and self._仅管理员可用:
                return "⚠️ 管理员设置了权限，当前用户无权限"
            if not event.is_admin() and action not in self._允许的列表:
                return "⚠️ 管理员未允许该动作请求"
        return None

    def _format_message_line(self, msg: dict, max_length: int = 50, show_id: bool = False) -> str:
        """将单条消息格式化为易读的一行文字。"""
        nickname = msg.get("sender", {}).get("nickname", "未知")
        card = msg.get("sender", {}).get("card", "")
        display_name = card or nickname
        raw_msg = msg.get("raw_message", "")
        simplified = _simplify_cq_codes(raw_msg)
        if max_length != -1 and len(simplified) > max_length:
            simplified = simplified[:max_length] + "…"
        if show_id:
            return f"msg_id={msg.get('message_id')};{display_name}：{simplified}"
        return f"{display_name}：{simplified}"

    @staticmethod
    def _get_group_id(event: AiocqhttpMessageEvent) -> int | None:
        """从事件中提取 group_id，私聊时返回 None。"""
        return event.message_obj.raw_message.get("group_id")

    @filter.llm_tool(name="call_onebot_action")
    async def call_action(self, event: AiocqhttpMessageEvent, action: str, params: dict, limit: int = None) -> str:
        """
        调用 OneBot 协议（NapCat）的任意 Action API。

        Args:
            action (string): Action 名称，如 "get_friend_list"。
            params (object): 参数对象，无参数传 {}。
            limit(number): 可选。结果为列表时截取前 N 条，默认不截断。
        """
        err = self._check_permission(event, action)
        if err:
            return err
        if not isinstance(action, str):
            return "❌️ action参数的类型不正确"
        if limit is not None:
            try:
                limit = int(limit)
            except (ValueError, TypeError):
                return "❌️ limit 参数的类型不正确"

        try:
            result = await event.bot.call_action(action, **(params or {}))

            # 处理长度限制：兼容三种常见结果形态
            if limit is not None and limit > 0:
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
        """获取当前消息的原始 JSON 数据。"""
        err = self._check_permission(event)
        if err:
            return err
        try:
            raw = dict(event.message_obj.raw_message)
            return json.dumps(raw, ensure_ascii=False, indent=4)
        except Exception:
            return str(event.get_messages())

    @filter.llm_tool(name="send_onebot_msg")
    async def send_onebot_msg(
            self,
            event: AiocqhttpMessageEvent,
            message_str: str = None,
            message_array: list[dict] = None,
            receive_result: bool = False
    ) -> str | None:
        """使用 OneBot API 发送组合/复杂消息到当前聊天。纯文本请直接返回，禁止使用工具。视频和文件只能单独发。

        Args:
            message_str(string): 可选。CQ 码字符串，如 [CQ:at,qq=xxx]你好[CQ:image,file=/tmp/t.jpg]。
            message_array(array[object]): 可选。消息段数组，如 [{"type":"face","data":{"id":"272"}}]。
            receive_result(boolean): 可选。是否返回发送结果。默认 false，非必要建议保持 false，一次性把内容发完。
        """
        err = self._check_permission(event)
        if err:
            return err

        if message_array:
            message = message_array
        elif message_str:
            message = message_str
        else:
            return "❌ 错误：message_str 和 message_array 不能同时为空，请至少提供一个参数。"

        try:
            raw = event.message_obj.raw_message
            result = await event.bot.call_action(
                "send_msg",
                group_id=raw.get("group_id"),
                user_id=raw.get("user_id"),
                message=message
            )
            if receive_result:
                return f"🚀 消息发送成功，结果：{result}"
            else:
                return None
        except Exception as e:
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
        err = self._check_permission(event)
        if err:
            return err

        group_id = self._get_group_id(event)
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
        err = self._check_permission(event)
        if err:
            return err

        group_id = self._get_group_id(event)
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
            minutes: int = 0,
            msg_id: int = 0,
            max_length: int = 50,
            show_message_id: bool = False
    ) -> str:
        """获取当前群聊近 n 条消息记录，格式化为易读的对话记录。仅在群聊场景下可用。

        Args:
            count(number): 可选。最大条数，默认 20，上限 100。
            minutes(number): 可选。回溯时间范围（分钟），默认 0 不限制。与 count 叠加，先触限先停。
            msg_id(number): 可选。起始消息 ID，从此往前查。默认 0 从最新开始。
            max_length(number): 可选。单条消息最大字符数，超出截断。默认 50，-1 不截断。
            show_message_id(boolean): 可选。是否显示 message_id。默认 false。
        """
        err = self._check_permission(event)
        if err:
            return err

        group_id = self._get_group_id(event)
        if not group_id:
            return "⚠️ 当前非群聊场景，无法获取群消息记录"

        count = max(1, min(int(count), 100))
        max_length = int(max_length) if max_length is not None else 50
        cutoff = int(_time.time()) - minutes * 60 if minutes > 0 else 0

        collected = {}
        current_anchor = msg_id or None
        deadline = _time.monotonic() + 15

        for _ in range(10):
            if _time.monotonic() > deadline:
                break

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

            first_time = messages[0].get("time", 0)
            last_time = messages[-1].get("time", 0)
            chunk_earliest = messages[-1] if first_time > last_time else messages[0]
            chunk_earliest_time = chunk_earliest.get("time", 0)

            for msg in messages:
                msg_time = msg.get("time", 0)
                if cutoff and msg_time < cutoff:
                    continue
                msg_id = msg.get("message_id")
                if msg_id in collected:
                    continue
                collected[msg_id] = {
                    "raw_message": msg,
                    "time": msg_time
                }
                if len(collected) >= count:
                    break

            if len(collected) >= count:
                break
            if cutoff and chunk_earliest_time < cutoff:
                break

            new_anchor = chunk_earliest.get("message_seq")
            if new_anchor is None:
                new_anchor = chunk_earliest.get("real_id")
            if new_anchor is None:
                new_anchor = chunk_earliest.get("seq")
            if new_anchor is None:
                new_anchor = chunk_earliest.get("message_id")
            if new_anchor is None or (current_anchor is not None and str(new_anchor) == str(current_anchor)):
                break
            current_anchor = new_anchor

        if not collected:
            return "ℹ️ 没有获取到消息记录"

        items = sorted(collected.values(), key=lambda x: x["time"], reverse=True)[:count]
        lines = [self._format_message_line(it["raw_message"], max_length, show_message_id) for it in items]
        return "\n".join(lines)

    @filter.llm_tool(name="batch_delete_msg")
    async def batch_delete_msg(
            self,
            event: AiocqhttpMessageEvent,
            message_ids: list[str]
    ) -> str:
        """批量撤回消息。传入多个 message_id，逐条撤回。适用于群聊和私聊。

        Args:
            message_ids(array[string]): 要撤回的消息 ID 列表，例如 ["123456", "789012"]。
        """
        err = self._check_permission(event, "delete_msg")
        if err:
            return err
        if not isinstance(message_ids, list) or not message_ids:
            return "❌ message_ids 必须是非空数组"

        failed = []
        success = 0
        for mid in message_ids:
            try:
                mid_int = int(mid)
            except (ValueError, TypeError):
                failed.append(str(mid))
                continue
            try:
                await event.bot.call_action("delete_msg", message_id=mid_int)
                success += 1
            except Exception:
                failed.append(str(mid))

        parts = [f"撤回成功 {success}/{len(message_ids)} 条"]
        if failed:
            parts.append(f"撤回失败：{', '.join(failed)}")
        return "\n".join(parts)

    @filter.llm_tool(name="get_user_recent_msgs")
    async def get_user_recent_msgs(
            self,
            event: AiocqhttpMessageEvent,
            user_id: int,
            minutes: int = 10,
            max_count: int = 20,
            max_length: int = 50
    ) -> str:
        """获取当前群内指定用户最近 n 分钟内的发言记录。仅在群聊场景下可用。

        Args:
            user_id(number): 目标用户的 QQ 号。
            minutes(number): 可选。回溯时间范围（分钟），默认 10。
            max_count(number): 可选。最大条数，默认 20，上限 100。
            max_length(number): 可选。单条消息最大字符数，超出截断。默认 50，-1 不截断。
        """
        err = self._check_permission(event)
        if err:
            return err

        group_id = self._get_group_id(event)
        if not group_id:
            return "⚠️ 当前非群聊场景，无法获取群消息记录"

        minutes = max(1, min(int(minutes), 1440))
        max_count = max(1, min(int(max_count), 100))
        max_length = int(max_length) if max_length is not None else 50

        cutoff = int(_time.time()) - minutes * 60
        collected = {}  # 用 dict 去重，key=message_id
        current_anchor = None
        deadline = _time.monotonic() + 15  # 15 秒超时保护

        for _ in range(10):
            if _time.monotonic() > deadline:
                break

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
            chunk_earliest = messages[-1] if first_time > last_time else messages[0]
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

                simplified = _simplify_cq_codes(msg.get("raw_message", ""))
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

            # 提取锚点：message_seq > real_id > seq > message_id（用 is None 避免 0 被当作 falsy）
            new_anchor = chunk_earliest.get("message_seq")
            if new_anchor is None:
                new_anchor = chunk_earliest.get("real_id")
            if new_anchor is None:
                new_anchor = chunk_earliest.get("seq")
            if new_anchor is None:
                new_anchor = chunk_earliest.get("message_id")
            if new_anchor is None or (current_anchor is not None and str(new_anchor) == str(current_anchor)):
                break
            current_anchor = new_anchor

        items = sorted(collected.values(), key=lambda x: x["time"], reverse=True)[:max_count]

        if not items:
            return f"ℹ️ 该用户在最近 {minutes} 分钟内没有发言记录"

        lines = [f"msg_id={it['message_id']}：{it['content']}" for it in items]
        header = f"用户 {user_id} 最近 {minutes} 分钟内的发言（共 {len(items)} 条）：\n"
        return header + "\n".join(lines)

    @filter.llm_tool(name="get_msg_content")
    async def get_msg_content(
            self,
            event: AiocqhttpMessageEvent,
            msg_id: int
    ) -> str:
        """通过消息 ID 获取消息内容，返回带 CQ 码的 raw_message 字符串。

        Args:
            msg_id(number): 消息 ID。
        """
        err = self._check_permission(event)
        if err:
            return err

        try:
            result = await event.bot.call_action("get_msg", message_id=int(msg_id))
        except Exception as e:
            return f"❌ 获取消息失败: {str(e)}"

        raw = result.get("raw_message", "") if isinstance(result, dict) else str(result)
        return raw if raw else json.dumps(result, ensure_ascii=False, indent=4)

    # ========== AI解答：独立调用LLM分析群消息 ==========

    @staticmethod
    def _extract_reply_id(event: AiocqhttpMessageEvent) -> int | None:
        """从事件中提取引用消息的ID"""
        raw = event.message_obj.raw_message
        raw_str = raw.get("raw_message", "") if isinstance(raw, dict) else str(raw)
        match = re.search(r"\[CQ:reply,id=(\d+)\]", raw_str)
        return int(match.group(1)) if match else None

    async def _fetch_group_messages(
        self, event: AiocqhttpMessageEvent, count: int, anchor_msg_id: int | None = None
    ) -> list[dict]:
        """获取群消息历史，返回按时间正序排列的消息列表。
        anchor_msg_id: 锚点消息ID，获取包含锚点在内的最近count条消息"""
        group_id = self._get_group_id(event)
        if not group_id:
            return []

        count = max(1, min(count, 100))
        collected: dict[int, dict] = {}
        current_anchor = None

        # Resolve anchor message_seq for paginated fetching
        if anchor_msg_id:
            try:
                anchor = await event.bot.call_action("get_msg", message_id=int(anchor_msg_id))
                current_anchor = (
                    anchor.get("message_seq")
                    or anchor.get("real_id")
                    or anchor.get("seq")
                )
            except Exception:
                pass

        deadline = _time.monotonic() + 15

        for _ in range(10):
            if _time.monotonic() > deadline:
                break

            params = {"group_id": group_id, "count": 100, "reverseOrder": True}
            if current_anchor is not None:
                params["message_seq"] = current_anchor

            try:
                result = await event.bot.call_action("get_group_msg_history", **params)
            except Exception:
                if not collected:
                    return []
                break

            messages = result.get("messages", []) if isinstance(result, dict) else []
            if not messages:
                break

            first_time = messages[0].get("time", 0)
            last_time = messages[-1].get("time", 0)
            chunk_earliest = messages[-1] if first_time > last_time else messages[0]

            for msg in messages:
                msg_id = msg.get("message_id")
                if msg_id in collected:
                    continue
                collected[msg_id] = msg
                if len(collected) >= count:
                    break

            if len(collected) >= count:
                break

            new_anchor = (
                chunk_earliest.get("message_seq")
                or chunk_earliest.get("real_id")
                or chunk_earliest.get("seq")
                or chunk_earliest.get("message_id")
            )
            if new_anchor is None or (
                current_anchor is not None and str(new_anchor) == str(current_anchor)
            ):
                break
            current_anchor = new_anchor

        # If anchor specified but not in results, fetch it separately
        if anchor_msg_id and anchor_msg_id not in collected:
            try:
                anchor = await event.bot.call_action("get_msg", message_id=int(anchor_msg_id))
                collected[anchor.get("message_id", anchor_msg_id)] = anchor
            except Exception:
                pass

        items = sorted(collected.values(), key=lambda x: x.get("time", 0))
        return items[-count:]

    @staticmethod
    def _load_provider_ids() -> tuple[str, list[str]]:
        """Read main provider ID and fallback list from cmd_config.json"""
        config_path = Path(__file__).resolve().parent.parent.parent / "cmd_config.json"
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
        ps = config.get("provider_settings", {})
        return ps.get("default_provider_id", ""), ps.get("fallback_chat_models", [])

    async def _tool_loop_agent_with_fallback(
        self, event: AiocqhttpMessageEvent, prompt: str, system_prompt: str = "",
        tools=None,
    ) -> tuple[str, str]:
        """Call tool_loop_agent with fallback. Returns (text, model_id)"""
        main_id, fallback_ids = self._load_provider_ids()
        all_ids = [main_id] + fallback_ids
        last_error = ""
        for pid in all_ids:
            if not pid:
                continue
            try:
                resp = await self.context.tool_loop_agent(
                    event=event,
                    chat_provider_id=pid,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    tools=tools,
                )
                return resp.completion_text, pid
            except Exception as e:
                last_error = str(e)
                logger.warning(f"[AI解答] 模型 {pid} 调用失败: {last_error}")
                continue
        raise Exception(f"所有模型均调用失败，最后错误: {last_error}")

    @filter.command("AI解答", alias={"ai解答"})
    async def ai解答(self, event: AiocqhttpMessageEvent):
        """引用消息则解答该消息相关问题，未引用则分析最近对话。支持参数：数字→获取n条记录；文本→直接提问。可调用工具"""
        event.stop_event()

        group_id = self._get_group_id(event)
        if not group_id:
            yield event.plain_result("⚠️ AI解答目前仅支持群聊场景")
            return

        # 解析指令参数
        raw_text = event.get_message_str().strip()
        arg = ""
        for prefix in ("/AI解答", "AI解答", "/ai解答", "ai解答"):
            if raw_text.startswith(prefix):
                arg = raw_text[len(prefix):].strip()
                break

        # 判断参数类型：数字→消息条数，文本→直接提问
        custom_count = None
        direct_text = None
        if arg:
            try:
                custom_count = int(arg)
            except ValueError:
                direct_text = arg

        count = custom_count if custom_count else self._ai解答消息条数
        reply_id = self._extract_reply_id(event)

        # 取全部已注册的LLM工具
        tools = self.context.get_llm_tool_manager().get_full_tool_set()

        try:
            if direct_text:
                mode = "直接提问"
                logger.info(f"[AI解答] 模式={mode} 问题: {direct_text[:50]}")
                yield event.plain_result(f"🔍 AI解答中({mode})，请稍候…")
                result_text, used_model = await self._tool_loop_agent_with_fallback(
                    event, direct_text, "你是一个智能助手，可以使用工具获取信息，请给出详细、准确的解答。", tools
                )
                logger.info(f"[AI解答] 完成，使用模型: {used_model}")
                yield event.plain_result(f"模型: {used_model}\n\n{result_text}")

            elif reply_id:
                mode = "锚点引用"
                logger.info(f"[AI解答] 模式={mode} 锚点msg_id={reply_id} 获取{count}条上下文")
                messages = await self._fetch_group_messages(event, count, reply_id)
                lines = []
                for msg in messages:
                    line = self._format_message_line(msg, max_length=-1)
                    if str(msg.get("message_id")) == str(reply_id):
                        line = f"【问题锚点】{line}"
                    lines.append(line)
                conversation = "\n".join(lines)
                prompt = (
                    f"以下是群聊对话记录：\n{conversation}\n\n"
                    "请解答标记为【问题锚点】的消息所涉及的问题。"
                    "结合上下文语境，给出详细、准确的解答。"
                    "你可以使用工具搜索资料来辅助解答。"
                )
                system_prompt = (
                    "你是一个群聊分析助手。用户引用了群聊中的某条消息，"
                    "请结合上下文对话记录，解答该消息所涉及的问题。"
                    "你可以使用工具获取额外信息。"
                )

                if not messages:
                    yield event.plain_result("ℹ️ 没有获取到消息记录")
                    return

                yield event.plain_result(f"🔍 AI解答中({mode})，请稍候…")
                logger.info(f"[AI解答] 获取到{len(messages)}条消息，开始调用LLM")
                result_text, used_model = await self._tool_loop_agent_with_fallback(
                    event, prompt, system_prompt, tools
                )
                logger.info(f"[AI解答] 完成，使用模型: {used_model}")
                yield event.plain_result(f"模型: {used_model}\n\n{result_text}")

            else:
                mode = "最近对话"
                logger.info(f"[AI解答] 模式={mode} 获取最近{count}条消息")
                messages = await self._fetch_group_messages(event, count)
                lines = [self._format_message_line(msg, max_length=-1) for msg in messages]
                conversation = "\n".join(lines)
                prompt = (
                    f"以下是群聊最近的对话记录：\n{conversation}\n\n"
                    "请识别其中可能的问题并给出解答。"
                    "如果没有明确的问题，请总结讨论要点。"
                    "你可以使用工具搜索资料来辅助解答。"
                )
                system_prompt = (
                    "你是一个群聊分析助手。请分析最近的群聊对话记录，"
                    "识别其中可能的问题并给出解答。"
                    "你可以使用工具获取额外信息。"
                )

                if not messages:
                    yield event.plain_result("ℹ️ 没有获取到消息记录")
                    return

                yield event.plain_result(f"🔍 AI解答中({mode}，{count}条)，请稍候…")
                logger.info(f"[AI解答] 获取到{len(messages)}条消息，开始调用LLM")
                result_text, used_model = await self._tool_loop_agent_with_fallback(
                    event, prompt, system_prompt, tools
                )
                logger.info(f"[AI解答] 完成，使用模型: {used_model}")
                yield event.plain_result(f"模型: {used_model}\n\n{result_text}")

        except Exception as e:
            logger.error(f"[AI解答] 失败: {e}", exc_info=True)
            yield event.plain_result(f"❌ AI解答失败: {e}")