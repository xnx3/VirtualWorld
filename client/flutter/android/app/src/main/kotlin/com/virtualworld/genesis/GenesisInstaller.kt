package com.virtualworld.genesis

import android.content.Context
import android.content.Intent
import android.util.Log
import java.io.*
import java.util.zip.ZipInputStream

/**
 * Genesis 安装管理器
 * 负责将 Genesis 后端安装到 Termux 环境
 */
object GenesisInstaller {

    private const val TAG = "GenesisInstaller"
    const val TERMUX_HOME = "/data/data/com.termux/files/home"
    const val GENESIS_DIR = "$TERMUX_HOME/genesis"
    const val DATA_DIR = "$GENESIS_DIR/data"

    /**
     * 检查 Genesis 是否已安装到 Termux
     */
    fun isInstalled(): Boolean {
        val mainPy = File("$GENESIS_DIR/genesis/main.py")
        val startScript = File("$GENESIS_DIR/start_genesis.sh")
        return mainPy.exists() && startScript.exists()
    }

    /**
     * 安装 Genesis 到 Termux
     * @param context Android Context
     * @param progressCallback 进度回调 (stage, progress 0-100)
     * @return 是否成功
     */
    fun install(
        context: Context,
        progressCallback: ((String, Int) -> Unit)? = null
    ): InstallResult {
        try {
            progressCallback?.invoke("准备安装目录", 5)
            Log.i(TAG, "Starting Genesis installation...")

            // 创建目标目录
            val genesisDir = File(GENESIS_DIR)
            val dataDir = File(DATA_DIR)
            val chronicleDir = File("$DATA_DIR/chronicle")

            genesisDir.mkdirs()
            dataDir.mkdirs()
            chronicleDir.mkdirs()

            progressCallback?.invoke("复制文件", 20)

            // 从 assets 复制 genesis 文件
            copyAssetsToDir(context, "genesis", genesisDir)

            progressCallback?.invoke("复制启动脚本", 70)

            // 复制启动脚本
            copyAssetToFile(context, "start_genesis.sh", File("$GENESIS_DIR/start_genesis.sh"))
            copyAssetToFile(context, "install.sh", File("$GENESIS_DIR/install.sh"))

            progressCallback?.invoke("设置权限", 85)

            // 设置脚本执行权限
            Runtime.getRuntime().exec("chmod 755 $GENESIS_DIR/start_genesis.sh")
            Runtime.getRuntime().exec("chmod 755 $GENESIS_DIR/install.sh")

            // 复制配置模板
            copyAssetToFile(context, "config.yaml.example", File("$DATA_DIR/config.yaml.example"))

            progressCallback?.invoke("安装完成", 100)
            Log.i(TAG, "Genesis installation completed")

            return InstallResult(success = true, message = "安装成功")

        } catch (e: Exception) {
            Log.e(TAG, "Installation failed: ${e.message}", e)
            return InstallResult(success = false, message = "安装失败: ${e.message}")
        }
    }

    /**
     * 从 assets 复制目录到目标目录
     */
    private fun copyAssetsToDir(context: Context, assetPath: String, targetDir: File) {
        val assetManager = context.assets
        val files = assetManager.list(assetPath) ?: return

        for (file in files) {
            val sourcePath = "$assetPath/$file"
            val targetFile = File(targetDir, file)

            // 检查是目录还是文件
            try {
                val subFiles = assetManager.list(sourcePath)
                if (subFiles != null && subFiles.isNotEmpty()) {
                    // 是目录
                    targetFile.mkdirs()
                    copyAssetsToDir(context, sourcePath, targetFile)
                } else {
                    // 是文件
                    targetFile.parentFile?.mkdirs()
                    copyAssetToFile(context, sourcePath, targetFile)
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
     * 在 Termux 中运行安装脚本
     */
    fun runInstallScript(): Boolean {
        return try {
            val process = Runtime.getRuntime().exec(
                "su -c 'cd $GENESIS_DIR && bash install.sh'"
            )
            val exitCode = process.waitFor()
            exitCode == 0
        } catch (e: Exception) {
            Log.e(TAG, "Failed to run install script: ${e.message}")
            false
        }
    }

    /**
     * 获取 Termux 的 genesis 数据目录路径
     */
    fun getDataPath(): String = DATA_DIR

    /**
     * 检查配置文件是否存在
     */
    fun hasConfig(): Boolean {
        return File("$DATA_DIR/config.yaml").exists()
    }
}

/**
 * 安装结果
 */
data class InstallResult(
    val success: Boolean,
    val message: String
)
