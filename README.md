# AstrBot 思考模式切换插件

控制 Ollama 模型的思考模式，支持 `/think` 和 `/no_think` 命令切换。

## 功能

- 用户可使用 `/think` 启用思考模式
- 用户可使用 `/no_think` 禁用思考模式
- 默认为非思考模式
- 支持状态查询和持久化
- 支持消息内联命令（如 `你好 /think`）

## 适用模型

- Ollama 运行的 Qwen3、DeepSeek-R1 等支持思考的模型
- 通过在系统提示中注入 `/think` 或 `/no_think` 标记控制模型思考行为

## 安装

### 方式一：通过 WebUI 安装

在 AstrBot WebUI 的插件市场，输入仓库地址安装：

```
git@github.com:zwj-3193655211/astrbot_plugin_think_mode.git
```

### 方式二：手动安装

将本项目克隆到 AstrBot 的 `data/plugins/` 目录下：

```bash
cd AstrBot/data/plugins
git clone git@github.com:zwj-3193655211/astrbot_plugin_think_mode.git
```

重启 AstrBot 或在 WebUI 中重载插件。

## 使用方法

| 命令 | 功能 |
|------|------|
| `/think` | 启用思考模式 |
| `/no_think` | 禁用思考模式（默认） |
| `/think_status` | 查询当前状态 |

### 内联使用

也可以在消息中直接使用，如：

```
帮我分析这个问题 /think
```

这会临时切换到思考模式并处理当前请求。

## 工作原理

1. **状态存储**：按用户 ID 存储，持久化到 `data/plugin_data/astrbot_plugin_think_mode/think_state.json`
2. **注入方式**：
   - 通过修改 Provider 的 `custom_extra_body` 配置注入 `think` 参数（适用于 Ollama API）
   - 同时在系统提示中注入 `/think` 或 `/no_think` 标记（作为备选方案）
3. **默认状态**：非思考模式（`think: false`）

## 注意事项

- **适用 Provider**：Ollama（通过 OpenAI 兼容 API）
- **适用模型**：Qwen3、DeepSeek-R1 等支持思考的模型
- 该插件会动态修改 Provider 的 `custom_extra_body` 配置

## 配置

可在 `_conf_schema.json` 中配置默认思考模式。

## 许可证

MIT License
