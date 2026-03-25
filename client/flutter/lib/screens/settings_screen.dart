import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/app_state.dart';
import '../services/websocket_service.dart';
import '../l10n/app_localizations.dart';

/// 设置界面
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late TextEditingController _serverController;
  late TextEditingController _portController;
  String _selectedLanguage = 'zh';
  bool _isLoading = true;
  bool _isConnecting = false;

  @override
  void initState() {
    super.initState();
    _serverController = TextEditingController();
    _portController = TextEditingController();
    _loadSettings();
  }

  Future<void> _loadSettings() async {
    final prefs = await SharedPreferences.getInstance();
    if (!mounted) return;
    final ws = context.read<WebSocketService>();

    setState(() {
      _serverController.text = prefs.getString('server_host') ?? ws.serverUrl;
      _portController.text = (prefs.getInt('server_port') ?? ws.serverPort).toString();
      _selectedLanguage = prefs.getString('language') ?? 'zh';
      _isLoading = false;
    });
  }

  Future<void> _saveSettings() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('server_host', _serverController.text.trim());
    await prefs.setInt('server_port', int.tryParse(_portController.text) ?? WebSocketService.defaultPort);
    await prefs.setString('language', _selectedLanguage);
  }

  @override
  void dispose() {
    _serverController.dispose();
    _portController.dispose();
    super.dispose();
  }

  Future<void> _handleConnect() async {
    final host = _serverController.text.trim();
    final portStr = _portController.text.trim();
    final port = int.tryParse(portStr) ?? WebSocketService.defaultPort;

    // 验证端口范围
    if (port < 1 || port > 65535) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('端口必须在 1-65535 范围内')),
        );
      }
      return;
    }

    // 验证主机地址
    if (host.isEmpty) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('请输入服务器地址')),
        );
      }
      return;
    }

    setState(() => _isConnecting = true);

    await _saveSettings();
    final ws = context.read<WebSocketService>();
    final success = await ws.connect(host: host, port: port);

    if (mounted) {
      setState(() => _isConnecting = false);

      if (success) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('连接成功！'),
            backgroundColor: Colors.green,
          ),
        );
      }
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
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // 连接设置
          _buildSectionHeader(loc?.connection ?? 'Connection'),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // 服务器地址
                  TextField(
                    controller: _serverController,
                    decoration: InputDecoration(
                      labelText: loc?.serverAddress ?? 'Server Address',
                      hintText: '192.168.31.250',
                      border: const OutlineInputBorder(),
                      helperText: '输入 Genesis 服务器的 IP 地址',
                    ),
                  ),
                  const SizedBox(height: 12),
                  // 端口
                  TextField(
                    controller: _portController,
                    decoration: InputDecoration(
                      labelText: loc?.port ?? 'Port',
                      hintText: '19842',
                      border: const OutlineInputBorder(),
                    ),
                    keyboardType: TextInputType.number,
                  ),
                  const SizedBox(height: 16),

                  // 连接状态和按钮
                  Consumer<WebSocketService>(
                    builder: (context, ws, _) {
                      return Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          // 状态行
                          Row(
                            children: [
                              Icon(
                                ws.isConnected
                                    ? Icons.check_circle
                                    : (ws.isConnecting || _isConnecting)
                                        ? Icons.pending
                                        : Icons.error_outline,
                                color: ws.isConnected
                                    ? Colors.green
                                    : (ws.isConnecting || _isConnecting)
                                        ? Colors.orange
                                        : Colors.red,
                              ),
                              const SizedBox(width: 8),
                              Text(
                                ws.isConnected
                                    ? (loc?.connected ?? 'Connected')
                                    : (ws.isConnecting || _isConnecting)
                                        ? (loc?.connecting ?? 'Connecting...')
                                        : (loc?.disconnected ?? 'Disconnected'),
                                style: TextStyle(
                                  color: ws.isConnected
                                      ? Colors.green
                                      : (ws.isConnecting || _isConnecting)
                                          ? Colors.orange
                                          : Colors.red,
                                ),
                              ),
                              if (ws.isConnecting || _isConnecting) ...[
                                const SizedBox(width: 8),
                                const SizedBox(
                                  width: 16,
                                  height: 16,
                                  child: CircularProgressIndicator(strokeWidth: 2),
                                ),
                              ],
                              const Spacer(),
                              // 连接按钮
                              ElevatedButton(
                                onPressed: (ws.isConnecting || _isConnecting)
                                    ? null
                                    : _handleConnect,
                                child: Text(loc?.connect ?? 'Connect'),
                              ),
                            ],
                          ),

                          // 错误信息
                          if (ws.lastError != null && !ws.isConnected) ...[
                            const SizedBox(height: 12),
                            Container(
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: Colors.red.withOpacity(0.1),
                                borderRadius: BorderRadius.circular(8),
                                border: Border.all(color: Colors.red.withOpacity(0.3)),
                              ),
                              child: Row(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  const Icon(Icons.warning_amber, color: Colors.orange, size: 20),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: Text(
                                      ws.lastError!,
                                      style: const TextStyle(fontSize: 12, color: Colors.white70),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ],
                      );
                    },
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),

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

  Future<void> _updateLanguage(String lang) async {
    setState(() => _selectedLanguage = lang);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('language', lang);
    context.read<AppState>().setLanguage(lang);
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