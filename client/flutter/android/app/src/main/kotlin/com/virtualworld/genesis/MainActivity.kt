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
        private const val TERMUX_APK_NAME = "termux-arm64-v8a.apk"
        private const val REQUEST_INSTALL_TERMUX = 1001
    }

    private var installProgressCallback: MethodChannel? = null

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
                                "message" to installResult.message
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
     * 安装内嵌的 Termux APK
     */
    private fun installBundledTermux(): Boolean {
        return try {
            // 检查 Android 8.0+ 的安装权限
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                if (!packageManager.canRequestPackageInstalls()) {
                    Log.w("MainActivity", "No permission to install packages")
                    // 引导用户到设置页面授权
                    val intent = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES)
                    intent.data = Uri.parse("package:$packageName")
                    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    startActivity(intent)
                    return false
                }
            }

            // 从 assets 复制 Termux APK 到缓存目录
            val apkFile = File(cacheDir, TERMUX_APK_NAME)
            assets.open(TERMUX_APK_NAME).use { input ->
                FileOutputStream(apkFile).use { output ->
                    input.copyTo(output)
                }
            }

            // 使用 FileProvider 获取 URI
            val apkUri = FileProvider.getUriForFile(
                this,
                "${packageName}.fileprovider",
                apkFile
            )

            // 启动安装
            val installIntent = Intent(Intent.ACTION_INSTALL_PACKAGE)
            installIntent.data = apkUri
            installIntent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            installIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(installIntent)

            Log.i("MainActivity", "Termux installation started")
            true
        } catch (e: Exception) {
            Log.e("MainActivity", "Failed to install bundled Termux: ${e.message}", e)
            false
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

    private fun stopGenesisService(): Boolean {
        return try {
            val process = Runtime.getRuntime().exec("pkill -f genesis.main")
            process.waitFor()
            true
        } catch (e: Exception) {
            false
        }
    }

    private fun isGenesisRunning(): Boolean {
        return try {
            val process = Runtime.getRuntime().exec("pgrep -f genesis.main")
            val exitCode = process.waitFor()
            exitCode == 0
        } catch (e: Exception) {
            false
        }
    }
}
