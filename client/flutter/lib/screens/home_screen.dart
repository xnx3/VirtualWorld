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
  bool _showTaskDialog = false;

  @override
  void initState() {
    super.initState();
    _connectToBackend();
  }

  Future<void> _connectToBackend() async {
    final ws = context.read<WebSocketService>();
    final state = context.read<AppState>();

    // 尝试连接
    final connected = await ws.connect();
    if (connected) {
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
    return Scaffold(
      appBar: _buildAppBar(),
      drawer: _buildDrawer(),
      body: Consumer<AppState>(
        builder: (context, state, child) {
          if (!state.isRunning) {
            return _buildDisconnectedState();
          }
          return _buildMainContent(state);
        },
      ),
      floatingActionButton: _buildFab(),
      bottomNavigationBar: _buildBottomBar(),
    );
  }

  PreferredSizeWidget _buildAppBar() {
    return AppBar(
      title: Row(
        children: [
          Text('Genesis', style: TextStyle(fontWeight: FontWeight.bold)),
          SizedBox(width: 8),
          Text('创世', style: TextStyle(fontSize: 14, color: Colors.white60)),
        ],
      ),
      actions: [
        IconButton(
          icon: const Icon(Icons.settings),
          onPressed: () => Navigator.pushNamed(context, '/settings'),
        ),
        Consumer<AppState>(
          builder: (context, state, _) {
            final loc = AppLocalizations.of(context);
            return Container(
              margin: const EdgeInsets.only(right: 8),
              child: Chip(
                label: Text(state.isRunning ? loc!.running : loc!.stopped),
                backgroundColor: state.isRunning ? Colors.green : Colors.red,
                labelStyle: const TextStyle(color: Colors.white, fontSize: 12),
              ),
            );
          },
        ),
      ],
    );
  }

  Widget _buildDrawer() {
    final loc = AppLocalizations.of(context);
    return Drawer(
      child: ListView(
        children: [
          DrawerHeader(
            decoration: BoxDecoration(color: Colors.deepPurple),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                Text(loc!.appName, style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
                SizedBox(height: 8),
                Text('Silicon Civilization Simulator', style: TextStyle(color: Colors.white70)),
              ],
            ),
          ),
          ListTile(
            leading: const Icon(Icons.home),
            title: Text('Dashboard'),
            selected: true,
            onTap: () => Navigator.pop(context),
          ),
          ListTile(
            leading: const Icon(Icons.history),
            title: Text(loc.chronicle),
            onTap: () => Navigator.pop(context),
          ),
          ListTile(
            leading: const Icon(Icons.public),
            title: Text(loc.world),
            onTap: () => Navigator.pop(context),
          ),
          const Divider(),
          ListTile(
            leading: const Icon(Icons.settings),
            title: Text(loc.settings),
            onTap: () {
              Navigator.pop(context);
              Navigator.pushNamed(context, '/settings');
            },
          ),
        ],
      ),
    );
  }

  Widget _buildDisconnectedState() {
    final loc = AppLocalizations.of(context);
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.cloud_off, size: 64, color: Colors.white30),
          const SizedBox(height: 16),
          Text(loc!.disconnected),
          const SizedBox(height: 8),
          const Text(
            'Start the Genesis backend with:\n./genesis.sh start --api',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.white60, fontSize: 12),
          ),
          const SizedBox(height: 24),
          ElevatedButton.icon(
            onPressed: _connectToBackend,
            icon: const Icon(Icons.refresh),
            label: Text('Retry Connection'),
          ),
        ],
      ),
    );
  }

  Widget _buildMainContent(AppState state) {
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
            AppLocalizations.of(context)!.eventLog,
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          ...state.events.take(20).map((e) => EventLogCard(event: e)),
        ],
      ),
    );
  }

  Widget _buildFab() {
    final loc = AppLocalizations.of(context);
    return FloatingActionButton.extended(
      onPressed: () => _showTaskInputDialog(),
      icon: const Icon(Icons.assignment),
      label: Text(loc!.assignTask),
    );
  }

  Widget _buildBottomBar() {
    final loc = AppLocalizations.of(context);
    return BottomAppBar(
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
        children: [
          IconButton(
            icon: const Icon(Icons.play_arrow),
            tooltip: loc!.start,
            onPressed: () {
              // TODO: Start command
            },
          ),
          IconButton(
            icon: const Icon(Icons.stop),
            tooltip: loc.stop,
            onPressed: () {
              context.read<WebSocketService>().sendStop();
              context.read<AppState>().setRunning(false);
            },
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: loc.status,
            onPressed: () {
              context.read<WebSocketService>().requestStatus();
            },
          ),
        ],
      ),
    );
  }

  void _showTaskInputDialog() {
    final loc = AppLocalizations.of(context);
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(loc!.assignTask),
        content: TextField(
          controller: _taskController,
          decoration: InputDecoration(
            hintText: loc.taskHint,
            border: OutlineInputBorder(),
          ),
          maxLines: 3,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () {
              final task = _taskController.text.trim();
              if (task.isNotEmpty) {
                context.read<WebSocketService>().sendTask(task);
                _taskController.clear();
                Navigator.pop(context);
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text('Task assigned!')),
                );
              }
            },
            child: Text('Send'),
          ),
        ],
      ),
    );
  }
}