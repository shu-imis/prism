from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.agent_factory import AgentFactory
from llm.client import LLMClient, LLMProvider, ProviderSettings, parse_json_object, strip_model_noise
import llm.analysis as llm_analysis
import llm.config as llm_config
from tests.helpers import FakeKeyring, make_json_client


class LLMConfigTests(unittest.TestCase):
    """全链路 AI 集成：全局配置、文档抽取、行为体生成。"""

    def test_llm_json_fallback(self) -> None:
        """验证 LLM 多厂商 fallback 和 JSON 修复解析。"""
        calls: list[str] = []

        def fake_transport(provider, messages, options):
            calls.append(provider.provider.value)
            if provider.provider == LLMProvider.OPENAI:
                raise RuntimeError("temporary outage")
            return 'analysis\n```json\n{"score": 88, "ok": true,}\n```'

        client = LLMClient(
            providers=[
                ProviderSettings(LLMProvider.OPENAI, "gpt-4o-mini", "key"),
                ProviderSettings(LLMProvider.ANTHROPIC, "claude", "key"),
            ],
            max_retries=0,
            transport=fake_transport,
        )

        result = client.chat_json("只返回 JSON", "score")
        self.assertEqual(result["score"], 88)
        self.assertEqual(calls, ["openai", "anthropic"])

    def test_llm_custom_compatible_base_url(self) -> None:
        """验证自定义兼容 API 地址（如 DeepSeek）。"""
        observed = []

        def fake_transport(provider, messages, options):
            observed.append(provider)
            return '{"ok": true}'

        client = LLMClient(
            providers=[
                ProviderSettings(
                    LLMProvider.OPENAI,
                    "deepseek-chat",
                    "key",
                    "https://api.deepseek.com",
                )
            ],
            max_retries=0,
            transport=fake_transport,
        )

        result = client.chat_json("只返回 JSON", "ping")
        self.assertTrue(result["ok"])
        self.assertEqual(observed[0].provider, LLMProvider.OPENAI)
        self.assertEqual(observed[0].model, "deepseek-chat")
        self.assertEqual(observed[0].base_url, "https://api.deepseek.com")

    def test_parse_json_object_tries_all_balanced_candidates(self) -> None:
        """parse_json_object：逐个尝试平衡括号片段，跳过非 JSON 的前置片段。"""
        result = parse_json_object('说明 [见附录] {"a": 1}')
        self.assertEqual(result, {"a": 1})

    def test_clamp_int_handles_infinity(self) -> None:
        """_clamp_int：Infinity/-Infinity/NaN 回退默认值，不抛 OverflowError。"""
        self.assertEqual(llm_analysis._clamp_int(float("inf"), 0, 100, 50), 50)
        self.assertEqual(llm_analysis._clamp_int(float("-inf"), 0, 100, 50), 50)
        self.assertEqual(llm_analysis._clamp_int(float("nan"), 0, 100, 50), 50)

    def test_llm_retry_permanent_error_skips_to_next_provider(self) -> None:
        """4xx 永久性错误（带 status_code）不重试，直接切换下一个厂商。"""
        calls: list[str] = []

        class _StatusError(Exception):
            status_code = 401

        def fake_transport(provider, messages, options):
            calls.append(provider.provider.value)
            if provider.provider == LLMProvider.OPENAI:
                raise _StatusError("invalid api key")
            return '{"ok": true}'

        client = LLMClient(
            providers=[
                ProviderSettings(LLMProvider.OPENAI, "gpt-4o-mini", "key"),
                ProviderSettings(LLMProvider.ANTHROPIC, "claude", "key"),
            ],
            max_retries=3,
            transport=fake_transport,
        )

        result = client.chat_json("只返回 JSON", "ping")
        self.assertTrue(result["ok"])
        # openai 只尝试一次（不重试），随后切到 anthropic
        self.assertEqual(calls, ["openai", "anthropic"])

    def test_llm_retry_after_header_respected(self) -> None:
        """429 限流带 Retry-After 响应头时按头等待（封顶 30s）。"""
        attempts: list[int] = []

        class _RateLimitError(Exception):
            status_code = 429

            class response:
                headers = {"retry-after": "7"}

        def fake_transport(provider, messages, options):
            attempts.append(1)
            if len(attempts) == 1:
                raise _RateLimitError("rate limited")
            return '{"ok": true}'

        client = LLMClient(
            providers=[ProviderSettings(LLMProvider.OPENAI, "gpt-4o-mini", "key")],
            max_retries=1,
            transport=fake_transport,
        )

        with mock.patch("llm.client.time.sleep") as sleep_mock:
            result = client.chat_json("只返回 JSON", "ping")

        self.assertTrue(result["ok"])
        sleep_mock.assert_called_once_with(7.0)

    def test_truncated_response_retried_with_larger_max_tokens(self) -> None:
        """截断重试：SDK 路径报告截断时以 max_tokens=8192 重试一次（仅一次）。"""
        client = LLMClient(
            providers=[ProviderSettings(LLMProvider.OPENAI, "m", "key")],
            max_retries=0,
        )
        seen_max_tokens = []

        def fake_call_sdk(self_, provider, messages, options):
            seen_max_tokens.append(options["max_tokens"])
            # 第一次报告截断，第二次完整（即使再次截断也不会第三次调用）
            return ("部分文本", True) if len(seen_max_tokens) == 1 else ("完整文本", False)

        with mock.patch.object(LLMClient, "_call_sdk", fake_call_sdk):
            result = client.chat("sys", "user")

        self.assertEqual(result, "完整文本")
        self.assertEqual(seen_max_tokens, [4096, 8192])

    def test_strip_model_noise_variants(self) -> None:
        """strip_model_noise：大小写不敏感，兼容 <thinking> 变体。"""
        self.assertEqual(strip_model_noise("<Think>想</Think>结果"), "结果")
        self.assertEqual(strip_model_noise("<thinking>想</thinking>结果"), "结果")
        self.assertEqual(strip_model_noise("<think>想</think>结果"), "结果")

    def test_extract_scenario_rejects_empty_nodes(self) -> None:
        """场景抽取：nodes 为空时抛 ValueError（未能识别供应链节点）。"""
        payload = '{"title": "t", "background": "有背景但无节点", "nodes": []}'
        with self.assertRaises(ValueError):
            llm_analysis.extract_scenario_from_docs(make_json_client(payload), "文档")

    def test_vendor_state_persist_and_reload(self) -> None:
        """厂商配置持久化：key 入钥匙串（.env 不留明文），url/model 入 .env，生效厂商可切换。"""
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            fake = FakeKeyring()
            state = {
                2: {"key": "kimi-key", "url": "https://api.moonshot.cn/v1", "model": "kimi-k2"},
            }
            with mock.patch.dict(os.environ, {}, clear=True), \
                    mock.patch.object(llm_config, "_get_keyring", return_value=fake):
                llm_config.persist_vendor_state(state, active_vendor=2, env_path=env_path)
                env_text = env_path.read_text(encoding="utf-8")
                self.assertIn("KIMI_API_KEY=", env_text)
                self.assertNotIn("kimi-key", env_text)  # 明文不落盘
                self.assertEqual(
                    fake.get_password(llm_config._KEYRING_SERVICE, "KIMI_API_KEY"),
                    "kimi-key",
                )
                self.assertEqual(llm_config.get_active_vendor(), 2)

                reloaded = llm_config.load_vendor_state()
                self.assertEqual(reloaded[2]["key"], "kimi-key")
                self.assertEqual(reloaded[2]["model"], "kimi-k2")

                settings = llm_config.get_active_provider_settings()
                self.assertIsNotNone(settings)
                self.assertEqual(settings.provider, LLMProvider.OPENAI)
                self.assertEqual(settings.api_key, "kimi-key")

    def test_vendor_state_env_fallback_without_keyring(self) -> None:
        """无钥匙串后端时回退本机绑定加密写 .env，不落明文且可解密读回。"""
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            state = {
                2: {"key": "kimi-key", "url": "https://api.moonshot.cn/v1", "model": "kimi-k2"},
            }
            with mock.patch.dict(os.environ, {}, clear=True), \
                    mock.patch.object(llm_config, "_get_keyring", return_value=None), \
                    mock.patch.object(
                        llm_config, "_machine_secret", return_value=b"test-machine-id"
                    ):
                llm_config.persist_vendor_state(state, active_vendor=2, env_path=env_path)
                env_text = env_path.read_text(encoding="utf-8")
                self.assertNotIn("kimi-key", env_text)  # 明文不落盘
                self.assertIn(llm_config._ENC_PREFIX, env_text)

                # 模拟重启：清空进程环境变量，仅从 .env 密文恢复
                with mock.patch.dict(os.environ, {}, clear=True):
                    for line in env_text.splitlines():
                        if line.startswith("KIMI_API_KEY="):
                            os.environ["KIMI_API_KEY"] = line.split("=", 1)[1].strip("'\"")
                    reloaded = llm_config.load_vendor_state()
                    self.assertEqual(reloaded[2]["key"], "kimi-key")

    def test_encrypted_value_migrates_to_keyring(self) -> None:
        """无钥匙串时期写入的 enc:v1: 密文，在钥匙串可用后自动迁入并清空。"""
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            fake = FakeKeyring()
            with mock.patch.object(
                llm_config, "_machine_secret", return_value=b"test-machine-id"
            ):
                ciphertext = llm_config._encrypt_value("kimi-key")
                self.assertIsNotNone(ciphertext)
                with mock.patch.dict(os.environ, {"KIMI_API_KEY": ciphertext}, clear=True), \
                        mock.patch.object(llm_config, "_get_keyring", return_value=fake), \
                        mock.patch.object(
                            llm_config, "_env_path",
                            side_effect=lambda p=None: Path(p) if p else env_path,
                        ):
                    state = llm_config.load_vendor_state()
                    self.assertEqual(state[2]["key"], "kimi-key")
                    self.assertEqual(
                        fake.get_password(llm_config._KEYRING_SERVICE, "KIMI_API_KEY"),
                        "kimi-key",
                    )
                    self.assertEqual(os.environ["KIMI_API_KEY"], "")
                    self.assertNotIn("kimi-key", env_path.read_text(encoding="utf-8"))

    def test_plaintext_key_migrates_to_keyring(self) -> None:
        """.env/环境变量残留的明文 Key 在读取时自动迁入钥匙串并清空明文。"""
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            fake = FakeKeyring()
            with mock.patch.dict(os.environ, {"KIMI_API_KEY": "kimi-key"}, clear=True), \
                    mock.patch.object(llm_config, "_get_keyring", return_value=fake), \
                    mock.patch.object(
                        llm_config, "_env_path",
                        side_effect=lambda p=None: Path(p) if p else env_path,
                    ):
                state = llm_config.load_vendor_state()
                self.assertEqual(state[2]["key"], "kimi-key")
                self.assertEqual(
                    fake.get_password(llm_config._KEYRING_SERVICE, "KIMI_API_KEY"),
                    "kimi-key",
                )
                self.assertEqual(os.environ["KIMI_API_KEY"], "")
                self.assertNotIn("kimi-key", env_path.read_text(encoding="utf-8"))

    def test_build_llm_client_without_key_returns_none(self) -> None:
        """未配置任何 API Key 时 build_llm_client 返回 None（AI 功能降级）。"""
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(llm_config, "_get_keyring", return_value=None):
            self.assertIsNone(llm_config.get_active_provider_settings())
            self.assertIsNone(llm_config.build_llm_client())

    def test_persist_env_vars(self) -> None:
        """persist_env_vars：任意键值写入 .env 并同步当前进程环境变量。"""
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            with mock.patch.dict(os.environ, {}, clear=True):
                llm_config.persist_env_vars(
                    {"SIM_MAX_ROUNDS": "16", "LLM_DECISION_TEMPERATURE": "0.5"},
                    env_path=env_path,
                )
                self.assertEqual(os.environ["SIM_MAX_ROUNDS"], "16")
                env_text = env_path.read_text(encoding="utf-8")
                self.assertIn("SIM_MAX_ROUNDS", env_text)
                self.assertIn("16", env_text)
                self.assertIn("LLM_DECISION_TEMPERATURE", env_text)

    def test_extract_scenario_from_docs_validates_fields(self) -> None:
        """文档抽取：非法节点类型/越界数值被修正，背景为空时报错。"""
        payload = (
            '{"title": "电子产品供应链", "industry": "电子制造", '
            '"background": "以华南制造商为核心的四级供应链。", '
            '"nodes": ['
            '{"name": "芯片供应商", "type": "supplier", "inventory": 80, "lead_time": 2, '
            '"capacity": 100, "cost_index": 52, "downstream": ["制造商"]}, '
            '{"name": "坏节点", "type": "hacker", "inventory": 999, "lead_time": -3, '
            '"capacity": 0, "cost_index": 200}, '
            '{"name": "", "type": "retailer"}], '
            '"initial_inventory": 120, "baseline_cost": -5, "baseline_service_level": 1.5}'
        )
        result = llm_analysis.extract_scenario_from_docs(
            make_json_client(payload), "某电子产品供应链文档内容"
        )

        self.assertEqual(result["title"], "电子产品供应链")
        self.assertEqual(len(result["nodes"]), 2)  # 空名节点被过滤
        bad = result["nodes"][1]
        self.assertEqual(bad["type"], "supplier")  # 非法类型回退
        self.assertEqual(bad["inventory"], 100)    # clamp 到上限
        self.assertEqual(bad["lead_time"], 0)
        self.assertEqual(result["initial_inventory"], 100)
        self.assertEqual(result["baseline_cost"], 0)
        self.assertEqual(result["baseline_service_level"], 1.0)

        with self.assertRaises(ValueError):
            llm_analysis.extract_scenario_from_docs(make_json_client("{}"), "文档")
        with self.assertRaises(ValueError):
            llm_analysis.extract_scenario_from_docs(make_json_client(payload), "")

    def test_generate_agent_config_validates_and_truncates(self) -> None:
        """行为体生成：非法 stance 回退模板默认，7 个行为体齐全，种子事件截断到 3 条。"""
        agents_config = {
            str(i): {"stance": "aggressive", "activity": 0.5, "influence": 1.0, "profile": f"画像{i}"}
            for i in range(1, 8)
        }
        agents_config["1"]["stance"] = "reckless"      # 非法，应回退
        agents_config["2"]["activity"] = 9.9           # 越界，应 clamp
        seeds = [{"content": f"事件{i}", "cycle": i} for i in range(1, 6)]
        payload = json.dumps(
            {"agents_config": agents_config, "seed_events": seeds},
            ensure_ascii=False,
        )

        result = llm_analysis.generate_agent_config(
            make_json_client(payload), {"title": "t", "background": "b", "nodes": []}
        )

        self.assertEqual(len(result["agents_config"]), 7)
        template_1 = AgentFactory.get_template(1)
        self.assertEqual(result["agents_config"]["1"]["stance"], template_1["decision_stance"])
        self.assertEqual(result["agents_config"]["2"]["activity"], 1.0)
        self.assertEqual(len(result["seed_events"]), 3)
        self.assertEqual(result["seed_events"][0]["content"], "事件1")


if __name__ == "__main__":
    unittest.main()
