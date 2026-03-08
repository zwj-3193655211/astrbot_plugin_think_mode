"""
astrbot_plugin_think_mode
思考模式切换插件 - 支持 /think 和 /no_think 命令

功能：
- 用户可使用 /think 启用思考模式
- 用户可使用 /no_think 禁用思考模式  
- 默认为非思考模式
- 支持状态查询和持久化
- 支持消息内联命令（如 "你好 /think"）

适用模型：
- Ollama 运行的 Qwen3、DeepSeek-R1 等支持思考的模型
- 通过 API 的 think 参数控制模型是否输出思考过程
"""

import re
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Star, register, Context, StarTools
from astrbot.api import logger, AstrBotConfig


@register("astrbot_plugin_think_mode", "AstrBot", "思考模式切换插件", "1.0.0")
class ThinkModePlugin(Star):
    """思考模式切换插件
    
    通过 Ollama API 的 think 参数控制模型是否输出思考过程。
    支持命令切换和消息内联切换两种方式。
    """
    
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._data_dir = StarTools.get_data_dir(self.name)
        self._state_file = self._data_dir / "think_state.json"
        self._think_mode = self._load_state()
        # 读取配置
        self._default_mode = self.config.get("default_think_mode", False)
        self._global_mode = self.config.get("global_mode", False)
        logger.info(f"[think_mode] 插件已加载，数据目录：{self._data_dir}")
        logger.info(f"[think_mode] 默认思考模式: {'开启' if self._default_mode else '关闭'}")
        logger.info(f"[think_mode] 全局模式: {'开启' if self._global_mode else '关闭'}")
        logger.info(f"[think_mode] 当前已记录 {len(self._think_mode)} 个用户的思考模式状态")

    def _load_state(self) -> dict:
        """从文件加载思考模式状态"""
        if self._state_file.exists():
            try:
                import json
                return json.loads(self._state_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"[think_mode] 加载状态失败：{e}")
        return {}

    def _save_state(self):
        """保存思考模式状态到文件"""
        try:
            import json
            self._state_file.write_text(
                json.dumps(self._think_mode, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"[think_mode] 保存状态失败：{e}")

    def _sanitize_user_id(self, user_id: str) -> str:
        """过滤 user_id，仅保留字母、数字、下划线、连字符"""
        return re.sub(r'[^a-zA-Z0-9_\-]', '_', user_id)

    def _get_user_think_mode(self, user_id: str) -> bool:
        """获取用户当前的思考模式
        
        如果开启了全局模式，则使用配置中的默认值
        否则使用用户的个人设置，无设置时使用默认值
        """
        if self._global_mode:
            return self._default_mode
        user_id = self._sanitize_user_id(user_id)
        return self._think_mode.get(user_id, self._default_mode)

    def _set_user_think_mode(self, user_id: str, mode: bool):
        """设置用户思考模式并持久化"""
        user_id = self._sanitize_user_id(user_id)
        self._think_mode[user_id] = mode
        self._save_state()
        logger.info(f"[think_mode] 用户 {user_id} 思考模式已设置为: {mode}")

    def _parse_think_commands(self, message: str) -> tuple[bool | None, str]:
        """
        解析消息中的思考模式命令
        
        Returns:
            (think_mode, cleaned_message)
            - think_mode: None 表示未检测到命令，True/False 表示检测到对应命令
            - cleaned_message: 移除命令后的消息内容
        """
        think_mode = None
        cleaned_message = message

        # 检测 /think 命令（支持 /think、/Think、/THINK 等变体）
        think_pattern = re.compile(r'/think\b', re.IGNORECASE)
        if think_pattern.search(message):
            think_mode = True
            cleaned_message = think_pattern.sub('', message).strip()

        # 检测 /no_think 命令
        no_think_pattern = re.compile(r'/no_think\b', re.IGNORECASE)
        if no_think_pattern.search(message):
            think_mode = False
            cleaned_message = no_think_pattern.sub('', message).strip()

        return think_mode, cleaned_message

    def _is_ollama_native_provider(self, provider) -> bool:
        """检查是否为 Ollama 原生 Provider
        
        Ollama 原生 API (/api/chat) 支持 think 参数，
        OpenAI 兼容 API (/v1/chat/completions) 不支持。
        """
        if provider is None:
            return False
        
        # 检查 Provider 类型名称
        provider_type = type(provider).__name__
        if provider_type == "ProviderOllamaNative":
            return True
        
        # 检查 provider_config 中的 type
        provider_config = getattr(provider, 'provider_config', {})
        provider_type_name = provider_config.get('type', '')
        if provider_type_name == 'ollama_native':
            return True
        
        return False

    def _is_openai_compatible_ollama(self, provider) -> bool:
        """检查是否为 OpenAI 兼容 API 连接 Ollama
        
        这种情况下 think 参数不生效。
        """
        if provider is None:
            return False
        
        provider_config = getattr(provider, 'provider_config', {})
        api_base = provider_config.get('api_base', '')
        provider_type = provider_config.get('type', '')
        
        # 检查是否使用 OpenAI 兼容 API 连接本地 Ollama
        if provider_type == 'openai_chat_completion':
            if '11434' in api_base and '/v1' in api_base:
                return True
        
        return False

    @filter.on_llm_request()
    async def inject_think_mode(self, event: AstrMessageEvent, req: ProviderRequest):
        """在 LLM 请求前注入思考模式参数
        
        此钩子在每次 LLM 请求前被调用，用于：
        1. 检测消息中的内联命令（/think 或 /no_think）
        2. 检测 Provider 类型并选择合适的注入方式
        3. 对于 Ollama 原生 Provider，通过 custom_extra_body 注入 think 参数
        4. 对于 OpenAI 兼容 API，给出警告（不支持 think 参数）
        """
        user_id = event.get_sender_id()
        message = event.message_str or ""

        # 解析消息中的内联命令
        inline_mode, _ = self._parse_think_commands(message)

        # 如果检测到内联命令，立即更新状态
        if inline_mode is not None:
            self._set_user_think_mode(user_id, inline_mode)
            mode_str = "思考" if inline_mode else "普通"
            logger.info(f"[think_mode] 用户 {user_id} 通过内联命令切换到{mode_str}模式")

        # 获取当前思考模式状态
        current_mode = self._get_user_think_mode(user_id)

        try:
            provider = self.context.get_using_provider(event.unified_msg_origin)
            
            # 检查 Provider 类型
            if self._is_ollama_native_provider(provider):
                # Ollama 原生 API - 支持 think 参数
                if provider and hasattr(provider, 'provider_config'):
                    custom_extra_body = dict(provider.provider_config.get('custom_extra_body', {}))
                    custom_extra_body['think'] = current_mode
                    provider.provider_config['custom_extra_body'] = custom_extra_body
                    logger.info(f"[think_mode] Ollama 原生 API - 已设置 think={current_mode}")
            
            elif self._is_openai_compatible_ollama(provider):
                # OpenAI 兼容 API 连接 Ollama - 不支持 think 参数
                # 只在首次检测时警告
                if not hasattr(self, '_warned_openai_compatible'):
                    self._warned_openai_compatible = True
                    logger.warning(
                        "[think_mode] 检测到使用 OpenAI 兼容 API (/v1) 连接 Ollama，"
                        "该端点不支持 think 参数！思考模式切换将不生效。\n"
                        "请在配置中将 Provider 类型从 'openai_chat_completion' 改为 'ollama_native'，"
                        "并将 api_base 从 'http://127.0.0.1:11434/v1' 改为 'http://127.0.0.1:11434'"
                    )
                
                # 仍然尝试设置（以防万一某些版本支持）
                if provider and hasattr(provider, 'provider_config'):
                    custom_extra_body = dict(provider.provider_config.get('custom_extra_body', {}))
                    custom_extra_body['think'] = current_mode
                    provider.provider_config['custom_extra_body'] = custom_extra_body
                    logger.debug(f"[think_mode] OpenAI 兼容 API - 尝试设置 think={current_mode}（可能不生效）")
            
            else:
                # 其他 Provider - 尝试设置 think 参数
                if provider and hasattr(provider, 'provider_config'):
                    custom_extra_body = dict(provider.provider_config.get('custom_extra_body', {}))
                    custom_extra_body['think'] = current_mode
                    provider.provider_config['custom_extra_body'] = custom_extra_body
                    logger.debug(f"[think_mode] 已设置 custom_extra_body = {custom_extra_body}")
                    
        except Exception as e:
            logger.error(f"[think_mode] 设置 Provider custom_extra_body 失败: {e}")

        # 通过系统提示注入思考模式标记（作为备选方案）
        # 部分模型支持通过提示中的 /think /no_think 标记切换模式
        if current_mode:
            think_marker = "\n\n/think"
        else:
            think_marker = "\n\n/no_think"
        
        req.system_prompt = (req.system_prompt or "") + think_marker

        logger.debug(f"[think_mode] 用户 {user_id} 思考模式: {current_mode}")

    @filter.command("think")
    async def cmd_think(self, event: AstrMessageEvent):
        """启用思考模式
        
        启用后，支持思考的模型（如 Qwen3、DeepSeek-R1）会在回答前进行深度思考，
        输出推理过程，然后给出最终回答。
        """
        user_id = event.get_sender_id()
        self._set_user_think_mode(user_id, True)
        yield event.plain_result(
            "✅ 已启用思考模式\n\n"
            "模型会在回答前进行深度思考，展示推理过程。\n"
            "使用 /no_think 可关闭思考模式。"
        )

    @filter.command("no_think")
    async def cmd_no_think(self, event: AstrMessageEvent):
        """禁用思考模式（默认）
        
        禁用后，模型将直接给出回答，不展示思考过程。
        这是默认状态。
        """
        user_id = event.get_sender_id()
        self._set_user_think_mode(user_id, False)
        yield event.plain_result(
            "✅ 已禁用思考模式\n\n"
            "模型将直接回答，不展示思考过程。\n"
            "使用 /think 可开启思考模式。"
        )

    @filter.command("think_status")
    async def cmd_status(self, event: AstrMessageEvent):
        """查询当前思考模式状态"""
        user_id = event.get_sender_id()
        current_mode = self._get_user_think_mode(user_id)
        
        if current_mode:
            status = "🧠 思考模式（已启用）"
            desc = "模型会先思考再回答，展示推理过程"
        else:
            status = "💬 普通模式（默认）"
            desc = "模型直接回答，不展示思考过程"
        
        yield event.plain_result(
            f"当前状态：{status}\n"
            f"{desc}\n\n"
            f"可用命令：\n"
            f"• /think - 启用思考模式\n"
            f"• /no_think - 禁用思考模式\n"
            f"• /think_status - 查询当前状态\n\n"
            f"也可以在消息中直接使用 /think 或 /no_think 切换模式。"
        )

    async def terminate(self):
        """插件卸载时保存状态"""
        self._save_state()
        logger.info("[think_mode] 插件已卸载，状态已保存")