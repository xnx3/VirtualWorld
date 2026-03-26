package com.virtualworld.genesis

import android.content.Context
import android.util.Log
import java.io.File

/**
 * Genesis 配置管理器
 * 负责读写 Termux 中的 config.yaml
 */
object GenesisConfig {

    private const val TAG = "GenesisConfig"

    /**
     * 保存 LLM 配置到 config.yaml
     */
    fun saveLLMConfig(
        context: Context,
        baseUrl: String,
        apiKey: String,
        model: String
    ): ConfigResult {
        try {
            val configFile = File("${GenesisInstaller.DATA_DIR}/config.yaml")

            // 如果文件不存在，从模板创建
            if (!configFile.exists()) {
                val template = File("${GenesisInstaller.DATA_DIR}/config.yaml.example")
                if (template.exists()) {
                    template.copyTo(configFile)
                } else {
                    // 创建默认配置
                    createDefaultConfig(configFile)
                }
            }

            // 读取现有配置
            var content = configFile.readText()

            // 更新 LLM 配置
            content = updateYamlSection(content, "llm", mapOf(
                "base_url" to baseUrl,
                "api_key" to apiKey,
                "model" to model,
                "max_tokens" to 4096,
                "temperature" to 0.7
            ))

            configFile.writeText(content)
            Log.i(TAG, "LLM config saved to ${configFile.absolutePath}")

            return ConfigResult(success = true, message = "配置已保存")

        } catch (e: Exception) {
            Log.e(TAG, "Failed to save config: ${e.message}", e)
            return ConfigResult(success = false, message = "保存失败: ${e.message}")
        }
    }

    /**
     * 读取当前 LLM 配置
     */
    fun readLLMConfig(context: Context): Map<String, String> {
        try {
            val configFile = File("${GenesisInstaller.DATA_DIR}/config.yaml")
            if (!configFile.exists()) {
                return mapOf(
                    "base_url" to "https://api.openai.com/v1",
                    "api_key" to "",
                    "model" to "gpt-4o-mini"
                )
            }

            val content = configFile.readText()
            return parseYamlSection(content, "llm")

        } catch (e: Exception) {
            Log.e(TAG, "Failed to read config: ${e.message}")
            return mapOf(
                "base_url" to "https://api.openai.com/v1",
                "api_key" to "",
                "model" to "gpt-4o-mini"
            )
        }
    }

    /**
     * 创建默认配置文件
     */
    private fun createDefaultConfig(file: File) {
        file.parentFile?.mkdirs()
        file.writeText("""
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
""".trimIndent())
    }

    /**
     * 更新 YAML 配置块
     */
    private fun updateYamlSection(content: String, section: String, values: Map<String, Any>): String {
        val lines = content.lines().toMutableList()
        var inSection = false
        var sectionStart = -1
        var sectionEnd = lines.size

        // 找到 section 的位置
        for (i in lines.indices) {
            val line = lines[i]
            if (line.startsWith("$section:")) {
                inSection = true
                sectionStart = i
            } else if (inSection && line.isNotEmpty() && !line.startsWith(" ") && !line.startsWith("\t")) {
                sectionEnd = i
                break
            }
        }

        // 如果找不到 section，添加到末尾
        if (sectionStart == -1) {
            lines.add("")
            lines.add("$section:")
            values.forEach { (key, value) ->
                val yamlValue = if (value is String) "\"$value\"" else value.toString()
                lines.add("  $key: $yamlValue")
            }
            return lines.joinToString("\n")
        }

        // 更新现有值
        val newLines = lines.toMutableList()
        val existingKeys = mutableSetOf<String>()

        for (i in sectionStart until sectionEnd) {
            val line = newLines[i]
            for ((key, value) in values) {
                if (line.trim().startsWith("$key:")) {
                    existingKeys.add(key)
                    val yamlValue = if (value is String) "\"$value\"" else value.toString()
                    val indent = line.takeWhile { it == ' ' || it == '\t' }
                    newLines[i] = "$indent$key: $yamlValue"
                }
            }
        }

        // 添加新值
        val keysToAdd = values.keys - existingKeys
        if (keysToAdd.isNotEmpty()) {
            var insertIndex = sectionEnd
            for (key in keysToAdd) {
                val value = values[key]!!
                val yamlValue = if (value is String) "\"$value\"" else value.toString()
                newLines.add(insertIndex, "  $key: $yamlValue")
                insertIndex++
            }
        }

        return newLines.joinToString("\n")
    }

    /**
     * 解析 YAML 配置块
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
                if (line.isNotEmpty() && !line.startsWith(" ") && !line.startsWith("\t")) {
                    break
                }

                val trimmed = line.trim()
                if (trimmed.contains(":")) {
                    val parts = trimmed.split(":", limit = 2)
                    if (parts.size == 2) {
                        val key = parts[0].trim()
                        var value = parts[1].trim()
                        // 移除引号
                        if (value.startsWith("\"") && value.endsWith("\"")) {
                            value = value.substring(1, value.length - 1)
                        }
                        result[key] = value
                    }
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
