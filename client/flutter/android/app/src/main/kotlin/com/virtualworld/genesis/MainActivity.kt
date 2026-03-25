package com.virtualworld.genesis

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/**
 * Flutter 主活动
 * 提供 Termux 服务控制接口
 */
class MainActivity : FlutterActivity() {

    companion object {
        private const val CHANNEL = "com.virtualworld.genesis/termux"
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL).setMethodCallHandler { call, result ->
            when (call.method) {
                "checkTermux" -> {
                    val installed = isPackageInstalled("com.termux")
                    result.success(installed)
                }
                "openTermux" -> {
                    openTermuxApp()
                    result.success(true)
                }
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
                intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                startActivity(intent)
            }
        } catch (e: Exception) {
            // Termux not installed
        }
    }

    private fun startGenesisService(): Boolean {
        return try {
            // 使用 RUN_COMMAND intent 启动 Genesis
            val intent = android.content.Intent("com.termux.RUN_COMMAND")
            intent.setClassName("com.termux", "com.termux.app.RunCommandService")
            intent.putExtra("com.termux.RUN_COMMAND_PATH", "/data/data/com.termux/files/home/genesis/start_genesis.sh")
            intent.putExtra("com.termux.RUN_COMMAND_WORKDIR", "/data/data/com.termux/files/home/genesis")
            intent.putExtra("com.termux.RUN_COMMAND_BACKGROUND", true)
            startService(intent)
            true
        } catch (e: Exception) {
            false
        }
    }

    private fun stopGenesisService(): Boolean {
        return try {
            // 使用 pkill 停止 Genesis 进程
            val process = Runtime.getRuntime().exec(
                "pkill -f genesis.main"
            )
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
