package com.virtualworld.genesis

import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Environment
import android.util.Log
import java.io.File
import java.io.FileOutputStream
import java.io.IOException

/**
 * Genesis 安装管理器
 * 负责将 Genesis 后端安装到 Termux 环境
 *
 * 安装流程（使用共享存储中转）：
 * 1. 将 genesis 文件复制到共享存储的 Download 目录
 * 2. 生成安装脚本，放到共享存储
 * 3. 提示用户在 Termux 中运行安装脚本
 * 4. 脚本将文件复制到 ~/genesis/
 *
 * 支持两种安装方式：
 * - 快速安装：使用预构建的 bundle（genesis-termux-bundle.tar.gz），解压即用
 * - 完整安装：从源码安装，需要 pip install 编译依赖
 */
object GenesisInstaller {

    private const val TAG = "GenesisInstaller"
    private const val BUNDLE_NAME = "genesis-termux-bundle.tar.gz"

    // Termux 内部路径（仅供参考，应用无法直接访问）
    const val TERMUX_HOME = "/data/data/com.termux/files/home"
    const val GENESIS_DIR = "$TERMUX_HOME/genesis"
    const val DATA_DIR = "$GENESIS_DIR/data"
    const val SHARED_GENESIS_DIR_IN_TERMUX = "\$HOME/storage/downloads/Genesis"
    const val QUICK_INSTALL_SCRIPT_IN_TERMUX = "$SHARED_GENESIS_DIR_IN_TERMUX/quick_install.sh"
    const val FULL_INSTALL_SCRIPT_IN_TERMUX = "$SHARED_GENESIS_DIR_IN_TERMUX/install.sh"

    // 共享存储目录名
    private const val SHARED_DIR_NAME = "Genesis"

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

        // 先检查 Termux 是否安装
        val termuxInstalled = try {
            context.packageManager.getPackageInfo("com.termux", 0)
            true
        } catch (e: Exception) {
            false
        }
        if (!termuxInstalled) {
            if (markedInstalled) {
                Log.w(TAG, "Termux not installed but Genesis marked as installed, resetting")
                markInstalled(context, false)
            }
            return false
        }

        // 再检查共享目录中关键安装文件是否存在，避免仅凭缓存误判
        val sharedDir = getSharedStorageDir(context)
        val hasInstallScript = sharedDir?.let { File(it, "install.sh").exists() } ?: false
        val hasGenesisSource = sharedDir?.let { File(it, "genesis").isDirectory } ?: false
        val hasPreparedFiles = hasInstallScript && hasGenesisSource

        if (!hasPreparedFiles) {
            if (markedInstalled) {
                Log.w(TAG, "Install marker exists but shared files missing, resetting")
                markInstalled(context, false)
            }
            return false
        }

        // 文件齐全但标记丢失时，自动修复标记
        if (!markedInstalled) {
            markInstalled(context, true)
        }

        return true
    }

    /**
     * 标记安装状态
     */
    private fun markInstalled(context: Context, installed: Boolean) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().putBoolean(KEY_INSTALLED, installed).apply()
    }

    /**
     * 检查是否有存储权限
     */
    fun hasStoragePermission(context: Context): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            // Android 11+ 需要 MANAGE_EXTERNAL_STORAGE
            Environment.isExternalStorageManager()
        } else {
            // Android 10 及以下检查读写权限
            val read = context.checkSelfPermission(android.Manifest.permission.READ_EXTERNAL_STORAGE)
            val write = context.checkSelfPermission(android.Manifest.permission.WRITE_EXTERNAL_STORAGE)
            read == android.content.pm.PackageManager.PERMISSION_GRANTED &&
            write == android.content.pm.PackageManager.PERMISSION_GRANTED
        }
    }

    /**
     * 当前 APK 是否已内置预构建 Python 运行时 bundle
     */
    fun hasBundledRuntime(context: Context): Boolean {
        return try {
            context.assets.open(BUNDLE_NAME).use { true }
        } catch (e: IOException) {
            false
        }
    }

    /**
     * 安装 Genesis
     * 将文件复制到共享存储，并返回安装指令
     */
    fun install(
        context: Context,
        progressCallback: ((String, Int) -> Unit)? = null,
        autoRunInTermux: Boolean = true,
    ): InstallResult {
        try {
            progressCallback?.invoke("准备安装", 5)
            Log.i(TAG, "Starting Genesis installation...")

            // Step 1: 检查存储权限
            if (!hasStoragePermission(context)) {
                return InstallResult(
                    success = false,
                    message = "需要存储权限才能安装 Genesis。\n\n请在设置中授予\"所有文件访问\"权限后重试。"
                )
            }

            // Step 2: 获取共享存储目录
            val sharedDir = getSharedStorageDir(context)
            if (sharedDir == null) {
                return InstallResult(
                    success = false,
                    message = "无法访问共享存储，请授予存储权限"
                )
            }

            progressCallback?.invoke("清理旧文件", 10)

            // Step 3: 清理旧文件
            val genesisDir = File(sharedDir, "genesis")
            if (genesisDir.exists()) {
                genesisDir.deleteRecursively()
            }
            genesisDir.mkdirs()

            progressCallback?.invoke("复制 Genesis 文件", 20)

            // Step 4: 复制 genesis 源代码到共享存储
            copyAssetsToDir(context, "genesis", genesisDir)

            progressCallback?.invoke("复制配置文件", 60)

            // Step 5: 复制配置和脚本文件
            copyAssetToFile(context, "start_genesis.sh", File(sharedDir, "start_genesis.sh"))
            copyAssetToFile(context, "install.sh", File(sharedDir, "install.sh"))
            copyAssetToFile(context, "quick_install.sh", File(sharedDir, "quick_install.sh"))
            copyAssetToFile(context, "config.yaml.example", File(sharedDir, "config.yaml.example"))

            // Step 5.5: 复制预构建 bundle（如果存在）
            val hasBundle = copyBundleIfExists(context, sharedDir)

            progressCallback?.invoke("生成安装指令", 80)

            val installScriptPath = "${sharedDir.absolutePath}/install.sh"
            val quickInstallScriptPath = "${sharedDir.absolutePath}/quick_install.sh"
            val preferredScriptPath = if (hasBundle) quickInstallScriptPath else installScriptPath

            // Step 6: 生成安装指令文件
            val instructionFile = File(sharedDir, "INSTALL_INSTRUCTIONS.txt")
            instructionFile.writeText(getInstallInstructions(sharedDir, hasBundle))

            // Step 7: 尝试自动触发 Termux 执行安装
            val autoInstallResult = if (autoRunInTermux) {
                tryAutoInstallInTermux(context, preferredScriptPath)
            } else {
                CommandResult(success = false, error = null)
            }

            progressCallback?.invoke("安装准备完成", 100)

            Log.i(TAG, "Genesis files copied to: ${sharedDir.absolutePath}")

            val manualCommand = "termux-setup-storage\nbash \"$preferredScriptPath\""
            val installInstructions = buildInstallMessage(
                sharedDirPath = sharedDir.absolutePath,
                hasBundle = hasBundle,
                installScriptPath = installScriptPath,
                quickInstallScriptPath = quickInstallScriptPath,
                autoInstallResult = autoInstallResult,
                autoRunAttempted = autoRunInTermux,
            )

            // 安装文件已准备就绪，写入已安装标记
            markInstalled(context, true)

            return InstallResult(
                success = true,
                message = installInstructions,
                autoInstallTriggered = autoRunInTermux && autoInstallResult.success,
                autoInstallError = autoInstallResult.error,
                manualCommand = manualCommand,
                hasBundledRuntime = hasBundle,
            )

        } catch (e: Exception) {
            Log.e(TAG, "Installation failed: ${e.message}", e)
            markInstalled(context, false)
            return InstallResult(success = false, message = "安装失败: ${e.message}")
        }
    }

    private fun buildInstallMessage(
        sharedDirPath: String,
        hasBundle: Boolean,
        installScriptPath: String,
        quickInstallScriptPath: String,
        autoInstallResult: CommandResult,
        autoRunAttempted: Boolean,
    ): String {
        val scriptHint = if (hasBundle) {
            "【推荐】快速安装（约1分钟）：\n" +
                "1. 如果 Termux 首次弹出文件访问权限，请点“允许”\n" +
                "2. termux-setup-storage\n" +
                "3. bash \"$quickInstallScriptPath\"\n\n" +
                "或者完整安装（约20分钟）：\n" +
                "bash \"$installScriptPath\""
        } else {
            "完整安装（约20分钟）：\n" +
                "1. 如果 Termux 首次弹出文件访问权限，请点“允许”\n" +
                "2. termux-setup-storage\n" +
                "3. bash \"$installScriptPath\""
        }

        return if (!autoRunAttempted) {
            "安装文件已准备就绪。\n\n" +
                "应用接下来可以直接在后台调用 Termux 完成安装并启动。\n" +
                "如果后台启动失败，再手动执行：\n$scriptHint"
        } else if (autoInstallResult.success) {
            "安装文件已准备就绪，并已尝试自动触发 Termux 执行安装命令。\n\n" +
                "注意：这一步只是把安装文件准备好，真正安装会在 Termux 内完成。\n" +
                "第一次安装如果看到文件访问权限弹窗，请点“允许”。\n\n" +
                "安装文件位置:\n$sharedDirPath\n\n" +
                "请切换到 Termux 查看安装输出。\n" +
                "如果未自动开始，请手动执行：\n$scriptHint"
        } else {
            "安装文件已准备就绪，但自动触发 Termux 安装失败：${autoInstallResult.error ?: "未知原因"}\n\n" +
                "注意：这一步只是把安装文件准备好，真正安装仍需在 Termux 内完成。\n" +
                "第一次安装如果看到文件访问权限弹窗，请点“允许”。\n\n" +
                "安装文件位置:\n$sharedDirPath\n\n" +
                "请手动执行：\n$scriptHint"
        }
    }

    /**
     * 获取共享存储的 Download 目录下的 Genesis 目录
     */
    private fun getSharedStorageDir(context: Context): File? {
        // 使用外部存储的 Download 目录
        val downloadsDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
        val genesisDir = File(downloadsDir, SHARED_DIR_NAME)

        if (!genesisDir.exists()) {
            val created = genesisDir.mkdirs()
            if (!created) {
                Log.e(TAG, "Failed to create directory: ${genesisDir.absolutePath}")
                // 尝试使用应用外部存储目录
                val extDir = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
                if (extDir != null) {
                    val altDir = File(extDir, SHARED_DIR_NAME)
                    altDir.mkdirs()
                    return altDir
                }
                return null
            }
        }

        return genesisDir
    }

    /**
     * 获取安装指令
     */
    private fun getInstallInstructions(sharedDir: File, hasBundle: Boolean): String {
        val installScriptPath = "${sharedDir.absolutePath}/install.sh"
        val quickInstallScriptPath = "${sharedDir.absolutePath}/quick_install.sh"
        val commandBlock = if (hasBundle) {
            """
2. 首次如果弹出文件访问权限，点“允许”

3. 执行快速安装：
   termux-setup-storage
   bash "$quickInstallScriptPath"

4. 如果快速安装不可用，再执行完整安装：
   bash "$installScriptPath"

5. 安装完成后启动服务：
   cd ~/genesis
   ./start_genesis.sh
""".trimIndent()
        } else {
            """
2. 首次如果弹出文件访问权限，点“允许”

3. 运行安装脚本：
   termux-setup-storage
   bash "$installScriptPath"

4. 安装完成后启动服务：
   cd ~/genesis
   ./start_genesis.sh
""".trimIndent()
        }
        return """
=== Genesis 安装说明 ===

1. 打开 Termux 应用

${commandBlock}

祝你好运，硅基生命！
""".trimIndent()
    }

    private fun isTermuxInstalled(context: Context): Boolean {
        return try {
            context.packageManager.getPackageInfo("com.termux", 0)
            true
        } catch (e: Exception) {
            false
        }
    }

    /**
     * 通过 Termux RUN_COMMAND API 自动触发安装。
     *
     * 执行逻辑：
     * 1. 先调用 termux-setup-storage（若已授权则快速返回）
     * 2. 再执行 install/quick_install 脚本
     */
    private fun tryAutoInstallInTermux(context: Context, scriptPath: String): CommandResult {
        if (!isTermuxInstalled(context)) {
            return CommandResult(success = false, error = "Termux 未安装")
        }

        val quotedScriptPath = quoteForShell(scriptPath)
        val shellCommand = """
            termux-setup-storage >/dev/null 2>&1 || true
            target=$quotedScriptPath
            waited=0
            while [ ! -r "${'$'}target" ] && [ ${'$'}waited -lt 30 ]; do
                sleep 1
                waited=${'$'}((waited + 1))
            done
            if [ ! -r "${'$'}target" ]; then
                echo "Storage permission is not ready for ${'$'}target"
                exit 1
            fi
            bash "${'$'}target"
        """.trimIndent()

        return try {
            val intent = Intent("com.termux.RUN_COMMAND")
            intent.setClassName("com.termux", "com.termux.app.RunCommandService")
            intent.putExtra("com.termux.RUN_COMMAND_PATH", "/data/data/com.termux/files/usr/bin/bash")
            intent.putExtra("com.termux.RUN_COMMAND_ARGUMENTS", arrayOf("-lc", shellCommand))
            intent.putExtra("com.termux.RUN_COMMAND_WORKDIR", TERMUX_HOME)
            intent.putExtra("com.termux.RUN_COMMAND_BACKGROUND", true)

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }

            CommandResult(success = true, error = null)
        } catch (e: SecurityException) {
            Log.e(TAG, "SecurityException: Need RUN_COMMAND permission", e)
            CommandResult(
                success = false,
                error = "需要 Termux RUN_COMMAND 权限。请先打开 Termux 并允许外部应用调用后重试"
            )
        } catch (e: Exception) {
            Log.e(TAG, "Failed to auto-install via Termux: ${e.message}", e)
            CommandResult(success = false, error = "执行失败: ${e.message}")
        }
    }

    private fun quoteForShell(value: String): String {
        return "'${value.replace("'", "'\"'\"'")}'"
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
     * 复制预构建 bundle（如果存在）
     * 直接尝试打开 bundle 文件，避免遍历所有 assets
     * @return true 如果 bundle 复制成功
     */
    private fun copyBundleIfExists(context: Context, targetDir: File): Boolean {
        val bundleName = BUNDLE_NAME
        val sha256Name = "genesis-termux-bundle.tar.gz.sha256"

        return try {
            // 直接尝试打开 bundle 文件 - 比遍历所有 assets 更高效
            context.assets.open(bundleName).use { input ->
                FileOutputStream(File(targetDir, bundleName)).use { output ->
                    input.copyTo(output)
                }
            }
            Log.i(TAG, "Bundle file copied: $bundleName")

            // 尝试复制 SHA256 文件（可选）
            try {
                context.assets.open(sha256Name).use { input ->
                    FileOutputStream(File(targetDir, sha256Name)).use { output ->
                        input.copyTo(output)
                    }
                }
                Log.i(TAG, "SHA256 file copied: $sha256Name")
            } catch (e: IOException) {
                Log.d(TAG, "No SHA256 file found, skipping")
            }

            val sizeMB = File(targetDir, bundleName).length() / (1024 * 1024)
            Log.i(TAG, "Bundle size: $sizeMB MB")
            true
        } catch (e: IOException) {
            Log.i(TAG, "No pre-built bundle found in assets")
            false
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
    val message: String,
    val autoInstallTriggered: Boolean = false,
    val autoInstallError: String? = null,
    val manualCommand: String? = null,
    val hasBundledRuntime: Boolean = false,
)

/**
 * 命令执行结果
 */
data class CommandResult(
    val success: Boolean,
    val error: String?
)
