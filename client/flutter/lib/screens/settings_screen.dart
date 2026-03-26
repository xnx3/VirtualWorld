import 'dart:io';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:http/http.dart' as http;

import '../services/app_state.dart';
import '../l10n/app_localizations.dart';

/// 设置界面 - Termux 集成 + API 配置
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

  // API 配置
  final _baseUrlController = TextEditingController(text: 'https://api.openai.com/v1');
  final _apiKeyController = TextEditingController();
  final _modelController = TextEditingController(text: 'gpt-4o-mini');
  bool _isSaving = false;
  bool _isTesting = false;
  bool _apiConfigured = false;
  bool _obscureApiKey = true;

  // 预设 API 提供商
  final _presets = [
    {'name': 'OpenAI', 'baseUrl': 'https://api.openai.com/v1', 'model': 'gpt-4o-mini'},
    {'name': 'DeepSeek', 'baseUrl': 'https://api.deepseek.com/v1', 'model': 'deepseek-chat'},
    {'name': 'Claude', 'baseUrl': 'https://api.anthropic.com/v1', 'model': 'claude-3-haiku-20240307'},
    {'name': '本地 Ollama', 'baseUrl': 'http://localhost:11434/v1', 'model': 'llama3'},
  ];

  @override
  void initState() {
    super.initState();
    _loadSettings();
    _setupProgressListener();
  }

  @override
  void dispose() {
    _baseUrlController.dispose();
    _apiKeyController.dispose();
    _modelController.dispose();
    super.dispose();
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
      await _loadAPIConfig();
    }
  }

  Future<void> _loadAPIConfig() async {
    try {
      final config = await _channel.invokeMethod('readLLMConfig') as Map;
      if (mounted && config.isNotEmpty) {
        setState(() {
          _baseUrlController.text = config['base_url'] ?? 'https://api.openai.com/v1';
          _apiKeyController.text = config['api_key'] ?? '';
          _modelController.text = config['model'] ?? 'gpt-4o-mini';
          _apiConfigured = _apiKeyController.text.isNotEmpty;
        });
      }
    } catch (e) {
      debugPrint('Failed to load API config: $e');
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

  /// 应用预设配置
  void _applyPreset(String name) {
    final preset = _presets.firstWhere((p) => p['name'] == name, orElse: () => _presets[0]);
    setState(() {
      _baseUrlController.text = preset['baseUrl']!;
      _modelController.text = preset['model']!;
    });
  }

  /// 保存并测试 API 配置
  Future<void> _saveAndTestConfig() async {
    if (_apiKeyController.text.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('请输入 API Key'), backgroundColor: Colors.orange),
      );
      return;
    }

    setState(() => _isSaving = true);

    try {
      // 先测试 API
      final testResult = await _testAPIConnection();

      if (!testResult['success']) {
        setState(() => _isSaving = false);
        _showErrorDialog('API 测试失败', testResult['error']);
        return;
      }

      // 测试成功，保存配置
      final saveResult = await _channel.invokeMethod('saveLLMConfig', {
        'baseUrl': _baseUrlController.text.trim(),
        'apiKey': _apiKeyController.text.trim(),
        'model': _modelController.text.trim(),
      }) as Map;

      setState(() {
        _isSaving = false;
        _apiConfigured = true;
      });

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('✓ API 配置已保存并验证成功'),
            backgroundColor: Colors.green,
          ),
        );
      }
    } catch (e) {
      setState(() => _isSaving = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('保存失败: $e'), backgroundColor: Colors.red),
        );
      }
    }
  }

  /// 测试 API 连接
  Future<Map<String, dynamic>> _testAPIConnection() async {
    setState(() => _isTesting = true);

    try {
      final baseUrl = _baseUrlController.text.trim();
      final apiKey = _apiKeyController.text.trim();
      final model = _modelController.text.trim();

      // 构建请求
      final uri = Uri.parse('$baseUrl/chat/completions');
      final response = await http.post(
        uri,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $apiKey',
        },
        body: jsonEncode({
          'model': model,
          'messages': [
            {'role': 'user', 'content': 'Say "OK" in one word.'}
          ],
          'max_tokens': 10,
        }),
      ).timeout(Duration(seconds: 30));

      setState(() => _isTesting = false);

      if (response.statusCode == 200) {
        final body = jsonDecode(response.body);
        // 检查是否有有效响应
        if (body['choices'] != null && (body['choices'] as List).isNotEmpty) {
          return {'success': true};
        } else {
          return {'success': false, 'error': '响应格式异常: ${response.body}'};
        }
      } else {
        // 解析错误信息
        String errorMessage = 'HTTP ${response.statusCode}';
        try {
          final errorBody = jsonDecode(response.body);
          if (errorBody['error'] != null) {
            errorMessage = errorBody['error']['message'] ?? errorBody['error'].toString();
          }
        } catch (_) {}
        return {'success': false, 'error': errorMessage};
      }
    } catch (e) {
      setState(() => _isTesting = false);
      return {'success': false, 'error': e.toString()};
    }
  }

  /// 显示错误对话框
  void _showErrorDialog(String title, String error) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Row(
          children: [
            Icon(Icons.error, color: Colors.red),
            SizedBox(width: 8),
            Text(title),
          ],
        ),
        content: SingleChildScrollView(
          child: SelectableText(
            error,
            style: TextStyle(color: Colors.red[300], fontSize: 12),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text('确定'),
          ),
        ],
      ),
    );
  }

  /// 安装内嵌的 Termux
  Future<void> _installBundledTermux() async {
    try {
      // 先检查 Termux APK 是否存在
      final checkResult = await _channel.invokeMethod('checkTermuxApkExists') as Map;
      debugPrint('Termux APK check: $checkResult');

      if (checkResult['exists'] != true) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Termux APK 不存在: ${checkResult['apkName']}'),
              backgroundColor: Colors.red,
              duration: Duration(seconds: 5),
            ),
          );
        }
        return;
      }

      // 检查是否有安装权限
      final canInstall = await _channel.invokeMethod('canInstallPackages') as bool;
      if (!canInstall) {
        // 请求权限
        await _channel.invokeMethod('requestInstallPermission');
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('请授权后重试'), backgroundColor: Colors.orange),
          );
        }
        return;
      }

      // 安装内嵌的 Termux
      final result = await _channel.invokeMethod('installBundledTermux') as Map;
      final success = result['success'] as bool;

      if (success && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('请在系统界面完成 Termux 安装'), backgroundColor: Colors.blue),
        );
        // 延迟检查安装状态
        Future.delayed(Duration(seconds: 5), () => _checkAllStatus());
      } else if (mounted) {
        final error = result['error'] ?? '未知错误';
        final stage = result['stage'] ?? '';
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('安装失败 [$stage]: $error'),
            backgroundColor: Colors.red,
            duration: Duration(seconds: 5),
          ),
        );
      }
    } catch (e) {
      debugPrint('Failed to install bundled Termux: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('安装异常: $e'),
            backgroundColor: Colors.red,
            duration: Duration(seconds: 5),
          ),
        );
      }
    }
  }

  /// 打开 Termux 下载页面（保留兼容性，但改用内嵌安装）
  Future<void> _openTermuxDownload() async {
    await _installBundledTermux();
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
          // === LLM API 配置 ===
          _buildSectionHeader('LLM API 配置'),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: _buildAPIConfigPanel(),
            ),
          ),
          const SizedBox(height: 24),

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

  /// 构建 API 配置面板
  Widget _buildAPIConfigPanel() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // 预设选择
        Text('快速选择:', style: TextStyle(color: Colors.white60, fontSize: 12)),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          children: _presets.map((p) => ActionChip(
            label: Text(p['name']!),
            onPressed: () => _applyPreset(p['name']!),
          )).toList(),
        ),
        const SizedBox(height: 16),

        // Base URL
        TextField(
          controller: _baseUrlController,
          decoration: const InputDecoration(
            labelText: 'API Base URL',
            hintText: 'https://api.openai.com/v1',
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 12),

        // API Key
        TextField(
          controller: _apiKeyController,
          obscureText: _obscureApiKey,
          decoration: InputDecoration(
            labelText: 'API Key',
            hintText: 'sk-...',
            border: OutlineInputBorder(),
            suffixIcon: IconButton(
              icon: Icon(_obscureApiKey ? Icons.visibility : Icons.visibility_off),
              onPressed: () => setState(() => _obscureApiKey = !_obscureApiKey),
            ),
          ),
        ),
        const SizedBox(height: 12),

        // Model
        TextField(
          controller: _modelController,
          decoration: const InputDecoration(
            labelText: 'Model',
            hintText: 'gpt-4o-mini',
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 16),

        // 状态指示
        if (_apiConfigured)
          Row(
            children: [
              Icon(Icons.check_circle, color: Colors.green, size: 16),
              SizedBox(width: 4),
              Text('已配置', style: TextStyle(color: Colors.green, fontSize: 12)),
            ],
          ),
        const SizedBox(height: 12),

        // 保存按钮
        SizedBox(
          width: double.infinity,
          child: ElevatedButton.icon(
            onPressed: _isSaving ? null : _saveAndTestConfig,
            icon: _isSaving || _isTesting
                ? SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : Icon(Icons.save),
            label: Text(_isTesting ? '测试中...' : '保存并验证'),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.deepPurple,
            ),
          ),
        ),
      ],
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
            icon: const Icon(Icons.install_mobile),
            label: const Text('安装 Termux'),
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
