"""人设注册表测试。

回归点：人设以前散在三处硬编码（接口的中文描述、守护进程的英文预设、任务里的兜底默认值），
所以"界面里选的人设传不到对话引擎"、也没法自定义。现在统一走 personas 注册表。
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.api import routes
from app.services.conversation import personas


class PersonaRegistryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.custom_file = Path(self._tmp.name) / "personas.json"
        self._patches = [
            patch.object(personas, "CUSTOM_FILE", self.custom_file),
            patch.object(personas, "SESSION_DIR", Path(self._tmp.name)),
        ]
        for item in self._patches:
            item.start()

    def tearDown(self):
        for item in reversed(self._patches):
            item.stop()
        self._tmp.cleanup()

    def test_builtins_are_listed_and_marked(self):
        keys = [p["key"] for p in personas.list_personas()]
        self.assertEqual(keys[:4], ["designer", "trader", "student", "business"])
        self.assertTrue(all(p["builtin"] for p in personas.list_personas()[:4]))

    def test_create_custom_persona(self):
        created = personas.upsert_custom_persona(
            {
                "name": "Nguyen Van B",
                "desc": "二手车商，30岁，岘港",
                "tone": "随和、爱开玩笑",
                "age": 30,
                "occupation": "二手车商",
                "location": "Da Nang",
                "backstory": "在岘港做二手车生意，常和外地客户打交道。",
            }
        )
        self.assertEqual(created["key"], "nguyen-van-b")
        self.assertFalse(created["builtin"])
        self.assertTrue(self.custom_file.exists())
        listed = {p["key"]: p for p in personas.list_personas()}
        self.assertIn("nguyen-van-b", listed)
        # 列表里也必须标成"自定义"，否则前端不给删除按钮
        self.assertFalse(listed["nguyen-van-b"]["builtin"])
        self.assertTrue(listed["designer"]["builtin"])

    def test_chinese_name_falls_back_to_custom_key(self):
        created = personas.upsert_custom_persona({"name": "张三"})
        self.assertEqual(created["key"], "custom")
        second = personas.upsert_custom_persona({"name": "李四"})
        self.assertEqual(second["key"], "custom-2")  # 不覆盖前一个

    def test_duplicate_name_gets_unique_key(self):
        first = personas.upsert_custom_persona({"name": "Tester"})
        second = personas.upsert_custom_persona({"name": "Tester"})
        self.assertEqual(first["key"], "tester")
        self.assertEqual(second["key"], "tester-2")

    def test_resolve_persona_config_for_custom_and_builtin(self):
        personas.upsert_custom_persona(
            {
                "name": "Custom Guy",
                "tone": "话少、直接",
                "age": 41,
                "occupation": "维修工",
                "location": "Can Tho",
                "backstory": "在芹苴修手机 10 年。",
            }
        )
        custom = personas.resolve_persona_config("custom-guy")
        self.assertEqual(custom["name"], "Custom Guy")
        self.assertEqual(custom["age"], 41)
        self.assertEqual(custom["tone"], "话少、直接")  # tone 直接当风格用
        self.assertEqual(custom["occupation"], "维修工")

        builtin = personas.resolve_persona_config("designer")
        self.assertEqual(builtin["name"], "Nguyen Van A")
        self.assertEqual(builtin["tone"], "casual, friendly, slightly naive")  # 内置用 style

    def test_unknown_key_falls_back_to_default(self):
        config = personas.resolve_persona_config("does-not-exist")
        self.assertEqual(config, personas.DEFAULT_PERSONA)
        self.assertEqual(personas.resolve_persona_config(None), personas.DEFAULT_PERSONA)

    def test_empty_name_rejected(self):
        with self.assertRaises(ValueError):
            personas.upsert_custom_persona({"name": "   "})

    def test_delete_only_custom(self):
        personas.upsert_custom_persona({"name": "Temporary"})
        self.assertTrue(personas.delete_custom_persona("temporary"))
        self.assertFalse(personas.delete_custom_persona("temporary"))
        self.assertFalse(personas.delete_custom_persona("designer"))  # 内置删不掉

    def test_persona_key_for_account_reads_meta(self):
        meta = Path(self._tmp.name) / "tester_meta.json"
        meta.write_text(json.dumps({"persona": "trader"}), encoding="utf-8")
        self.assertEqual(personas.persona_key_for_account("tester"), "trader")
        self.assertIsNone(personas.persona_key_for_account("no-such-account"))

    def test_corrupt_custom_file_is_ignored(self):
        self.custom_file.write_text("{not json", encoding="utf-8")
        # 坏文件不能把内置预设一起带崩
        self.assertEqual(len(personas.list_personas()), len(personas.BUILTIN_PERSONAS))


class PersonaEndpointTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._patch = patch.object(
            personas, "CUSTOM_FILE", Path(self._tmp.name) / "personas.json"
        )
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def test_create_list_delete_round_trip(self):
        import asyncio

        created = asyncio.run(routes.create_persona({"name": "API Guy", "desc": "测试"}))
        self.assertEqual(created["status"], "created")
        key = created["persona"]["key"]

        listed = asyncio.run(routes.list_personas())["personas"]
        self.assertIn(key, [p["key"] for p in listed])

        deleted = asyncio.run(routes.delete_persona(key))
        self.assertEqual(deleted["status"], "deleted")
        self.assertNotIn(key, [p["key"] for p in asyncio.run(routes.list_personas())["personas"]])

    def test_delete_builtin_returns_404(self):
        import asyncio

        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(routes.delete_persona("designer"))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_create_without_name_returns_400(self):
        import asyncio

        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(routes.create_persona({"desc": "没有名字"}))
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
