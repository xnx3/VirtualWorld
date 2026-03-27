package com.virtualworld.genesis

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.Settings
import android.util.Log
import androidx.core.content.FileProvider
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.io.FileOutputStream

/**
 * Flutter 主活动
 * 提供 Termux 服务控制接口
 */
class MainActivity : FlutterActivity() {

    companion object {
        private const val CHANNEL = "com.virtualworld.genesis/termux"
        private const val REQUEST_INSTALL_TERMUX = 1001

        // Termux APK 文件名 - 支持多种架构
        // 优先级: x86_64 > universal > arm64-v8a (用于真机)
        private val TERMUX_APK_NAMES = listOf(
            "termux-x86_64.apk",      // x86_64 模拟器
            "termux-universal.apk",   // 通用版本
            "termux-arm64-v8a.apk"    // ARM64 真机
        )
    }

    private var installProgressCallback: MethodChannel? = null

    /**
     * 根据设备架构选择最合适的 Termux APK
     * 返回 Pair<APK文件名, 是否存在>
     */
    private fun selectBestTermuxApk(): Pair<String, Boolean> {
        val abis = Build.SUPPORTED_ABIS.toList()
        Log.i("MainActivity", "Device supported ABIs: $abis")

        // 检查 assets 中可用的 APK
        val availableApks = try {
            assets.list("")?.filter { it.startsWith("termux-") && it.endsWith(".apk") }?.toSet() ?: emptySet()
        } catch (e: Exception) {
            emptySet()
        }
        Log.i("MainActivity", "Available Termux APKs in assets: $availableApks")

        // 根据架构选择 APK
        val preferredApk = when {
            // x86_64 模拟器优先使用 x86_64 版本
            abis.contains("x86_64") && availableApks.contains("termux-x86_64.apk") -> "termux-x86_64.apk"
            // 其次使用 universal 版本
            availableApks.contains("termux-universal.apk") -> "termux-universal.apk"
            // ARM64 真机
            abis.contains("arm64-v8a") && availableApks.contains("termux-arm64-v8a.apk") -> "termux-arm64-v8a.apk"
            // 回退到第一个可用的
            availableApks.isNotEmpty() -> availableApks.first()
            else -> "termux-universal.apk" // 默认
        }

        val exists = availableApks.contains(preferredApk)
        Log.i("MainActivity", "Selected Termux APK: $preferredApk, exists: $exists")
        return Pair(preferredApk, exists)
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        val channel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL)
        installProgressCallback = channel

        channel.setMethodCallHandler { call, result ->
            when (call.method) {
                // === Termux 检测 ===
                "checkTermux" -> {
                    val installed = isPackageInstalled("com.termux")
                    result.success(installed)
                }

                "openTermux" -> {
                    openTermuxApp()
                    result.success(true)
                }

                "openTermuxStore" -> {
                    // 改为安装内嵌的 Termux APK
                    val installResult = installBundledTermux()
                    result.success(installResult)
                }

                "installBundledTermux" -> {
                    val installResult = installBundledTermux()
                    result.success(installResult)
                }

                "canInstallPackages" -> {
                    val canInstall = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                        packageManager.canRequestPackageInstalls()
                    } else {
                        true
                    }
                    result.success(canInstall)
                }

                "requestInstallPermission" -> {
                    requestInstallPackagesPermission()
                    result.success(true)
                }

                // === 调试：检查 Termux APK 是否存在 ===
                "checkTermuxApkExists" -> {
                    try {
                        val files = assets.list("")
                        val (selectedApk, exists) = selectBestTermuxApk()
                        val allAssets = files?.toList() ?: emptyList<String>()
                        result.success(mapOf(
                            "exists" to exists,
                            "apkName" to selectedApk,
                            "allAssets" to allAssets,
                            "supportedAbis" to Build.SUPPORTED_ABIS.toList()
                        ))
                    } catch (e: Exception) {
                        result.success(mapOf(
                            "exists" to false,
                            "error" to e.message
                        ))
                    }
                }

                // === Genesis 安装 ===
                "isGenesisInstalled" -> {
                    val installed = GenesisInstaller.isInstalled(this)
                    result.success(installed)
                }

                "installGenesis" -> {
                    Thread {
                        val installResult = GenesisInstaller.install(context = this) { stage, progress ->
                            runOnUiThread {
                                channel.invokeMethod("installProgress", mapOf(
                                    "stage" to stage,
                                    "progress" to progress
                                ))
                            }
                        }
                        runOnUiThread {
                            result.success(mapOf(
                                "success" to installResult.success,
                                "message" to installResult.message,
                                "autoInstallTriggered" to installResult.autoInstallTriggered,
                                "autoInstallError" to installResult.autoInstallError,
                                "manualCommand" to installResult.manualCommand,
                            ))
                        }
                    }.start()
                }

                "getGenesisDataPath" -> {
                    result.success(GenesisInstaller.getDataPath())
                }

                "hasConfig" -> {
                    result.success(GenesisInstaller.hasConfig())
                }

                // === 存储权限 ===
                "hasStoragePermission" -> {
                    val hasPermission = GenesisInstaller.hasStoragePermission(this)
                    result.success(hasPermission)
                }

                "requestStoragePermission" -> {
                    requestStoragePermission()
                    result.success(true)
                }

                // === 服务控制 ===
                "startGenesis" -> {
                    val success = startGenesisService()
                    result.success(success)
                }

                "stopGenesis" -> {
                    val success = stopGenesisService()
                    result.success(success)
                }

                "checkServiceRunning" -> {
                    val running = isGenesisRunning()
                    result.success(running)
                }

                // === LLM 配置 ===
                "saveLLMConfig" -> {
                    val baseUrl = call.argument<String>("baseUrl") ?: ""
                    val apiKey = call.argument<String>("apiKey") ?: ""
                    val model = call.argument<String>("model") ?: ""

                    val configResult = GenesisConfig.saveLLMConfig(
                        context = this,
                        baseUrl = baseUrl,
                        apiKey = apiKey,
                        model = model
                    )
                    result.success(mapOf(
                        "success" to configResult.success,
                        "message" to configResult.message
                    ))
                }

                "readLLMConfig" -> {
                    val config = GenesisConfig.readLLMConfig(this)
                    result.success(config)
                }

                else -> result.notImplemented()
            }
        }
    }

    private fun isPackageInstalled(packageName: String): Boolean {
        return try {
            val pm = packageManager
            pm.getPackageInfo(packageName, 0)
            true
        } catch (e: Exception) {
            false
        }
    }

    private fun openTermuxApp() {
        try {
            val intent = packageManager.getLaunchIntentForPackage("com.termux")
            if (intent != null) {
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                startActivity(intent)
            }
        } catch (e: Exception) {
            // Termux not installed
        }
    }

    /**
     * 安装 Termux
     * 优先使用内嵌 APK，如果不存在则引导用户从 GitHub 下载
     */
    private fun installBundledTermux(): Map<String, Any> {
        return try {
            Log.i("MainActivity", "Starting Termux installation...")

            // 检查 Android 8.0+ 的安装权限
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                if (!packageManager.canRequestPackageInstalls()) {
                    Log.w("MainActivity", "No permission to install packages")
                    // 引导用户到设置页面授权
                    val intent = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES)
                    intent.data = Uri.parse("package:$packageName")
                    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    startActivity(intent)
                    return mapOf(
                        "success" to false,
                        "error" to "需要安装权限，请在设置中授权后重试",
                        "stage" to "permission"
                    )
                }
            }

            Log.i("MainActivity", "Permission OK, selecting best Termux APK...")

            // 根据架构选择合适的 APK
            val (termuxApkName, apkExists) = selectBestTermuxApk()

            if (!apkExists) {
                val availableApks = try {
                    assets.list("")?.filter { it.startsWith("termux-") && it.endsWith(".apk") } ?: emptyList()
                } catch (e: Exception) {
                    emptyList()
                }
                return mapOf(
                    "success" to false,
                    "error" to "APK 文件不存在: $termuxApkName，当前设备架构: ${Build.SUPPORTED_ABIS.joinToString()}",
                    "stage" to "asset_check",
                    "selectedApk" to termuxApkName,
                    "availableApks" to availableApks
                )
            }

            // 从 assets 复制 Termux APK 到缓存目录
            val apkFile = File(cacheDir, termuxApkName)
            try {
                assets.open(termuxApkName).use { input ->
                    FileOutputStream(apkFile).use { output ->
                        input.copyTo(output)
                    }
                }
                Log.i("MainActivity", "APK copied to: ${apkFile.absolutePath}, size: ${apkFile.length()}")
            } catch (e: Exception) {
                Log.e("MainActivity", "Failed to copy APK: ${e.message}")
                return mapOf(
                    "success" to false,
                    "error" to "复制 APK 失败: ${e.message}",
                    "stage" to "copy_apk"
                )
            }

            // 使用 FileProvider 获取 URI
            val apkUri = try {
                FileProvider.getUriForFile(
                    this,
                    "${packageName}.fileprovider",
                    apkFile
                )
            } catch (e: Exception) {
                Log.e("MainActivity", "FileProvider error: ${e.message}")
                return mapOf(
                    "success" to false,
                    "error" to "FileProvider 错误: ${e.message}",
                    "stage" to "fileprovider"
                )
            }

            Log.i("MainActivity", "APK URI: $apkUri")

            // 启动安装
            try {
                val installIntent = Intent(Intent.ACTION_INSTALL_PACKAGE)
                installIntent.data = apkUri
                installIntent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                installIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                startActivity(installIntent)

                Log.i("MainActivity", "Termux installation intent sent successfully")
                mapOf(
                    "success" to true,
                    "message" to "请在系统界面完成 Termux 安装"
                )
            } catch (e: Exception) {
                Log.e("MainActivity", "Failed to start install intent: ${e.message}")
                mapOf(
                    "success" to false,
                    "error" to "启动安装失败: ${e.message}",
                    "stage" to "start_install"
                )
            }
        } catch (e: Exception) {
            Log.e("MainActivity", "Unexpected error: ${e.message}", e)
            mapOf(
                "success" to false,
                "error" to "未知错误: ${e.message}",
                "stage" to "unknown"
            )
        }
    }

    /**
     * 请求安装未知应用权限
     */
    private fun requestInstallPackagesPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            if (!packageManager.canRequestPackageInstalls()) {
                val intent = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES)
                intent.data = Uri.parse("package:$packageName")
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                startActivity(intent)
            }
        }
    }

    /**
     * 请求存储权限（Android 11+ 需要 MANAGE_EXTERNAL_STORAGE）
     */
    private fun requestStoragePermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            // Android 11+ 需要跳转到所有文件访问权限设置
            if (!Environment.isExternalStorageManager()) {
                val intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
                intent.data = Uri.parse("package:$packageName")
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                startActivity(intent)
            }
        } else {
            // Android 10 及以下请求运行时权限
            requestPermissions(
                arrayOf(
                    android.Manifest.permission.READ_EXTERNAL_STORAGE,
                    android.Manifest.permission.WRITE_EXTERNAL_STORAGE
                ),
                1002
            )
        }
    }

    private fun startGenesisService(): Boolean {
        return try {
            // 使用 RUN_COMMAND intent 启动 Genesis
            val intent = Intent("com.termux.RUN_COMMAND")
            intent.setClassName("com.termux", "com.termux.app.RunCommandService")
            intent.putExtra("com.termux.RUN_COMMAND_PATH", "${GenesisInstaller.GENESIS_DIR}/start_genesis.sh")
            intent.putExtra("com.termux.RUN_COMMAND_WORKDIR", GenesisInstaller.GENESIS_DIR)
            intent.putExtra("com.termux.RUN_COMMAND_BACKGROUND", true)

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(intent)
            } else {
                startService(intent)
            }
            true
        } catch (e: Exception) {
            Log.e("MainActivity", "Failed to start Genesis: ${e.message}")
            false
        }
    }

    /**
     * 停止 Genesis 服务
     * 通过 Termux RUN_COMMAND 执行 kill，确保能看到 Termux 进程
     */
    private fun stopGenesisService(): Boolean {
        return try {
            val intent = Intent("com.termux.RUN_COMMAND")
            intent.setClassName("com.termux", "com.termux.app.RunCommandService")
            intent.putExtra("com.termux.RUN_COMMAND_PATH", "/data/data/com.termux/files/usr/bin/bash")
            intent.putExtra("com.termux.RUN_COMMAND_ARGUMENTS", arrayOf("-c", "pkill -f 'genesis.main' 2>/dev/null; exit 0"))
            intent.putExtra("com.termux.RUN_COMMAND_WORKDIR", GenesisInstaller.GENESIS_DIR)
            intent.putExtra("com.termux.RUN_COMMAND_BACKGROUND", true)

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(intent)
            } else {
                startService(intent)
            }
            true
        } catch (e: Exception) {
            Log.e("MainActivity", "Failed to stop Genesis: ${e.message}")
            false
        }
    }

    /**
     * 检查 Genesis 是否在运行
     * 通过尝试连接 WebSocket 端口来判断，比 pgrep 跨进程更可靠
     */
    private fun isGenesisRunning(): Boolean {
        return try {
            val socket = java.net.Socket()
            socket.connect(java.net.InetSocketAddress("127.0.0.1", 19842), 1000)
            socket.close()
            true
        } catch (e: Exception) {
            false
        }
    }
}
