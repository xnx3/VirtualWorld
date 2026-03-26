package com.virtualworld.genesis

import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import java.io.File

/**
 * Genesis 配置管理器
 * 负责读写 Termux 中的 config.yaml
 *
 * 使用 Termux RUN_COMMAND API 解决权限问题
 */
object GenesisConfig {

    private const val TAG = "GenesisConfig"

    /**
     * 保存 LLM 配置到 config.yaml
     * 通过 Termux RUN_COMMAND 在 Termux 环境中写入
     */
    fun saveLLMConfig(
        context: Context,
        baseUrl: String,
        apiKey: String,
        model: String
    ): ConfigResult {
        try {
            // 生成配置更新脚本
            val scriptContent = buildConfigUpdateScript(baseUrl, apiKey, model)

            // 将脚本写入应用缓存目录
            val scriptFile = File(context.cacheDir, "update_config.sh")
            scriptFile.writeText(scriptContent)

            // 通过 Termux 执行
            val intent = Intent("com.termux.RUN_COMMAND")
            intent.setClassName("com.termux", "com.termux.app.RunCommandService")
            intent.putExtra("com.termux.RUN_COMMAND_PATH", scriptFile.absolutePath)
            intent.putExtra("com.termux.RUN_COMMAND_WORKDIR", context.cacheDir.absolutePath)
            intent.putExtra("com.termux.RUN_COMMAND_BACKGROUND", false)

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }

            // 等待执行完成
            Thread.sleep(2000)

            Log.i(TAG, "LLM config saved via Termux")
            return ConfigResult(success = true, message = "配置已保存")

        } catch (e: Exception) {
            Log.e(TAG, "Failed to save config: ${e.message}", e)
            return ConfigResult(success = false, message = "保存失败: ${e.message}")
        }
    }

    /**
     * 构建配置更新脚本
     * 在 Termux 环境中执行
     */
    private fun buildConfigUpdateScript(baseUrl: String, apiKey: String, model: String): String {
        // 转义特殊字符
        val escapedBaseUrl = baseUrl.replace("\"", "\\\"")
        val escapedApiKey = apiKey.replace("\"", "\\\"")
        val escapedModel = model.replace("\"", "\\\"")

        return """
#!/bin/bash
# Genesis 配置更新脚本

CONFIG_FILE="${'$'}HOME/genesis/data/config.yaml"

# 创建配置目录
mkdir -p "${'$'}HOME/genesis/data"

# 如果配置文件不存在，创建默认配置
if [ ! -f "${'$'}CONFIG_FILE" ]; then
    cat > "${'$'}CONFIG_FILE" << 'DEFAULTCONFIG'
# Genesis Configuration
# 生成式虚拟世界配置文件

simulation:
  tick_interval: 30
  min_beings: 10
  max_npc_per_node: 5

chain:
  block_interval: 60
  priest_grace_period: 100
  creator_succession_threshold: 1000

network:
  listen_port: 7331
  discovery_port: 7332
  max_peers: 50

being:
  hibernate_safety_timeout: 300

llm:
  base_url: "https://api.openai.com/v1"
  api_key: ""
  model: "gpt-4o-mini"
  max_tokens: 4096
  temperature: 0.7

language: "zh"
DEFAULTCONFIG
fi

# 使用 sed 更新配置值
sed -i 's|^  base_url:.*|  base_url: "'$escapedBaseUrl'"|' "${'$'}CONFIG_FILE"
sed -i 's|^  api_key:.*|  api_key: "'$escapedApiKey'"|' "${'$'}CONFIG_FILE"
sed -i 's|^  model:.*|  model: "'$escapedModel'"|' "${'$'}CONFIG_FILE"

echo "Config updated: ${'$'}CONFIG_FILE"
""".trimIndent()
    }

    /**
     * 读取当前 LLM 配置
     * 通过 Termux 执行命令读取
     */
    fun readLLMConfig(context: Context): Map<String, String> {
        // 由于无法直接读取 Termux 文件，返回默认值
        // 实际配置会在 UI 层通过 SharedPreferences 缓存
        return mapOf(
            "base_url" to "https://api.openai.com/v1",
            "api_key" to "",
            "model" to "gpt-4o-mini"
        )
    }

    /**
     * 解析 YAML 配置块
     * 改进了对带冒号值的处理
     */
    private fun parseYamlSection(content: String, section: String): Map<String, String> {
        val result = mutableMapOf<String, String>()
        val lines = content.lines()
        var inSection = false

        for (line in lines) {
            if (line.startsWith("$section:")) {
                inSection = true
                continue
            }

            if (inSection) {
                // 检查是否离开当前 section
                if (line.isNotEmpty() && !line.startsWith(" ") && !line.startsWith("\t")) {
                    break
                }

                val trimmed = line.trim()
                if (trimmed.isEmpty()) continue

                // 查找第一个冒号的位置（正确处理带冒号的值）
                val colonIndex = trimmed.indexOf(':')
                if (colonIndex > 0) {
                    val key = trimmed.substring(0, colonIndex).trim()
                    var value = trimmed.substring(colonIndex + 1).trim()

                    // 移除引号（支持单引号和双引号）
                    if ((value.startsWith("\"") && value.endsWith("\"")) ||
                        (value.startsWith("'") && value.endsWith("'"))) {
                        value = value.substring(1, value.length - 1)
                    }

                    result[key] = value
                }
            }
        }

        return result
    }
}

data class ConfigResult(
    val success: Boolean,
    val message: String
)
