import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/app_state.dart';
import '../services/websocket_service.dart';
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
  bool _initialized = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_initialized) {
      _initialized = true;
      // 延迟连接，避免在 build 中调用
      Future.microtask(() => _connectToBackend());
    }
  }

  Future<void> _connectToBackend() async {
    final ws = context.read<WebSocketService>();
    final state = context.read<AppState>();

    // 尝试连接
    final connected = await ws.connect();
    if (connected && mounted) {
      // 监听事件
      _eventSubscription = ws.events.listen((event) {
        state.handleServerEvent(event);
      });
      state.setRunning(true);
    }
  }

  @override
  void dispose() {
    _eventSubscription?.cancel();
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
          Text(loc?.appName ?? 'Genesis', style: const TextStyle(fontWeight: FontWeight.bold)),
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
                label: Text(state.isRunning
                  ? (loc?.running ?? 'Running')
                  : (loc?.stopped ?? 'Stopped')),
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
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.cloud_off, size: 64, color: Colors.white30),
          const SizedBox(height: 16),
          Text(loc?.disconnected ?? 'Disconnected'),
          const SizedBox(height: 8),
          Text(
            loc?.appDesc ?? 'Check server connection',
            textAlign: TextAlign.center,
            style: const TextStyle(color: Colors.white60, fontSize: 12),
          ),
          const SizedBox(height: 24),
          Consumer<WebSocketService>(
            builder: (context, ws, _) {
              if (ws.isReconnecting) {
                return Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                    const SizedBox(width: 12),
                    Text(loc?.connecting ?? 'Connecting...'),
                  ],
                );
              }
              return ElevatedButton.icon(
                onPressed: _connectToBackend,
                icon: const Icon(Icons.refresh),
                label: Text(loc?.retryConnection ?? 'Retry Connection'),
              );
            },
          ),
        ],
      ),
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
            spirit: '${(state.spiritPercentage * 100).toInt()}%',
            phase: state.beingPhase,
          ),
          const SizedBox(height: 12),

          // 精神力
          SpiritProgressBar(
            current: state.spiritCurrent,
            maximum: state.spiritMaximum,
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
                context.read<WebSocketService>().sendTask(task);
                _taskController.clear();
                Navigator.pop(context);
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(loc?.taskAssigned ?? 'Task assigned!')),
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