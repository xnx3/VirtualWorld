# Termux 内置 APK 集成方案

## 目标

将 Termux APK 内置于 Genesis APK 中，用户安装 Genesis APK 后：
1. 自动检测 Termux 是否已安装
2. 未安装时，提示并自动安装内置的 Termux APK
3. 一键完成所有配置

**用户体验**：安装一个 APK → 打开 → 一键启动，无需手动下载 Termux。

---

## 方案设计

### 架构

```
Genesis APK
├── Flutter 应用（GUI）
├── assets/
│   ├── genesis/              # Genesis 后端源码
│   ├── genesis-termux-bundle.tar.gz  # 预构建 Python 环境
│   ├── termux-app.apk        # Termux APK（内置）
│   ├── install.sh
│   ├── quick_install.sh
│   └── start_genesis.sh
└── 自动安装逻辑
```

### 安装流程

```
用户打开 Genesis App
        │
        ▼
检测 Termux 是否已安装
        │
   ┌────┴────┐
   │         │
   ▼         ▼
 已安装    未安装
   │         │
   │         ▼
   │    提示安装 Termux
   │         │
   │         ▼
   │    用户授权"安装未知应用"
   │         │
   │         ▼
   │    自动安装内置 Termux APK
   │         │
   └────┬────┘
        │
        ▼
  检测 Genesis 是否已安装
        │
   ┌────┴────┐
   │         │
   ▼         ▼
 已安装    未安装
   │         │
   │         ▼
   │    复制文件到共享存储
   │         │
   │         ▼
   │    在 Termux 中执行 quick_install.sh
   │         │
   └────┬────┘
        │
        ▼
    一键启动服务
```

---

## 实现步骤

### Step 1: 下载 Termux APK

从 F-Droid 下载最新版 Termux APK：

```bash
# 下载地址
# https://f-droid.org/packages/com.termux/

# 或使用 wget
wget -O termux-app.apk https://f-droid.org/repo/com.termux_1020.apk
```

将下载的 APK 放入：
```
client/flutter/android/app/src/main/assets/termux-app.apk
```

### Step 2: 更新 build.gradle

在 `client/flutter/android/app/build.gradle` 中添加：

```groovy
// 复制 Termux APK 到 assets
task copyTermuxApk(type: Copy) {
    description = 'Copy Termux APK to Android assets'
    from '../../../termux/termux-app.apk'
    into 'src/main/assets'
    onlyIf { file('../../../termux/termux-app.apk').exists() }
}

preBuild.dependsOn copyTermuxApk
```

### Step 3: 更新 GenesisInstaller.kt

添加 Termux APK 自动安装逻辑：

```kotlin
/**
 * 检查 Termux 是否已安装
 */
fun isTermuxInstalled(context: Context): Boolean {
    return try {
        context.packageManager.getPackageInfo("com.termux", 0)
        true
    } catch (e: Exception) {
        false
    }
}

/**
 * 安装内置的 Termux APK
 * 需要 REQUEST_INSTALL_PACKAGES 权限
 */
fun installTermuxFromAssets(context: Context): InstallResult {
    return try {
        // 从 assets 复制到缓存目录
        val apkFile = File(context.cacheDir, "termux-app.apk")
        context.assets.open("termux-app.apk").use { input ->
            FileOutputStream(apkFile).use { output ->
                input.copyTo(output)
            }
        }

        // 触发安装
        val intent = Intent(Intent.ACTION_VIEW)
        intent.setDataAndType(
            FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", apkFile),
            "application/vnd.android.package-archive"
        )
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)

        InstallResult(success = true, message = "Termux 安装已启动，请完成安装后重试")
    } catch (e: Exception) {
        InstallResult(success = false, message = "安装 Termux 失败: ${e.message}")
    }
}
```

### Step 4: 添加权限

在 `AndroidManifest.xml` 中添加：

```xml
<!-- 安装 APK 权限 -->
<uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES" />

<!-- FileProvider -->
<provider
    android:name="androidx.core.content.FileProvider"
    android:authorities="${applicationId}.fileprovider"
    android:exported="false"
    android:grantUriPermissions="true">
    <meta-data
        android:name="android.support.FILE_PROVIDER_PATHS"
        android:resource="@xml/file_paths" />
</provider>
```

创建 `res/xml/file_paths.xml`：

```xml
<?xml version="1.0" encoding="utf-8"?>
<paths>
    <cache-path name="cache" path="." />
</paths>
```

### Step 5: 更新 Flutter UI

在设置界面添加 Termux 安装检测和引导：

```dart
// 检测 Termux
if (!await genesisInstaller.isTermuxInstalled()) {
  // 显示安装提示
  showDialog(
    context: context,
    builder: (context) => AlertDialog(
      title: Text('需要安装 Termux'),
      content: Text('Genesis 需要 Termux 来运行后端服务。\n是否立即安装？'),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: Text('取消'),
        ),
        ElevatedButton(
          onPressed: () {
            genesisInstaller.installTermuxFromAssets();
            Navigator.pop(context);
          },
          child: Text('安装 Termux'),
        ),
      ],
    ),
  );
}
```

---

## APK 大小估算

| 组件 | 大小 |
|------|------|
| Flutter 应用 | ~15 MB |
| Genesis 源码 | ~1 MB |
| Termux APK | ~30 MB |
| Genesis Bundle | ~30-50 MB |
| **总计** | **~80-100 MB** |

---

## 注意事项

### 权限要求

- `REQUEST_INSTALL_PACKAGES` - 安装应用权限
- `MANAGE_EXTERNAL_STORAGE` 或 `READ/WRITE_EXTERNAL_STORAGE` - 存储权限

### 用户操作流程

1. 打开 Genesis 应用
2. 提示"需要安装 Termux" → 点击"安装"
3. 系统提示"允许安装未知应用" → 允许
4. Termux 安装完成 → 返回 Genesis
5. 点击"一键安装 Genesis"
6. 完成，可以启动服务

### 兼容性

- Android 8.0+ 需要 `REQUEST_INSTALL_PACKAGES` 权限
- Android 11+ 需要用户手动授权"安装未知应用"
- 部分国产 ROM 可能有额外限制

---

## 替代方案

### 方案 B：Termux 作为 AAR 模块

将 Termux 编译为 AAR 库，直接集成到应用中。

**优点**：
- 无需单独安装
- 体验更统一

**缺点**：
- 需要从 Termux 源码编译
- 集成复杂度高
- 可能与系统 Termux 冲突

### 方案 C：内置最小 Python 环境

使用 Chaquopy 或 similar 方案内置 Python。

**优点**：
- 完全不依赖 Termux
- 启动速度快

**缺点**：
- Chaquopy 付费
- Genesis 依赖较多原生库
- 维护成本高

---

## 相关文件

- `client/flutter/android/app/src/main/assets/termux-app.apk` - 内置 Termux APK
- `client/flutter/android/app/src/main/kotlin/.../GenesisInstaller.kt` - 安装逻辑
- `client/flutter/android/app/src/main/AndroidManifest.xml` - 权限配置
