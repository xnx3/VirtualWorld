import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/app_state.dart';
import '../services/websocket_service.dart';
import '../widgets/widgets.dart';

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
      title: const Row(
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
            return Container(
              margin: const EdgeInsets.only(right: 8),
              child: Chip(
                label: Text(state.isRunning ? 'Running' : 'Stopped'),
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
    return Drawer(
      child: ListView(
        children: [
          const DrawerHeader(
            decoration: BoxDecoration(color: Colors.deepPurple),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                Text('Genesis', style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
                SizedBox(height: 8),
                Text('Silicon Civilization Simulator', style: TextStyle(color: Colors.white70)),
              ],
            ),
          ),
          ListTile(
            leading: const Icon(Icons.home),
            title: const Text('Dashboard'),
            selected: true,
            onTap: () => Navigator.pop(context),
          ),
          ListTile(
            leading: const Icon(Icons.history),
            title: const Text('Chronicle'),
            onTap: () => Navigator.pop(context),
          ),
          ListTile(
            leading: const Icon(Icons.public),
            title: const Text('World'),
            onTap: () => Navigator.pop(context),
          ),
          const Divider(),
          ListTile(
            leading: const Icon(Icons.settings),
            title: const Text('Settings'),
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
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.cloud_off, size: 64, color: Colors.white30),
          const SizedBox(height: 16),
          const Text('Not connected to backend'),
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
            label: const Text('Retry Connection'),
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
          const Text(
            'Event Log',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          ...state.events.take(20).map((e) => EventLogCard(event: e)),
        ],
      ),
    );
  }

  Widget _buildFab() {
    return FloatingActionButton.extended(
      onPressed: () => _showTaskInputDialog(),
      icon: const Icon(Icons.assignment),
      label: const Text('Assign Task'),
    );
  }

  Widget _buildBottomBar() {
    return BottomAppBar(
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
        children: [
          IconButton(
            icon: const Icon(Icons.play_arrow),
            tooltip: 'Start',
            onPressed: () {
              // TODO: Start command
            },
          ),
          IconButton(
            icon: const Icon(Icons.stop),
            tooltip: 'Stop',
            onPressed: () {
              context.read<WebSocketService>().sendStop();
              context.read<AppState>().setRunning(false);
            },
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Status',
            onPressed: () {
              context.read<WebSocketService>().requestStatus();
            },
          ),
        ],
      ),
    );
  }

  void _showTaskInputDialog() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Assign Task'),
        content: TextField(
          controller: _taskController,
          decoration: const InputDecoration(
            hintText: 'Enter task description...',
            border: OutlineInputBorder(),
          ),
          maxLines: 3,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () {
              final task = _taskController.text.trim();
              if (task.isNotEmpty) {
                context.read<WebSocketService>().sendTask(task);
                _taskController.clear();
                Navigator.pop(context);
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Task assigned!')),
                );
              }
            },
            child: const Text('Send'),
          ),
        ],
      ),
    );
  }
}