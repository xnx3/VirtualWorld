import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../services/app_state.dart';
import '../services/websocket_service.dart';
import '../services/log_service.dart';
import '../widgets/widgets.dart';
import '../l10n/app_localizations.dart';

/// 主界面
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _taskController = TextEditingController();
  StreamSubscription? _eventSubscription;
  StreamSubscription? _connectionSubscription;
  bool _initialized = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_initialized) {
      _initialized = true;
      // 监听连接状态变化
      _setupConnectionListener();
      // 延迟连接，避免在 build 中调用
      Future.microtask(() => _connectToBackend());
    }
  }

  void _setupConnectionListener() {
    final ws = context.read<WebSocketService>();
    _connectionSubscription = ws.connectionChanges.listen((connected) {
      if (connected && mounted) {
        _setupEventListener();
        context.read<AppState>().setRunning(true);
      } else if (!connected && mounted) {
        context.read<AppState>().setRunning(false);
      }
    });
  }

  void _setupEventListener() {
    _eventSubscription?.cancel();
    final ws = context.read<WebSocketService>();
    final state = context.read<AppState>();
    _eventSubscription = ws.events.listen((event) {
      state.handleServerEvent(event);
    });
  }

  Future<void> _connectToBackend() async {
    if (!mounted) return;

    final ws = context.read<WebSocketService>();
    final state = context.read<AppState>();
    final logService = context.read<LogService>();

    logService.info('正在连接本地服务...', source: 'flutter');

    final connected = await ws.connect();

    if (!mounted) return;

    if (connected) {
      logService.info('连接成功', source: 'flutter');
      // Event listener is set up via connectionChanges stream in _setupConnectionListener
      // Only set running state here; avoid duplicate _setupEventListener call
      state.setRunning(true);
    } else {
      logService.error('连接失败: ${ws.lastError ?? "未知错误"}', source: 'flutter');
    }
  }

  Future<void> _retryConnect() async {
    final ws = context.read<WebSocketService>();
    await ws.retryConnect();
  }

  @override
  void dispose() {
    _eventSubscription?.cancel();
    _connectionSubscription?.cancel();
    _taskController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context);

    return Scaffold(
      appBar: _buildAppBar(loc),
      drawer: _buildDrawer(loc),
      body: Consumer<AppState>(
        builder: (context, state, child) {
          if (!state.isRunning) {
            return _buildDisconnectedState(loc);
          }
          return _buildMainContent(state, loc);
        },
      ),
      floatingActionButton: _buildFab(loc),
      bottomNavigationBar: _buildBottomBar(loc),
    );
  }

  PreferredSizeWidget _buildAppBar(AppLocalizations? loc) {
    return AppBar(
      title: Row(
        children: [
          Text(loc?.appName ?? 'Genesis',
              style: const TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(width: 8),
          Text(loc?.appName == '创世' ? 'Genesis' : '创世',
              style: const TextStyle(fontSize: 14, color: Colors.white60)),
        ],
      ),
      actions: [
        IconButton(
          icon: const Icon(Icons.settings),
          onPressed: () => Navigator.pushNamed(context, '/settings'),
        ),
        Consumer<AppState>(
          builder: (context, state, _) {
            return Container(
              margin: const EdgeInsets.only(right: 8),
              child: Chip(
                label: Text(
                    state.isRunning ? (loc?.running ?? 'Running') : (loc?.stopped ?? 'Stopped')),
                backgroundColor: state.isRunning ? Colors.green : Colors.red,
                labelStyle: const TextStyle(color: Colors.white, fontSize: 12),
              ),
            );
          },
        ),
      ],
    );
  }

  Widget _buildDrawer(AppLocalizations? loc) {
    return Drawer(
      child: ListView(
        children: [
          DrawerHeader(
            decoration: const BoxDecoration(color: Colors.deepPurple),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                Text(loc?.appName ?? 'Genesis',
                    style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
                const SizedBox(height: 8),
                Text(loc?.appDesc ?? 'Silicon Civilization',
                    style: const TextStyle(color: Colors.white70)),
              ],
            ),
          ),
          ListTile(
            leading: const Icon(Icons.home),
            title: Text(loc?.dashboard ?? 'Dashboard'),
            selected: true,
            onTap: () => Navigator.pop(context),
          ),
          ListTile(
            leading: const Icon(Icons.history),
            title: Text(loc?.chronicle ?? 'Chronicle'),
            onTap: () => Navigator.pop(context),
          ),
          ListTile(
            leading: const Icon(Icons.public),
            title: Text(loc?.world ?? 'World'),
            onTap: () => Navigator.pop(context),
          ),
          const Divider(),
          ListTile(
            leading: const Icon(Icons.article_outlined),
            title: const Text('日志'),
            onTap: () {
              Navigator.pop(context);
              Navigator.pushNamed(context, '/logs');
            },
          ),
          ListTile(
            leading: const Icon(Icons.settings),
            title: Text(loc?.settings ?? 'Settings'),
            onTap: () {
              Navigator.pop(context);
              Navigator.pushNamed(context, '/settings');
            },
          ),
        ],
      ),
    );
  }

  Widget _buildDisconnectedState(AppLocalizations? loc) {
    return Consumer<WebSocketService>(
      builder: (context, ws, _) {
        return Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                // 图标
                Icon(
                  ws.isConnecting || ws.isReconnecting
                      ? Icons.cloud_sync
                      : Icons.cloud_off,
                  size: 64,
                  color: ws.isConnecting || ws.isReconnecting
                      ? Colors.orange
                      : Colors.red.withOpacity(0.7),
                ),
                const SizedBox(height: 16),

                // 状态文字
                Text(
                  ws.isConnecting || ws.isReconnecting
                      ? (loc?.connecting ?? 'Connecting...')
                      : (loc?.disconnected ?? 'Disconnected'),
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 16),

                // 错误信息
                if (ws.lastError != null && !ws.isConnecting && !ws.isReconnecting) ...[
                  Container(
                    margin: const EdgeInsets.symmetric(horizontal: 16),
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.red.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: Colors.red.withOpacity(0.3)),
                    ),
                    child: Column(
                      children: [
                        const Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.error_outline, color: Colors.orange, size: 20),
                            SizedBox(width: 8),
                            Text('连接失败',
                                style: TextStyle(
                                    color: Colors.orange, fontWeight: FontWeight.bold)),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Text(
                          ws.lastError!,
                          textAlign: TextAlign.center,
                          style: const TextStyle(color: Colors.white70, fontSize: 13),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 24),
                ],

                // 重试按钮或加载指示器
                if (ws.isConnecting || ws.isReconnecting)
                  const Column(
                    children: [
                      CircularProgressIndicator(),
                      SizedBox(height: 16),
                      Text('正在连接本地服务...',
                          style: TextStyle(color: Colors.white60, fontSize: 12)),
                    ],
                  )
                else ...[
                  ElevatedButton.icon(
                    onPressed: _retryConnect,
                    icon: const Icon(Icons.refresh),
                    label: Text(loc?.retryConnection ?? 'Retry Connection'),
                    style: ElevatedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                    ),
                  ),

                  // Termux 提示
                  if (Platform.isAndroid) ...[
                    const SizedBox(height: 24),
                    OutlinedButton.icon(
                      onPressed: () => Navigator.pushNamed(context, '/settings'),
                      icon: const Icon(Icons.terminal),
                      label: const Text('打开设置启动 Termux 服务'),
                    ),
                  ],
                ],
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildMainContent(AppState state, AppLocalizations? loc) {
    return RefreshIndicator(
      onRefresh: () async {
        context.read<WebSocketService>().requestStatus();
      },
      child: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          // Tick 信息
          TickCard(
            tick: state.currentTick,
            beingName: state.beingName,
            phase: state.beingPhase,
            merit: state.merit,
            karma: state.karma,
            evolutionLevel: state.evolutionLevel,
            generation: state.generation,
          ),
          const SizedBox(height: 12),

          // 当前思考
          if (state.currentThought.isNotEmpty) ...[
            ThinkBubble(
              beingName: state.beingName,
              thought: state.currentThought,
            ),
            const SizedBox(height: 12),
          ],

          // 当前行动
          if (state.currentAction.isNotEmpty) ...[
            ActionCard(
              actionType: state.currentAction,
              details: state.currentActionDetails,
            ),
            const SizedBox(height: 12),
          ],

          // 事件日志
          Text(
            loc?.eventLog ?? 'Event Log',
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          ...state.events.take(20).map((e) => EventLogCard(event: e)),
        ],
      ),
    );
  }

  Widget _buildFab(AppLocalizations? loc) {
    return FloatingActionButton.extended(
      onPressed: () => _showTaskInputDialog(loc),
      icon: const Icon(Icons.assignment),
      label: Text(loc?.assignTask ?? 'Assign Task'),
    );
  }

  Widget _buildBottomBar(AppLocalizations? loc) {
    return BottomAppBar(
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
        children: [
          IconButton(
            icon: const Icon(Icons.play_arrow),
            tooltip: loc?.start ?? 'Start',
            onPressed: () {
              context.read<WebSocketService>().connect();
            },
          ),
          IconButton(
            icon: const Icon(Icons.stop),
            tooltip: loc?.stop ?? 'Stop',
            onPressed: () {
              context.read<WebSocketService>().sendStop();
              context.read<AppState>().setRunning(false);
            },
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: loc?.status ?? 'Status',
            onPressed: () {
              context.read<WebSocketService>().requestStatus();
            },
          ),
        ],
      ),
    );
  }

  void _showTaskInputDialog(AppLocalizations? loc) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(loc?.assignTask ?? 'Assign Task'),
        content: TextField(
          controller: _taskController,
          decoration: InputDecoration(
            hintText: loc?.taskHint ?? 'Enter task description...',
            border: const OutlineInputBorder(),
          ),
          maxLines: 3,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text(loc?.cancel ?? 'Cancel'),
          ),
          ElevatedButton(
            onPressed: () {
              final task = _taskController.text.trim();
              if (task.isNotEmpty) {
                final sent = context.read<WebSocketService>().sendTask(task);
                _taskController.clear();
                Navigator.pop(context);
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text(sent
                        ? (loc?.taskSent ?? 'Task sent to server...')
                        : '发送失败：未连接到服务器'),
                    backgroundColor: sent ? null : Colors.red,
                    duration: const Duration(seconds: 2),
                  ),
                );
              }
            },
            child: Text(loc?.send ?? 'Send'),
          ),
        ],
      ),
    );
  }
}