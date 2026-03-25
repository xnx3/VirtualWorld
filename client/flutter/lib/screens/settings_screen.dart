import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/app_state.dart';
import '../services/termux_service.dart';
import '../l10n/app_localizations.dart';

/// 设置界面
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  String _selectedLanguage = 'zh';
  bool _isLoading = true;

  // Termux 状态
  bool _termuxAvailable = false;
  bool _termuxRunning = false;
  String _genesisPath = '/data/data/com.termux/files/home/genesis';
  final _pathController = TextEditingController();

  // MethodChannel
  static const _channel = const MethodChannel('com.virtualworld.genesis/termux');

  @override
  void initState() {
    super.initState();
    _loadSettings();
  }

  @override
  void dispose() {
    _pathController.dispose();
    super.dispose();
  }

  Future<void> _loadSettings() async {
    final prefs = await SharedPreferences.getInstance();
    if (!mounted) return;

    setState(() {
      _selectedLanguage = prefs.getString('language') ?? 'zh';
      _genesisPath = prefs.getString('termux_genesis_path') ?? _genesisPath;
      _pathController.text = _genesisPath;
      _isLoading = false;
    });

    // 检查 Termux 状态
    if (Platform.isAndroid) {
      await _checkTermuxStatus();
    }
  }

  Future<void> _checkTermuxStatus() async {
    try {
      final available = await _channel.invokeMethod('checkTermux') as bool;
      final running = await _channel.invokeMethod('checkServiceRunning') as bool;

      if (mounted) {
        setState(() {
          _termuxAvailable = available;
          _termuxRunning = running;
        });
      }
    } catch (e) {
      debugPrint('Failed to check Termux status: $e');
    }
  }

  Future<void> _startService() async {
    try {
      final success = await _channel.invokeMethod('startGenesis') as bool;
      if (success && mounted) {
        setState(() => _termuxRunning = true);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Genesis 服务已启动')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('启动失败: $e')),
        );
      }
    }
  }

  Future<void> _stopService() async {
    try {
      await _channel.invokeMethod('stopGenesis');
      if (mounted) {
        setState(() => _termuxRunning = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Genesis 服务已停止')),
        );
      }
    } catch (e) {
      debugPrint('Failed to stop service: $e');
    }
  }

  Future<void> _openTermux() async {
    try {
      await _channel.invokeMethod('openTermux');
    } catch (e) {
      debugPrint('Failed to open Termux: $e');
    }
  }

  Future<void> _updateLanguage(String lang) async {
    setState(() => _selectedLanguage = lang);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('language', lang);
    context.read<AppState>().setLanguage(lang);
  }

  Future<void> _saveGenesisPath() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('termux_genesis_path', _pathController.text);
    setState(() => _genesisPath = _pathController.text);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('路径已保存')),
    );
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
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // Termux 服务状态
          if (Platform.isAndroid) ...[
            _buildSectionHeader('Termux 服务'),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // 状态指示
                    Row(
                      children: [
                        Icon(
                          _termuxAvailable ? Icons.check_circle : Icons.error,
                          color: _termuxAvailable ? Colors.green : Colors.red,
                        ),
                        const SizedBox(width: 8),
                        Text(
                          _termuxAvailable
                            ? 'Termux 已安装'
                            : 'Termux 未安装',
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            color: _termuxAvailable ? Colors.green : Colors.red,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),

                    // Genesis 安装路径
                    TextField(
                      controller: _pathController,
                      decoration: InputDecoration(
                        labelText: 'Genesis 安装路径',
                        hintText: '/data/data/com.termux/files/home/genesis',
                        suffixIcon: IconButton(
                          icon: const Icon(Icons.save),
                          onPressed: _saveGenesisPath,
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),

                    // 服务控制按钮
                    Row(
                      children: [
                        Expanded(
                          child: ElevatedButton.icon(
                            onPressed: _termuxAvailable && !_termuxRunning
                              ? _startService
                              : null,
                            icon: const Icon(Icons.play_arrow),
                            label: Text('启动服务'),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: ElevatedButton.icon(
                            onPressed: _termuxRunning
                              ? _stopService
                              : null,
                            icon: const Icon(Icons.stop),
                            label: Text('停止服务'),
                            style: ElevatedButton.styleFrom(
                              backgroundColor: Colors.red,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    OutlinedButton.icon(
                      onPressed: _termuxAvailable ? _openTermux : null,
                      icon: const Icon(Icons.terminal),
                      label: Text('打开 Termux'),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 24),
          ],

          // 语言设置
          _buildSectionHeader(loc?.language ?? 'Language'),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  RadioListTile<String>(
                    title: const Text('English'),
                    subtitle: const Text('English interface'),
                    value: 'en',
                    groupValue: _selectedLanguage,
                    onChanged: (value) => _updateLanguage(value!),
                  ),
                  RadioListTile<String>(
                    title: const Text('简体中文'),
                    subtitle: const Text('中文界面'),
                    value: 'zh',
                    groupValue: _selectedLanguage,
                    onChanged: (value) => _updateLanguage(value!),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),

          // 使用说明
          _buildSectionHeader('使用说明'),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Termux 集成步骤：',
                    style: TextStyle(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 8),
                  const Text('1. 从 F-Droid 安装 Termux'),
                  const Text('2. 将 genesis/ 复制到 ~/genesis/'),
                  const Text('3. 运行: bash ~/genesis/termux/install.sh'),
                  const Text('4. 配置 API 密钥'),
                  const Text('5. 点击"启动服务"'),
                  const SizedBox(height: 8),
                  const Text(
                    'API 地址: ws://127.0.0.1:19842',
                    style: TextStyle(color: Colors.cyan),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),

          // 关于
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
