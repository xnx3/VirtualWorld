import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Termux 服务管理器
/// 通过 Android Intent 或 shell 命令控制 Termux 中的 Genesis 服务
class TermuxService with ChangeNotifier {
  bool _isAvailable = false;
  bool _isRunning = false;
  String? _lastError;
  String _genesisPath = '/data/data/com.termux/files/home/genesis';

  bool get isAvailable => _isAvailable;
  bool get isRunning => _isRunning;
  String? get lastError => _lastError;
  String get genesisPath => _genesisPath;

  /// 设置 Genesis 安装路径
  set genesisPath(String path) {
    _genesisPath = path;
    notifyListeners();
  }

  String get _startScript => '$_genesisPath/start_genesis.sh';

  /// 从存储加载配置
  Future<void> loadConfig() async {
    final prefs = await SharedPreferences.getInstance();
    _genesisPath = prefs.getString('termux_genesis_path') ?? _genesisPath;
  }

  /// 保存配置
  Future<void> saveConfig() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('termux_genesis_path', _genesisPath);
  }

  /// 检查 Termux 是否可用
  Future<bool> checkAvailability() async {
    if (!Platform.isAndroid) {
      _isAvailable = false;
      return false;
    }

    try {
      // 检查 Termux 是否安装
      final result = await Process.run(
        'pm',
        ['list', 'packages', 'com.termux'],
      );

      _isAvailable = result.stdout.toString().contains('com.termux');
      notifyListeners();
      return _isAvailable;
    } catch (e) {
      _lastError = '检查 Termux 失败: $e';
      _isAvailable = false;
      notifyListeners();
      return false;
    }
  }

  /// 启动 Genesis 服务
  Future<bool> startService() async {
    if (!_isAvailable) {
      _lastError = 'Termux 未安装';
      notifyListeners();
      return false;
    }

    try {
      // 方法1: 使用 am 命令启动 Termux 并执行脚本
      final result = await Process.run(
        'am',
        [
          'start',
          '-n',
          'com.termux/.HomeActivity',
          '-e',
          'com.termux.RUN_COMMAND_PATH',
          _startScript,
          '-e',
          'com.termux.RUN_COMMAND_WORKDIR',
          _genesisPath,
          '-e',
          'com.termux.RUN_COMMAND_BACKGROUND',
          'true',
        ],
      );

      if (result.exitCode == 0) {
        _isRunning = true;
        _lastError = null;
        notifyListeners();
        return true;
      } else {
        _lastError = '启动失败: ${result.stderr}';
        notifyListeners();
        return false;
      }
    } catch (e) {
      _lastError = '启动服务失败: $e';
      notifyListeners();
      return false;
    }
  }

  /// 停止 Genesis 服务
  Future<bool> stopService() async {
    try {
      // 发送停止信号到 Python 进程
      await Process.run(
        'pkill',
        ['-f', 'genesis.main'],
      );

      _isRunning = false;
      notifyListeners();
      return true;
    } catch (e) {
      _lastError = '停止服务失败: $e';
      notifyListeners();
      return false;
    }
  }

  /// 检查服务状态
  Future<bool> checkServiceStatus() async {
    try {
      final result = await Process.run(
        'pgrep',
        ['-f', 'genesis.main'],
      );

      _isRunning = result.exitCode == 0;
      notifyListeners();
      return _isRunning;
    } catch (e) {
      _isRunning = false;
      notifyListeners();
      return false;
    }
  }

  /// 打开 Termux 应用
  Future<void> openTermux() async {
    await Process.run(
      'am',
      ['start', '-n', 'com.termux/.HomeActivity'],
    );
  }
}
