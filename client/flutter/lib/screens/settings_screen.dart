import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/app_state.dart';
import '../l10n/app_localizations.dart';

/// 设置界面 - Termux 集成
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  static const _channel = MethodChannel('com.virtualworld.genesis/termux');

  String _selectedLanguage = 'zh';
  bool _isLoading = true;

  // Termux 状态
  bool _termuxInstalled = false;
  bool _genesisInstalled = false;
  bool _genesisRunning = false;

  // 安装状态
  bool _isInstalling = false;
  String _installStage = '';
  int _installProgress = 0;

  @override
  void initState() {
    super.initState();
    _loadSettings();
    _setupProgressListener();
  }

  void _setupProgressListener() {
    _channel.setMethodCallHandler((call) async {
      if (call.method == 'installProgress') {
        final args = call.arguments as Map<dynamic, dynamic>;
        if (mounted) {
          setState(() {
            _installStage = args['stage'] as String? ?? '';
            _installProgress = args['progress'] as int? ?? 0;
          });
        }
      }
      return null;
    });
  }

  Future<void> _loadSettings() async {
    final prefs = await SharedPreferences.getInstance();
    if (!mounted) return;

    setState(() {
      _selectedLanguage = prefs.getString('language') ?? 'zh';
      _isLoading = false;
    });

    // 检查 Termux 状态
    if (Platform.isAndroid) {
      await _checkAllStatus();
    }
  }

  Future<void> _checkAllStatus() async {
    try {
      final termuxOk = await _channel.invokeMethod('checkTermux') as bool;
      final genesisOk = await _channel.invokeMethod('isGenesisInstalled') as bool;
      final running = await _channel.invokeMethod('checkServiceRunning') as bool;

      if (mounted) {
        setState(() {
          _termuxInstalled = termuxOk;
          _genesisInstalled = genesisOk;
          _genesisRunning = running;
        });
      }
    } catch (e) {
      debugPrint('Failed to check status: $e');
    }
  }

  Future<void> _updateLanguage(String lang) async {
    setState(() => _selectedLanguage = lang);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('language', lang);
    context.read<AppState>().setLanguage(lang);
  }

  /// 打开 Termux 下载页面
  Future<void> _openTermuxDownload() async {
    try {
      await _channel.invokeMethod('openTermuxStore');
    } catch (e) {
      debugPrint('Failed to open store: $e');
    }
  }

  /// 一键安装 Genesis
  Future<void> _installGenesis() async {
    if (_isInstalling) return;

    setState(() {
      _isInstalling = true;
      _installStage = '准备安装...';
      _installProgress = 0;
    });

    try {
      final result = await _channel.invokeMethod('installGenesis') as Map;

      if (mounted) {
        final success = result['success'] as bool;
        final message = result['message'] as String;

        setState(() {
          _isInstalling = false;
          if (success) {
            _genesisInstalled = true;
          }
        });

        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(message),
            backgroundColor: success ? Colors.green : Colors.red,
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        setState(() => _isInstalling = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('安装失败: $e'), backgroundColor: Colors.red),
        );
      }
    }
  }

  /// 启动服务
  Future<void> _startService() async {
    try {
      final success = await _channel.invokeMethod('startGenesis') as bool;
      if (success && mounted) {
        setState(() => _genesisRunning = true);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Genesis 服务已启动'), backgroundColor: Colors.green),
        );
        // 延迟检查确认
        Future.delayed(Duration(seconds: 2), () => _checkAllStatus());
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('启动失败: $e'), backgroundColor: Colors.red),
        );
      }
    }
  }

  /// 停止服务
  Future<void> _stopService() async {
    try {
      await _channel.invokeMethod('stopGenesis');
      if (mounted) {
        setState(() => _genesisRunning = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Genesis 服务已停止')),
        );
      }
    } catch (e) {
      debugPrint('Failed to stop service: $e');
    }
  }

  /// 打开 Termux 应用
  Future<void> _openTermux() async {
    try {
      await _channel.invokeMethod('openTermux');
    } catch (e) {
      debugPrint('Failed to open Termux: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context);

    if (_isLoading) {
      return Scaffold(
        appBar: AppBar(title: Text(loc?.settings ?? 'Settings')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: Text(loc?.settings ?? 'Settings'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _checkAllStatus,
            tooltip: '刷新状态',
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // === Termux 服务状态 ===
          if (Platform.isAndroid) ...[
            _buildSectionHeader('Termux 服务'),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: _isInstalling
                    ? _buildInstallProgress()
                    : _buildStatusPanel(),
              ),
            ),
            const SizedBox(height: 24),
          ],

          // === 语言设置 ===
          _buildSectionHeader(loc?.language ?? 'Language'),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  RadioListTile<String>(
                    title: const Text('English'),
                    value: 'en',
                    groupValue: _selectedLanguage,
                    onChanged: (value) => _updateLanguage(value!),
                  ),
                  RadioListTile<String>(
                    title: const Text('简体中文'),
                    value: 'zh',
                    groupValue: _selectedLanguage,
                    onChanged: (value) => _updateLanguage(value!),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),

          // === 关于 ===
          _buildSectionHeader(loc?.about ?? 'About'),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    loc?.appName ?? 'Genesis',
                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 18),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    loc?.appDesc ?? 'A world entirely inhabited by silicon-based life forms.',
                    style: const TextStyle(color: Colors.white60),
                  ),
                  const SizedBox(height: 16),
                  const Text('Version: 0.1.0'),
                  const SizedBox(height: 8),
                  const Text('© 2024 Genesis Project'),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// 构建状态面板
  Widget _buildStatusPanel() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Step 1: Termux 安装状态
        _buildStatusRow(
          'Step 1: Termux',
          _termuxInstalled,
          _termuxInstalled ? '已安装' : '未安装',
        ),
        if (!_termuxInstalled) ...[
          const SizedBox(height: 12),
          ElevatedButton.icon(
            onPressed: _openTermuxDownload,
            icon: const Icon(Icons.download),
            label: const Text('下载 Termux (F-Droid)'),
          ),
        ],

        const Divider(height: 24),

        // Step 2: Genesis 安装状态
        _buildStatusRow(
          'Step 2: Genesis',
          _genesisInstalled,
          _genesisInstalled ? '已安装' : '未安装',
        ),
        if (_termuxInstalled && !_genesisInstalled) ...[
          const SizedBox(height: 12),
          ElevatedButton.icon(
            onPressed: _installGenesis,
            icon: const Icon(Icons.install_mobile),
            label: const Text('一键安装 Genesis'),
          ),
        ],

        const Divider(height: 24),

        // Step 3: 服务状态
        _buildStatusRow(
          'Step 3: 服务',
          _genesisRunning,
          _genesisRunning ? '运行中' : '已停止',
        ),
        if (_genesisInstalled) ...[
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: !_genesisRunning ? _startService : null,
                  icon: const Icon(Icons.play_arrow),
                  label: const Text('启动服务'),
                  style: ElevatedButton.styleFrom(backgroundColor: Colors.green),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: _genesisRunning ? _stopService : null,
                  icon: const Icon(Icons.stop),
                  label: const Text('停止服务'),
                  style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: _openTermux,
            icon: const Icon(Icons.terminal),
            label: const Text('打开 Termux'),
          ),
        ],
      ],
    );
  }

  /// 构建安装进度
  Widget _buildInstallProgress() {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const CircularProgressIndicator(),
        const SizedBox(height: 16),
        Text(
          _installStage,
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 8),
        LinearProgressIndicator(value: _installProgress / 100),
        const SizedBox(height: 8),
        Text('$_installProgress%'),
      ],
    );
  }

  Widget _buildStatusRow(String label, bool isOk, String status) {
    return Row(
      children: [
        Icon(
          isOk ? Icons.check_circle : Icons.radio_button_unchecked,
          color: isOk ? Colors.green : Colors.grey,
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Text(label, style: const TextStyle(fontWeight: FontWeight.bold)),
        ),
        Text(
          status,
          style: TextStyle(
            color: isOk ? Colors.green : Colors.orange,
            fontSize: 12,
          ),
        ),
      ],
    );
  }

  Widget _buildSectionHeader(String title) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        title,
        style: const TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.bold,
          color: Colors.white60,
        ),
      ),
    );
  }
}
