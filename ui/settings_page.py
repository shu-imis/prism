"""全局设置

与「项目列表」「工作区」平级。
- LLM 配置：所有 AI 功能（Step1 文档分析、Step2 行为体生成、Step3 仿真、
  Step4 结果分析）统一使用此处选中的厂商配置。
- 仿真参数：仿真轮次、行为体决策温度。
配置持久化到 .env，保存后当前进程立即生效。
"""
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config import app_config
from llm.client import LLMProvider, ProviderSettings
from llm.config import (
    PRESETS,
    check_provider,
    get_active_vendor,
    load_vendor_state,
    persist_env_vars,
    persist_vendor_state,
)
from ui.ai_worker import run_ai_task
from ui.styles import *
from ui.widgets import (
    Caption,
    Card,
    DecimalInput,
    GhostBtn,
    Input,
    NumberInput,
    PrimaryBtn,
    SegmentedControl,
    Title,
)


class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._vendor_state: dict[int, dict[str, str]] = {}
        self._provider_index = 0
        self._build()
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, PAD_XL, 0, PAD_XL)
        layout.setSpacing(PAD_LG)

        # --- 页头（与「项目列表」一致，保存为页面级主操作） ---
        hdr = QHBoxLayout()
        hdr.setContentsMargins(PAD_XL, 0, PAD_XL, 0)
        hdr.addWidget(Title("设置", 18))
        hdr.addStretch()
        self._save_btn = PrimaryBtn("保存配置")
        self._save_btn.clicked.connect(self._on_save)
        hdr.addWidget(self._save_btn)
        layout.addLayout(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setContentsMargins(PAD_XL, 0, PAD_XL, 0)
        il.setSpacing(PAD_SM)

        card = Card()
        card.add(Title("LLM 配置", 14))
        card.add(Caption(
            "所有 AI 功能（Step1 文档分析、Step2 行为体生成、Step3 供应链仿真、"
            "Step4 结果分析）统一使用此处选中的厂商。配置保存在 .env 文件中。"
        ))

        self._provider_seg = SegmentedControl(
            [(str(i), p["label"]) for i, p in enumerate(PRESETS)]
        )
        self._provider_seg.valueChanged.connect(
            lambda v: self._on_provider_changed(int(v))
        )
        card.add(self._provider_seg)

        card.add(QLabel("API Key"))
        self._key = Input("API Key")
        self._key.setEchoMode(QLineEdit.Password)
        card.add(self._key)

        card.add(QLabel("Base URL"))
        self._url = Input("Base URL")
        card.add(self._url)

        card.add(QLabel("模型"))
        self._model = Input()
        card.add(self._model)

        # --- 调用参数（高级） ---
        adv = QHBoxLayout()
        adv.setSpacing(PAD_MD)
        adv.addWidget(QLabel("请求超时（秒）"))
        self._request_timeout = NumberInput(
            value=app_config.llm.request_timeout, min_val=5, max_val=180
        )
        adv.addWidget(self._request_timeout)
        adv.addWidget(QLabel("重试次数"))
        self._max_retries = NumberInput(
            value=app_config.llm.max_retries, min_val=0, max_val=5
        )
        adv.addWidget(self._max_retries)
        adv.addStretch()
        card.add_layout(adv)
        card.add(Caption("思考型模型响应较慢，调用超时可适当调大请求超时。"))

        br = QHBoxLayout()
        self._test_btn = GhostBtn("测试连接")
        self._test_btn.clicked.connect(self._on_test)
        br.addWidget(self._test_btn)
        br.addStretch()
        card.add_layout(br)

        self._status = Caption("")
        self._status.setVisible(False)
        card.add(self._status)

        il.addWidget(card)

        # --- 仿真参数 ---
        sim_card = Card()
        sim_card.add(Title("仿真参数", 14))
        sim_card.add(Caption(
            "仿真轮次为每次推演的周期数；决策温度控制行为体输出，"
            "较低更稳定，较高发言更多样。保存后下一次仿真生效。"
        ))
        sr = QHBoxLayout()
        sr.setSpacing(PAD_MD)
        sr.addWidget(QLabel("仿真轮次"))
        self._sim_rounds = NumberInput(
            value=app_config.sim.max_rounds, min_val=4, max_val=24
        )
        sr.addWidget(self._sim_rounds)
        sr.addWidget(QLabel("决策温度"))
        self._decision_temperature = DecimalInput(
            value=app_config.llm.decision_temperature,
            min_val=0.0, max_val=1.0, step=0.05, decimals=2,
        )
        sr.addWidget(self._decision_temperature)
        sr.addStretch()
        sim_card.add_layout(sr)
        il.addWidget(sim_card)

        il.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)

    # --- 配置读写 ---

    def _load(self):
        self._vendor_state = load_vendor_state()
        self._provider_index = get_active_vendor()
        self._provider_seg.set_value(str(self._provider_index))
        self._apply_vendor_state(self._provider_index)

    def _apply_vendor_state(self, index: int):
        if index in self._vendor_state:
            state = self._vendor_state[index]
            self._key.setText(state.get("key", ""))
            self._url.setText(state.get("url", ""))
            self._model.setText(state.get("model", ""))
        else:
            p = PRESETS[index]
            self._key.setText("")
            self._url.setText(p.get("url", ""))
            self._model.setText(p.get("model", ""))

    def _save_current_vendor_state(self):
        self._vendor_state[self._provider_index] = {
            "key": self._key.text().strip(),
            "url": self._url.text().strip(),
            "model": self._model.text().strip(),
        }

    def _on_provider_changed(self, index: int):
        if index == self._provider_index:
            return
        self._save_current_vendor_state()
        self._provider_index = index
        self._apply_vendor_state(index)

    # --- 操作 ---

    def _set_status(self, text: str, is_error: bool = False):
        self._status.setText(text)
        self._status.setStyleSheet(
            f"color:{COLOR_RED if is_error else TEXT_MUTED};"
        )
        self._status.setVisible(bool(text))

    def _on_save(self):
        self._save_current_vendor_state()
        ok_vendor = persist_vendor_state(self._vendor_state, active_vendor=self._provider_index)
        # 仿真参数：写 .env 并同步当前进程配置（下一次仿真生效）
        max_rounds = self._sim_rounds.value()
        decision_temperature = round(self._decision_temperature.value(), 2)
        request_timeout = self._request_timeout.value()
        max_retries = self._max_retries.value()
        ok_vars = persist_env_vars({
            "SIM_MAX_ROUNDS": str(max_rounds),
            "LLM_DECISION_TEMPERATURE": str(decision_temperature),
            "LLM_REQUEST_TIMEOUT": str(request_timeout),
            "LLM_MAX_RETRIES": str(max_retries),
        })
        app_config.sim.max_rounds = max_rounds
        app_config.llm.decision_temperature = decision_temperature
        app_config.llm.request_timeout = request_timeout
        app_config.llm.max_retries = max_retries

        if not (ok_vendor and ok_vars):
            self._set_status(
                "配置已生效，但 .env 写入失败，重启后将丢失", is_error=True
            )
            return
        label = PRESETS[self._provider_index]["label"]
        if self._key.text().strip():
            self._set_status(f"已保存，当前生效厂商：{label}")
        else:
            self._set_status(
                f"已保存，但 {label} 未填写 API Key，AI 功能暂不可用",
                is_error=True,
            )

    def _on_test(self):
        if not self._key.text().strip():
            self._set_status("请先填写 API Key", is_error=True)
            return
        preset = PRESETS[self._provider_index]
        settings = ProviderSettings(
            LLMProvider.ANTHROPIC if preset.get("proto") == "anthropic" else LLMProvider.OPENAI,
            self._model.text().strip() or preset.get("model", ""),
            self._key.text().strip(),
            self._url.text().strip() or preset.get("url", "") or None,
        )
        self._test_btn.setEnabled(False)
        self._set_status("正在测试连接…")
        run_ai_task(
            self,
            lambda: check_provider(settings),
            lambda _reply: self._on_test_done("连接成功，配置可用", False),
            lambda err: self._on_test_done(f"连接失败：{err}", True),
        )

    def _on_test_done(self, msg: str, is_error: bool):
        self._test_btn.setEnabled(True)
        self._set_status(msg, is_error)
