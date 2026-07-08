#!/usr/bin/env python3
import importlib
import sys
import types
import unittest


class DummyFilter:
    class PermissionType:
        ADMIN = "ADMIN"

    def llm_tool(self, *args, **kwargs):
        return lambda fn: fn

    def command(self, *args, **kwargs):
        return lambda fn: fn

    def permission_type(self, *args, **kwargs):
        return lambda fn: fn


def install_astrbot_stubs():
    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    event = types.ModuleType("astrbot.api.event")
    event.filter = DummyFilter()
    api_all = types.ModuleType("astrbot.api.all")
    api_all.Star = object
    api_all.Context = object
    api_all.AstrBotConfig = dict
    api_all.logger = types.SimpleNamespace(warning=lambda *args, **kwargs: None)
    aiocqhttp = types.ModuleType(
        "astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event"
    )

    class AiocqhttpMessageEvent:
        pass

    aiocqhttp.AiocqhttpMessageEvent = AiocqhttpMessageEvent

    sys.modules["astrbot"] = astrbot
    sys.modules["astrbot.api"] = api
    sys.modules["astrbot.api.event"] = event
    sys.modules["astrbot.api.all"] = api_all
    sys.modules["astrbot.core"] = types.ModuleType("astrbot.core")
    sys.modules["astrbot.core.platform"] = types.ModuleType("astrbot.core.platform")
    sys.modules["astrbot.core.platform.sources"] = types.ModuleType(
        "astrbot.core.platform.sources"
    )
    sys.modules["astrbot.core.platform.sources.aiocqhttp"] = types.ModuleType(
        "astrbot.core.platform.sources.aiocqhttp"
    )
    sys.modules[
        "astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event"
    ] = aiocqhttp
    return AiocqhttpMessageEvent


AiocqhttpMessageEvent = install_astrbot_stubs()
plugin_main = importlib.import_module("main")


class NonAdminEvent(AiocqhttpMessageEvent):
    def is_admin(self):
        return False


class PermissionTest(unittest.TestCase):
    def test_actionless_tools_respect_admin_only_default(self):
        plugin = object.__new__(plugin_main.OneBotToolkit)
        plugin._仅管理员可用 = True
        plugin._允许的列表 = set()

        err = plugin._check_permission(NonAdminEvent())

        self.assertEqual(err, "⚠️ 管理员设置了权限，当前用户无权限")


if __name__ == "__main__":
    unittest.main()
