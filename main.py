import fnmatch
import json
import re
import time as _time
from pathlib import Path
from astrbot.api.event import filter
from astrbot.api.all import Star, Context, AstrBotConfig, logger, ProviderRequest
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
from astrbot.core.tools.image_generation_tools import (
    GenerateImageTool,
    ListImageGenerationModelsTool,
)
from astrbot.core.tools.image_tools import ImageCaptionTool
from astrbot.core.tools.message_tools import SendMessageToUserTool
from astrbot.core.tools.transcription_tools import TranscribeMediaTool
from astrbot.core.tools.web_search_tools import (
    BaiduWebSearchTool,
    BochaWebSearchTool,
    BraveWebSearchTool,
    ExaGetContentsTool,
    ExaWebSearchTool,
    FirecrawlExtractWebPageTool,
    FirecrawlWebSearchTool,
    TavilyExtractWebPageTool,
    TavilyWebSearchTool,
    normalize_legacy_web_search_config,
)


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

    return re.sub(r"\[CQ:(\w+)([^]]*?)]", _replace, raw_message)

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
        平台设置 = config.get('平台设置', {})
        self.注入系统提示词 = 平台设置.get("注入系统提示词", True)
        self.系统提示词 = 平台设置.get("系统提示词") or "# 平台提醒\n当前消息平台为OneBot平台，可使用OneBot相关工具，平台不支持渲染Markdown文本，请勿将Markdown文本输出到正文"
        ai解答设置 = config.get('AI解答设置') or config  # 嵌套分组缺失时退回平铺旧键，兼容旧配置
        self._ai解答消息条数 = max(1, min(int(ai解答设置.get('AI解答消息条数', 10)), 100))
        self._ai解答模型 = ai解答设置.get('AI解答模型') or ''
        self._ai解答排除工具 = [str(p).strip() for p in (ai解答设置.get('AI解答排除工具') or []) if str(p).strip()]
        self._ai解答系统提示词 = str(ai解答设置.get('AI解答系统提示词') or '').strip()
        self._需要指令触发 = ai解答设置.get("需要指令触发", False)

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AiocqhttpMessageEvent):
        """监听群消息，触发AI解答"""
        if self._需要指令触发:
            return
        if not (text:=event.get_message_str().strip()):
            return
        if not (text.lower().startswith("ai解答 ") or text.lower() == "ai解答"):
            return

        async for result in self.ai解答指令(event):
            yield result

    @filter.on_llm_request()
    async def on_llm_request(self, event: AiocqhttpMessageEvent, req: ProviderRequest):
        """llm请求前按条件注入系统提示词"""
        if not isinstance(event, AiocqhttpMessageEvent):
            return
        if not self.注入系统提示词:
            return
        req.system_prompt += f"\n\n{self.系统提示词}\n\n"

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

    @staticmethod
    def _format_message_line(msg: dict, max_length: int = 50, show_id: bool = False, full_raw: bool = False) -> str:
        """将单条消息格式化为易读的一行文字。full_raw 时直接使用原始 raw_message（含完整 CQ 码），不简化不截断。"""
        nickname = msg.get("sender", {}).get("nickname", "未知")
        card = msg.get("sender", {}).get("card", "")
        display_name = card or nickname
        raw_msg = msg.get("raw_message", "")
        if full_raw:
            text = raw_msg
        else:
            text = _simplify_cq_codes(raw_msg)
            if max_length != -1 and len(text) > max_length:
                text = text[:max_length] + "…"
        if show_id:
            return f"msg_id={msg.get('message_id')};{display_name}：{text}"
        return f"{display_name}：{text}"

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
            show_message_id: bool = False,
            show_raw_message: bool = False
    ) -> str:
        """获取当前群聊近 n 条消息记录，格式化为易读的对话记录。仅在群聊场景下可用。

        Args:
            count(number): 可选。最大条数，默认 20，上限 100。
            minutes(number): 可选。回溯时间范围（分钟），默认 0 不限制。与 count 叠加，先触限先停。
            msg_id(number): 可选。起始消息 ID，从此往前查。默认 0 从最新开始。
            max_length(number): 可选。单条消息最大字符数，超出截断。默认 50，-1 不截断。
            show_message_id(boolean): 可选。是否显示 message_id。默认 false。
            show_raw_message(boolean): 可选。开启后直接输出每条消息的原始 raw_message（含完整 CQ 码信息），不再简化与截断，结果可能会非常长，请在必要时再使用。默认 false。
        """
        err = self._check_permission(event)
        if err:
            return err

        group_id = self._get_group_id(event)
        if not group_id:
            return "⚠️ 当前非群聊场景，无法获取群消息记录"

        count = max(1, min(int(count), 100))
        max_length = int(max_length) if max_length is not None else 50
        minutes = max(0, int(minutes or 0))
        cutoff = int(_time.time()) - minutes * 60 if minutes > 0 else 0

        # NapCat 返回通常是旧→新。
        # 无锚点且无时间过滤时，直接按 count 拉最新窗口，避免“先塞满旧消息就停”。
        if not msg_id and minutes <= 0:
            try:
                result = await event.bot.call_action(
                    "get_group_msg_history",
                    group_id=group_id,
                    count=count,
                    reverseOrder=True,
                )
            except Exception as e:
                return f"❌ 获取群消息记录失败: {str(e)}"

            messages = result.get("messages", []) if isinstance(result, dict) else []
            if not messages:
                return "ℹ️ 没有获取到消息记录"

            # 取最新 count 条，再按时间正序（旧→新）输出，方便 LLM 读对话
            items = sorted(messages, key=lambda x: x.get("time", 0))[-count:]
            lines = [self._format_message_line(msg, max_length, show_message_id, full_raw=show_raw_message) for msg in items]
            return "\n".join(lines)

        # 有锚点 / 时间范围：整页收集后再按时间取最新 count 条，禁止中途按条数早停
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
                mid = msg.get("message_id")
                if mid in collected:
                    continue
                collected[mid] = {
                    "raw_message": msg,
                    "time": msg_time
                }

            if cutoff and chunk_earliest_time < cutoff:
                break
            # 整页收完后再判断；NapCat 返回旧→新，中途按条数早停会拿到最旧消息
            if len(collected) >= count:
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

        # 取最新 count 条，再按时间正序（旧→新）输出
        items = sorted(collected.values(), key=lambda x: x["time"])[-count:]
        lines = [self._format_message_line(it["raw_message"], max_length, show_message_id, full_raw=show_raw_message) for it in items]
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

        items = sorted(collected.values(), key=lambda x: x["time"])[-max_count:]

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
        match = re.search(r"\[CQ:reply,id=(\d+)]", raw_str)
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

        # 无锚点：直接请求count条最新消息，不分页
        if not anchor_msg_id:
            try:
                result = await event.bot.call_action(
                    "get_group_msg_history",
                    group_id=group_id, count=count, reverseOrder=True,
                )
            except Exception:
                return []
            messages = result.get("messages", []) if isinstance(result, dict) else []
            return sorted(messages, key=lambda x: x.get("time", 0))

        # 有锚点：分页获取锚点附近的count条消息
        collected: dict[int, dict] = {}
        current_anchor = None

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

            params = {"group_id": group_id, "count": count, "reverseOrder": True}
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
                mid = msg.get("message_id")
                if mid in collected:
                    continue
                collected[mid] = msg

            # 整页收集后再判断；NapCat 返回旧→新，中途按条数早停会拿到最旧的消息
            if len(collected) >= count:
                break

            new_anchor = chunk_earliest.get("message_seq")
            if new_anchor is None:
                new_anchor = chunk_earliest.get("real_id")
            if new_anchor is None:
                new_anchor = chunk_earliest.get("seq")
            if new_anchor is None:
                new_anchor = chunk_earliest.get("message_id")
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

    def _get_ai解答工具集(self, event: AiocqhttpMessageEvent, exclude: str = ""):
        """获取全部已注册LLM工具与按主配置开启的内置工具，并按配置的通配符模式排除（如 *file*、shell*）"""
        tools = self.context.get_llm_tool_manager().get_full_tool_set()
        self._注入内置工具(event, tools)
        patterns = [p.lower() for p in self._ai解答排除工具]
        for name in [t.name for t in tools.tools]:
            if name == exclude or any(fnmatch.fnmatchcase(name.lower(), p) for p in patterns):
                tools.remove_tool(name)
        return tools

    def _注入内置工具(self, event: AiocqhttpMessageEvent, tools) -> None:
        """内置工具不常驻工具管理器，是正常对话管线在请求装配阶段按开关注入的；
        tool_loop_agent 不走管线装配，这里按同样条件把已开启的内置工具补进工具集。
        注入条件须与 astr_main_agent.py 的 _apply_web_search_tools 等函数保持一致。"""
        tool_mgr = self.context.get_llm_tool_manager()
        cfg = self.context.get_config(umo=event.unified_msg_origin)
        prov_settings = cfg.get("provider_settings", {})
        if not isinstance(prov_settings, dict):
            prov_settings = {}

        if prov_settings.get("web_search", False):
            normalize_legacy_web_search_config(cfg)
            websearch_classes = {
                "tavily": [TavilyWebSearchTool, TavilyExtractWebPageTool],
                "bocha": [BochaWebSearchTool],
                "brave": [BraveWebSearchTool],
                "firecrawl": [FirecrawlWebSearchTool, FirecrawlExtractWebPageTool],
                "baidu_ai_search": [BaiduWebSearchTool],
                "exa": [ExaWebSearchTool, ExaGetContentsTool],
            }
            provider = prov_settings.get("websearch_provider", "tavily")
            for cls in websearch_classes.get(provider, []):
                tools.add_tool(tool_mgr.get_builtin_tool(cls))

        if prov_settings.get("enable_image_generation_tool", False) and self.context.get_all_image_generation_providers():
            tools.add_tool(tool_mgr.get_builtin_tool(GenerateImageTool))
            tools.add_tool(tool_mgr.get_builtin_tool(ListImageGenerationModelsTool))

        if str(prov_settings.get("default_image_caption_provider_id") or "").strip():
            tools.add_tool(tool_mgr.get_builtin_tool(ImageCaptionTool))

        stt_settings = cfg.get("provider_stt_settings", {})
        if isinstance(stt_settings, dict) and stt_settings.get("enable", False) \
                and str(stt_settings.get("provider_id") or "").strip():
            tools.add_tool(tool_mgr.get_builtin_tool(TranscribeMediaTool))

        platform_meta = getattr(event, "platform_meta", None)
        if platform_meta and platform_meta.support_proactive_message:
            tools.add_tool(tool_mgr.get_builtin_tool(SendMessageToUserTool))

    @staticmethod
    def _get_default_provider_id() -> str:
        """未配置专用模型时，读取 cmd_config.json 的全局默认对话模型 ID"""
        config_path = Path(__file__).resolve().parent.parent.parent / "cmd_config.json"
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
        return config.get("provider_settings", {}).get("default_provider_id", "")

    async def _tool_loop_agent_once(
        self, event: AiocqhttpMessageEvent, prompt: str, system_prompt: str = "",
        tools=None,
    ) -> tuple[str, str]:
        """调用配置的模型执行 tool_loop_agent，失败直接抛异常。返回 (text, model_id)"""
        pid = self._ai解答模型 or self._get_default_provider_id()
        resp = await self.context.tool_loop_agent(
            event=event,
            chat_provider_id=pid,
            prompt=prompt,
            system_prompt=system_prompt,
            tools=tools,
        )
        # 核心在模型请求失败时不抛异常，而是返回 role="err" 的响应
        if getattr(resp, "role", "") == "err":
            raise Exception(resp.completion_text or "模型返回错误响应")
        return resp.completion_text or "", pid

    async def _send_forward_result(
        self, event: AiocqhttpMessageEvent, text: str, reply_msg_id: int | None = None,
        bot_name: str = "AI解答",
    ) -> bool:
        """以合并转发方式发送结果，失败回退到普通消息。成功返回True"""
        group_id = self._get_group_id(event)
        if not group_id:
            return False

        nodes = []
        if reply_msg_id:
            nodes.append({"type": "node", "data": {"id": int(reply_msg_id)}})

        bot_qq = event.get_self_id() or "0"
        nodes.append({
            "type": "node",
            "data": {
                "uin": int(bot_qq),
                "name": bot_name,
                "content": [{"type": "text", "data": {"text": text}}],
            },
        })

        try:
            await event.bot.call_action(
                "send_group_forward_msg", group_id=group_id, messages=nodes
            )
            return True
        except Exception as e:
            logger.warning(f"[AI解答] 合并转发失败: {e}，回退普通消息")
            return False

    @filter.command("AI解答", alias={"ai解答"})
    async def ai解答(self, event: AiocqhttpMessageEvent):
        """引用消息则解答该消息相关问题，未引用则分析最近对话。支持参数：数字→获取n条记录；文本→直接提问。可调用工具"""
        if not self._需要指令触发:
            return
        async for result in self.ai解答指令(event):
            yield result

    async def ai解答指令(self, event: AiocqhttpMessageEvent):
        group_id = self._get_group_id(event)
        if not group_id:
            yield event.plain_result("⚠️ AI解答目前仅支持群聊场景")
            event.stop_event()
            return

        # 解析指令参数
        raw_text = event.get_message_str().strip()
        arg = ''.join(raw_text.split(maxsplit=1)[1:] or '')

        # 判断参数类型：数字→消息条数，文本→直接提问
        custom_count = None
        direct_text = None
        if arg:
            try:
                custom_count = int(arg)
                if custom_count < 1:
                    yield event.plain_result(f"消息数过短，已使用默认值：{self._ai解答消息条数}")
                    custom_count = max(custom_count, self._ai解答消息条数)
                if custom_count > 100:
                    yield event.plain_result("消息数量过大，获取最近100条")
                    custom_count = min(custom_count, 100)
            except ValueError:
                direct_text = arg

        count = custom_count if custom_count else self._ai解答消息条数
        reply_id = self._extract_reply_id(event)

        tools = self._get_ai解答工具集(event, exclude="ai_solve")

        try:
            if direct_text:
                mode = "直接提问"
                logger.info(f"[AI解答] 模式={mode} 问题: {direct_text[:50]}")
                yield event.plain_result(f"🔍 AI解答中({mode})，请稍候…")
                result_text, used_model = await self._tool_loop_agent_once(
                    event, direct_text,
                    self._ai解答系统提示词 or "你是一个智能助手，可以使用工具获取信息，请给出详细、准确的解答。当前平台不支持渲染Markdown文本，请勿将Markdown文本输出到正文",
                    tools
                )
                logger.info(f"[AI解答] 完成，使用模型: {used_model}")
                reply_text = f"模型: {used_model}\n\n{result_text}"
                trigger_msg_id = event.message_obj.raw_message.get("message_id")
                if not await self._send_forward_result(event, reply_text, reply_msg_id=trigger_msg_id):
                    yield event.plain_result(reply_text)

            elif reply_id:
                mode = "锚点引用"
                logger.info(f"[AI解答] 模式={mode} 锚点msg_id={reply_id} 获取{count}条上下文")
                messages = await self._fetch_group_messages(event, count, reply_id)
                lines = []
                for msg in messages:
                    line = self._format_message_line(msg, max_length=-1, show_id=True)
                    if str(msg.get("message_id")) == str(reply_id):
                        line = f"【问题锚点】{line}"
                    lines.append(line)
                conversation = "\n".join(lines)
                logger.info(f"[AI解答] 获取到{len(messages)}条消息:\n{conversation}")
                prompt = (
                    f"以下是群聊对话记录（每行格式为 msg_id=消息ID;昵称：消息内容，按时间从早到晚排列）：\n{conversation}\n\n"
                    "请解答标记为【问题锚点】的消息所涉及的问题。"
                    "结合上下文语境，给出详细、准确的解答。"
                    "你可以使用工具搜索资料来辅助解答。"
                )
                system_prompt = self._ai解答系统提示词 or (
                    "你是一个群聊分析助手。用户引用了群聊中的某条消息，"
                    "请结合上下文对话记录，解答该消息所涉及的问题。"
                    "你可以使用工具获取额外信息。"
                    "当前平台不支持渲染Markdown文本，请勿将Markdown文本输出到正文"
                )

                if not messages:
                    yield event.plain_result("ℹ️ 没有获取到消息记录")
                    return

                yield event.plain_result(f"🔍 AI解答中({mode})，请稍候…")
                result_text, used_model = await self._tool_loop_agent_once(
                    event, prompt, system_prompt, tools
                )
                logger.info(f"[AI解答] 完成，使用模型: {used_model}")
                reply_text = f"模型: {used_model}\n\n{result_text}"
                trigger_msg_id = event.message_obj.raw_message.get("message_id")
                if not await self._send_forward_result(event, reply_text, reply_msg_id=trigger_msg_id):
                    yield event.plain_result(reply_text)

            else:
                mode = "最近对话"
                logger.info(f"[AI解答] 模式={mode} 获取最近{count}条消息")
                messages = await self._fetch_group_messages(event, count)
                lines = [self._format_message_line(msg, max_length=-1, show_id=True) for msg in messages]
                conversation = "\n".join(lines)
                logger.info(f"[AI解答] 获取到{len(messages)}条消息:\n{conversation}")
                prompt = (
                    f"以下是群聊最近的对话记录（每行格式为 msg_id=消息ID;昵称：消息内容，按时间从早到晚排列）：\n{conversation}\n\n"
                    "请识别其中可能的问题并给出解答。"
                    "如果没有明确的问题，请总结讨论要点。"
                    "你可以使用工具搜索资料来辅助解答。"
                )
                system_prompt = self._ai解答系统提示词 or (
                    "你是一个群聊分析助手。请分析最近的群聊对话记录，"
                    "识别其中可能的问题并给出解答。"
                    "你可以使用工具获取额外信息。"
                    "当前平台不支持渲染Markdown文本，请勿将Markdown文本输出到正文"
                )

                if not messages:
                    yield event.plain_result("ℹ️ 没有获取到消息记录")
                    return

                yield event.plain_result(f"🔍 AI解答中({mode}，{count}条)，请稍候…")
                result_text, used_model = await self._tool_loop_agent_once(
                    event, prompt, system_prompt, tools
                )
                logger.info(f"[AI解答] 完成，使用模型: {used_model}")
                reply_text = f"模型: {used_model}\n\n{result_text}"
                trigger_msg_id = event.message_obj.raw_message.get("message_id")
                if not await self._send_forward_result(event, reply_text, reply_msg_id=trigger_msg_id):
                    yield event.plain_result(reply_text)

        except Exception as e:
            logger.error(f"[AI解答] 失败: {e}", exc_info=True)
            yield event.plain_result(f"❌ AI解答失败: {e}")
        finally:
            # 必须在 LLM 请求结束后再停止事件传播：核心 agent 会监听事件停止信号并立即中止请求
            event.stop_event()

    @filter.llm_tool(name="ai_solve")
    async def ai_solve(
        self,
        event: AiocqhttpMessageEvent,
        question: str,
        return_result: bool = False,
    ) -> str | None:
        """独立调用AI解答用户问题。会启动独立的agent循环，可使用搜索等工具获取信息，不影响当前对话上下文。

        Args:
            question (string): 要解答的问题。
            return_result (boolean): 可选。true时返回解答结果文本，由你继续处理。false时工具自行发送解答结果并结束对话，你不需要再回复，降低上下文开销。默认false（推荐）。
        """
        # 取工具集，排除自身避免递归
        tools = self._get_ai解答工具集(event, exclude="ai_solve")

        try:
            result_text, used_model = await self._tool_loop_agent_once(
                event, question,
                self._ai解答系统提示词 or "你是一个智能助手，可以使用工具获取信息，请给出详细、准确的解答。当前平台不支持渲染Markdown文本，请勿将Markdown文本输出到正文",
                tools,
            )
        except Exception as e:
            logger.error(f"[ai_solve] 调用失败: {e}", exc_info=True)
            return f"AI解答失败: {e}"

        reply_text = f"模型: {used_model}\n\n{result_text}"

        if return_result:
            return reply_text

        # 自行发送并结束对话
        trigger_msg_id = event.message_obj.raw_message.get("message_id")
        if not await self._send_forward_result(event, reply_text, reply_msg_id=trigger_msg_id):
            await event.send(event.plain_result(reply_text))
        return None
