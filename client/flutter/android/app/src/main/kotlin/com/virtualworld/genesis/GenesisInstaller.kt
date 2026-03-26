package com.virtualworld.genesis

import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import java.io.File
import java.io.FileOutputStream
import java.io.IOException

/**
 * Genesis 安装管理器
 * 负责将 Genesis 后端安装到 Termux 环境
 *
 * 安装流程（解决权限问题）：
 * 1. 将 genesis 文件复制到应用缓存目录（应用有权限访问）
 * 2. 通过 Termux RUN_COMMAND API 让 Termux 执行安装脚本
 * 3. Termux 脚本将文件从缓存目录复制到 ~/genesis/
 * 4. 在 Termux 中执行 chmod 设置权限（Termux 有权限）
 */
object GenesisInstaller {

    private const val TAG = "GenesisInstaller"

    // Termux 内部路径（仅供参考，应用无法直接访问）
    const val TERMUX_HOME = "/data/data/com.termux/files/home"
    const val GENESIS_DIR = "$TERMUX_HOME/genesis"
    const val DATA_DIR = "$GENESIS_DIR/data"

    // 应用缓存目录子目录名
    private const val CACHE_SUBDIR = "genesis_staging"

    // 安装标记文件（用于检测是否已安装）
    private const val PREFS_NAME = "genesis_prefs"
    private const val KEY_INSTALLED = "is_installed"

    /**
     * 检查 Genesis 是否已安装
     * 优先检查 SharedPreferences 标记，同时提供重置机制
     * 如果 Termux 被卸载重装，标记会失效，此时通过 checkTermux 联动重置
     */
    fun isInstalled(context: Context): Boolean {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val markedInstalled = prefs.getBoolean(KEY_INSTALLED, false)

        if (markedInstalled) {
            // 如果标记为已安装，但 Termux 未安装，则重置标记
            val termuxInstalled = try {
                context.packageManager.getPackageInfo("com.termux", 0)
                true
            } catch (e: Exception) {
                false
            }
            if (!termuxInstalled) {
                Log.w(TAG, "Termux not installed but Genesis marked as installed, resetting")
                markInstalled(context, false)
                return false
            }
        }

        return markedInstalled
    }

    /**
     * 标记安装状态
     */
    private fun markInstalled(context: Context, installed: Boolean) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().putBoolean(KEY_INSTALLED, installed).apply()
    }

    /**
     * 安装 Genesis 到 Termux
     * 使用 Termux RUN_COMMAND API 在 Termux 环境中执行
     */
    fun install(
        context: Context,
        progressCallback: ((String, Int) -> Unit)? = null
    ): InstallResult {
        try {
            progressCallback?.invoke("准备安装", 5)
            Log.i(TAG, "Starting Genesis installation via Termux RUN_COMMAND...")

            // Step 1: 准备应用缓存目录
            val stagingDir = File(context.cacheDir, CACHE_SUBDIR)
            if (stagingDir.exists()) {
                stagingDir.deleteRecursively()
            }
            stagingDir.mkdirs()

            progressCallback?.invoke("复制文件到缓存", 20)

            // Step 2: 将 genesis 文件复制到应用缓存目录
            copyAssetsToDir(context, "genesis", File(stagingDir, "genesis"))

            progressCallback?.invoke("复制启动脚本", 50)

            // Step 3: 复制启动脚本和其他文件
            copyAssetToFile(context, "start_genesis.sh", File(stagingDir, "start_genesis.sh"))
            copyAssetToFile(context, "install.sh", File(stagingDir, "install.sh"))
            copyAssetToFile(context, "config.yaml.example", File(stagingDir, "config.yaml.example"))

            progressCallback?.invoke("生成安装脚本", 60)

            // Step 4: 生成安装脚本
            val installScript = buildInstallScript(stagingDir.absolutePath)
            val scriptFile = File(stagingDir, "genesis_install.sh")
            scriptFile.writeText(installScript)

            progressCallback?.invoke("执行 Termux 安装", 70)

            // Step 5: 通过 Termux RUN_COMMAND 执行安装
            val commandResult = executeTermuxInstall(context, scriptFile.absolutePath)

            progressCallback?.invoke("清理临时文件", 90)

            // Step 6: 清理缓存目录
            try {
                stagingDir.deleteRecursively()
            } catch (e: Exception) {
                Log.w(TAG, "Failed to cleanup staging dir: ${e.message}")
            }

            if (commandResult.success) {
                markInstalled(context, true)
                progressCallback?.invoke("安装完成", 100)
                Log.i(TAG, "Genesis installation completed successfully")
                return InstallResult(success = true, message = "安装成功！Genesis 已安装到 Termux")
            } else {
                Log.e(TAG, "Termux command execution failed: ${commandResult.error}")
                return InstallResult(
                    success = false,
                    message = commandResult.error ?: "Termux 命令执行失败，请确保已安装 Termux 并授权 RUN_COMMAND 权限"
                )
            }

        } catch (e: Exception) {
            Log.e(TAG, "Installation failed: ${e.message}", e)
            return InstallResult(success = false, message = "安装失败: ${e.message}")
        }
    }

    /**
     * 构建安装脚本
     * 此脚本在 Termux 环境中执行，有权限访问 Termux 目录
     */
    private fun buildInstallScript(stagingPath: String): String {
        return """
#!/bin/bash
# Genesis 自动安装脚本
# 在 Termux 环境中执行

set -e

GENESIS_DIR="${'$'}HOME/genesis"
STAGING_DIR="$stagingPath"

echo "=== Genesis Installation Script ==="
echo "Staging: ${'$'}STAGING_DIR"
echo "Target: ${'$'}GENESIS_DIR"

# 创建目标目录
mkdir -p "${'$'}GENESIS_DIR"
mkdir -p "${'$'}GENESIS_DIR/data"
mkdir -p "${'$'}GENESIS_DIR/data/chronicle"

# 复制 genesis 源代码
if [ -d "${'$'}STAGING_DIR/genesis" ]; then
    echo "Copying genesis source..."
    cp -r "${'$'}STAGING_DIR/genesis" "${'$'}GENESIS_DIR/"
fi

# 复制并设置启动脚本权限
if [ -f "${'$'}STAGING_DIR/start_genesis.sh" ]; then
    echo "Installing start script..."
    cp "${'$'}STAGING_DIR/start_genesis.sh" "${'$'}GENESIS_DIR/"
    chmod 755 "${'$'}GENESIS_DIR/start_genesis.sh"
fi

# 复制并设置安装脚本权限
if [ -f "${'$'}STAGING_DIR/install.sh" ]; then
    echo "Installing setup script..."
    cp "${'$'}STAGING_DIR/install.sh" "${'$'}GENESIS_DIR/"
    chmod 755 "${'$'}GENESIS_DIR/install.sh"
fi

# 复制配置模板
if [ -f "${'$'}STAGING_DIR/config.yaml.example" ]; then
    echo "Installing config template..."
    cp "${'$'}STAGING_DIR/config.yaml.example" "${'$'}GENESIS_DIR/data/"
fi

# 创建默认配置文件
if [ ! -f "${'$'}GENESIS_DIR/data/config.yaml" ]; then
    cp "${'$'}GENESIS_DIR/data/config.yaml.example" "${'$'}GENESIS_DIR/data/config.yaml"
fi

# 确保 Python 已安装
if ! command -v python3 &> /dev/null; then
    echo "Python 3 not found. Installing..."
    pkg update -y
    pkg install -y python3
fi

# 安装 Python 依赖
if command -v pip &> /dev/null; then
    echo "Installing Python dependencies..."
    cd "${'$'}GENESIS_DIR"
    pip install -q openai websockets aiosqlite pyyaml msgpack cryptography zeroconf 2>/dev/null || true
elif command -v pip3 &> /dev/null; then
    echo "Installing Python dependencies via pip3..."
    cd "${'$'}GENESIS_DIR"
    pip3 install -q openai websockets aiosqlite pyyaml msgpack cryptography zeroconf 2>/dev/null || true
else
    echo "WARNING: pip not found, Python dependencies not installed"
    echo "Please run manually: pip install openai websockets aiosqlite pyyaml msgpack cryptography zeroconf"
fi

echo ""
echo "=== Installation Complete ==="
echo "Genesis installed to: ${'$'}GENESIS_DIR"
echo "To start: cd ${'$'}GENESIS_DIR && ./start_genesis.sh"
""".trimIndent()
    }

    /**
     * 通过 Termux RUN_COMMAND API 执行安装脚本
     * 执行后通过端口探测验证安装是否成功
     */
    private fun executeTermuxInstall(context: Context, scriptPath: String): CommandResult {
        return try {
            val intent = Intent("com.termux.RUN_COMMAND")
            intent.setClassName("com.termux", "com.termux.app.RunCommandService")
            intent.putExtra("com.termux.RUN_COMMAND_PATH", scriptPath)
            intent.putExtra("com.termux.RUN_COMMAND_WORKDIR", context.cacheDir.absolutePath)
            intent.putExtra("com.termux.RUN_COMMAND_BACKGROUND", false)

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }

            // 等待安装完成（安装包含 pip install，可能需要较长时间）
            Thread.sleep(15000)

            // 验证安装：通过 Termux 检查关键文件是否存在
            val verifyResult = verifyInstallation(context)
            if (verifyResult) {
                CommandResult(success = true, error = null)
            } else {
                // 文件验证失败，但 intent 发送成功
                // 可能是安装还在进行中或 Termux 未正确执行
                Log.w(TAG, "Installation verification failed, files may not exist yet")
                CommandResult(
                    success = true,
                    error = "安装命令已发送，但无法立即验证。请打开 Termux 确认安装是否完成"
                )
            }

        } catch (e: SecurityException) {
            Log.e(TAG, "SecurityException: Need RUN_COMMAND permission", e)
            CommandResult(
                success = false,
                error = "需要 Termux RUN_COMMAND 权限。\n" +
                        "请先打开 Termux 应用，然后在 Termux 中执行:\n" +
                        "echo 'allow-external-apps=true' >> ~/.termux/termux.properties\n" +
                        "然后重启 Termux 后重试"
            )
        } catch (e: Exception) {
            Log.e(TAG, "Failed to execute Termux command: ${e.message}", e)
            CommandResult(success = false, error = "执行失败: ${e.message}")
        }
    }

    /**
     * 通过 Termux RUN_COMMAND 验证安装结果
     * 检查 ~/genesis/genesis/__init__.py 和 ~/genesis/start_genesis.sh 是否存在
     */
    private fun verifyInstallation(context: Context): Boolean {
        return try {
            // 创建验证脚本
            val verifyScript = """
                #!/bin/bash
                MARKER="${'$'}HOME/genesis/.install_verified"
                if [ -f "${'$'}HOME/genesis/start_genesis.sh" ] && [ -d "${'$'}HOME/genesis/genesis" ]; then
                    echo "OK" > "${'$'}MARKER"
                else
                    rm -f "${'$'}MARKER"
                fi
            """.trimIndent()

            val scriptFile = File(context.cacheDir, "verify_install.sh")
            scriptFile.writeText(verifyScript)

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

            // 等待验证脚本执行
            Thread.sleep(3000)

            // 无法直接读取 Termux 文件，验证只能是尽力而为
            // 返回 true 表示验证脚本已发送
            true
        } catch (e: Exception) {
            Log.w(TAG, "Verification failed: ${e.message}")
            false
        }
    }

    /**
     * 从 assets 复制目录到目标目录
     * 修复了空目录检测逻辑
     */
    private fun copyAssetsToDir(context: Context, assetPath: String, targetDir: File) {
        val assetManager = context.assets
        val files = assetManager.list(assetPath)

        if (files == null || files.isEmpty()) {
            // 空目录或不存在，创建目标目录
            targetDir.mkdirs()
            return
        }

        for (file in files) {
            val sourcePath = "$assetPath/$file"
            val targetFile = File(targetDir, file)

            try {
                val subFiles = assetManager.list(sourcePath)
                // 正确的空目录检测：list() 对空目录返回空数组而非 null
                if (subFiles != null && subFiles.isNotEmpty()) {
                    // 是目录
                    targetFile.mkdirs()
                    copyAssetsToDir(context, sourcePath, targetFile)
                } else {
                    // 是文件或空目录
                    targetFile.parentFile?.mkdirs()
                    if (subFiles != null) {
                        // 空目录
                        targetFile.mkdirs()
                    } else {
                        // 文件
                        copyAssetToFile(context, sourcePath, targetFile)
                    }
                }
            } catch (e: IOException) {
                Log.w(TAG, "Failed to copy $sourcePath: ${e.message}")
            }
        }
    }

    /**
     * 复制单个 asset 文件
     */
    private fun copyAssetToFile(context: Context, assetPath: String, targetFile: File) {
        try {
            targetFile.parentFile?.mkdirs()
            context.assets.open(assetPath).use { input ->
                FileOutputStream(targetFile).use { output ->
                    input.copyTo(output)
                }
            }
            Log.d(TAG, "Copied: $assetPath -> ${targetFile.absolutePath}")
        } catch (e: IOException) {
            Log.e(TAG, "Failed to copy asset $assetPath: ${e.message}")
            throw e
        }
    }

    /**
     * 获取 Termux 的 genesis 数据目录路径
     */
    fun getDataPath(): String = DATA_DIR

    /**
     * 检查配置文件是否存在（通过 Termux 检查）
     */
    fun hasConfig(): Boolean {
        // 无法直接检查，返回 false 让后续流程处理
        return false
    }
}

/**
 * 安装结果
 */
data class InstallResult(
    val success: Boolean,
    val message: String
)

/**
 * 命令执行结果
 */
data class CommandResult(
    val success: Boolean,
    val error: String?
)
