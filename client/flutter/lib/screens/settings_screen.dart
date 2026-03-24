import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/app_state.dart';
import '../services/websocket_service.dart';

/// 设置界面
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _serverController = TextEditingController(text: '127.0.0.1');
  final _portController = TextEditingController(text: '19842');
  String _selectedLanguage = 'zh';

  @override
  void dispose() {
    _serverController.dispose();
    _portController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Settings'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // 连接设置
          _buildSectionHeader('Connection'),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  TextField(
                    controller: _serverController,
                    decoration: const InputDecoration(
                      labelText: 'Server Address',
                      hintText: '127.0.0.1',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _portController,
                    decoration: const InputDecoration(
                      labelText: 'Port',
                      hintText: '19842',
                      border: OutlineInputBorder(),
                    ),
                    keyboardType: TextInputType.number,
                  ),
                  const SizedBox(height: 16),
                  Consumer<WebSocketService>(
                    builder: (context, ws, _) {
                      return Row(
                        children: [
                          Icon(
                            ws.isConnected ? Icons.check_circle : Icons.error,
                            color: ws.isConnected ? Colors.green : Colors.red,
                          ),
                          const SizedBox(width: 8),
                          Text(
                            ws.isConnected ? 'Connected' : 'Disconnected',
                            style: TextStyle(
                              color: ws.isConnected ? Colors.green : Colors.red,
                            ),
                          ),
                          const Spacer(),
                          ElevatedButton(
                            onPressed: () async {
                              final host = _serverController.text.trim();
                              final port = int.tryParse(_portController.text) ?? 19842;
                              await ws.connect(host: host, port: port);
                              setState(() {});
                            },
                            child: const Text('Connect'),
                          ),
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
          _buildSectionHeader('Language / 语言'),
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
                    onChanged: (value) => setState(() => _selectedLanguage = value!),
                  ),
                  RadioListTile<String>(
                    title: const Text('简体中文'),
                    subtitle: const Text('中文界面'),
                    value: 'zh',
                    groupValue: _selectedLanguage,
                    onChanged: (value) => setState(() => _selectedLanguage = value!),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),

          // 关于
          _buildSectionHeader('About'),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Genesis - Silicon Civilization Simulator',
                    style: TextStyle(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'A world entirely inhabited by silicon-based life forms '
                    'for survival and evolution.',
                    style: TextStyle(color: Colors.white60),
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