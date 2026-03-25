import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../services/log_service.dart';
import '../l10n/app_localizations.dart';

/// 日志查看界面
class LogScreen extends StatefulWidget {
  const LogScreen({super.key});

  @override
  State<LogScreen> createState() => _LogScreenState();
}

class _LogScreenState extends State<LogScreen> {
  LogLevel? _selectedLevel;
  String? _selectedSource;
  String _searchQuery = '';
  final _searchController = TextEditingController();

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  List<LogEntry> _filterEntries(List<LogEntry> entries) {
    var filtered = entries;

    if (_selectedLevel != null) {
      filtered = filtered.where((e) => e.level == _selectedLevel).toList();
    }

    if (_selectedSource != null) {
      filtered = filtered.where((e) => e.source == _selectedSource).toList();
    }

    if (_searchQuery.isNotEmpty) {
      final query = _searchQuery.toLowerCase();
      filtered = filtered.where((e) => e.message.toLowerCase().contains(query)).toList();
    }

    return filtered;
  }

  Color _getLevelColor(LogLevel level) {
    switch (level) {
      case LogLevel.debug:
        return Colors.grey;
      case LogLevel.info:
        return Colors.blue;
      case LogLevel.warning:
        return Colors.orange;
      case LogLevel.error:
        return Colors.red;
    }
  }

  IconData _getLevelIcon(LogLevel level) {
    switch (level) {
      case LogLevel.debug:
        return Icons.bug_report;
      case LogLevel.info:
        return Icons.info_outline;
      case LogLevel.warning:
        return Icons.warning_amber;
      case LogLevel.error:
        return Icons.error_outline;
    }
  }

  Future<void> _copyLog(LogService logService) async {
    final text = logService.export();
    await Clipboard.setData(ClipboardData(text: text));
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('日志已复制到剪贴板'),
          backgroundColor: Colors.green,
        ),
      );
    }
  }

  Future<void> _copyEntry(LogEntry entry) async {
    await Clipboard.setData(ClipboardData(text: entry.toString()));
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('已复制'),
          duration: Duration(seconds: 1),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context);

    return Scaffold(
      appBar: AppBar(
        title: Text(loc?.logs ?? 'Logs'),
        actions: [
          // 清空按钮
          IconButton(
            icon: const Icon(Icons.delete_outline),
            tooltip: '清空日志',
            onPressed: () {
              _showClearConfirmDialog(context);
            },
          ),
          // 复制全部按钮
          IconButton(
            icon: const Icon(Icons.copy),
            tooltip: '复制全部',
            onPressed: () {
              final logService = context.read<LogService>();
              _copyLog(logService);
            },
          ),
        ],
      ),
      body: Column(
        children: [
          // 筛选栏
          _buildFilterBar(),

          // 日志列表
          Expanded(
            child: Consumer<LogService>(
              builder: (context, logService, _) {
                final entries = _filterEntries(logService.allEntries);

                if (entries.isEmpty) {
                  return Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(Icons.article_outlined, size: 64, color: Colors.grey[600]),
                        const SizedBox(height: 16),
                        Text(
                          '暂无日志',
                          style: TextStyle(color: Colors.grey[600]),
                        ),
                      ],
                    ),
                  );
                }

                return ListView.builder(
                  padding: const EdgeInsets.all(8),
                  itemCount: entries.length,
                  itemBuilder: (context, index) {
                    final entry = entries[index];
                    return _buildLogEntry(entry);
                  },
                );
              },
            ),
          ),

          // 底部统计
          _buildStatsBar(),
        ],
      ),
    );
  }

  Widget _buildFilterBar() {
    return Container(
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: Colors.grey[900],
        border: Border(bottom: BorderSide(color: Colors.grey[800]!)),
      ),
      child: Column(
        children: [
          // 搜索框
          TextField(
            controller: _searchController,
            decoration: InputDecoration(
              hintText: '搜索日志...',
              prefixIcon: const Icon(Icons.search, size: 20),
              suffixIcon: _searchQuery.isNotEmpty
                  ? IconButton(
                      icon: const Icon(Icons.clear, size: 20),
                      onPressed: () {
                        _searchController.clear();
                        setState(() => _searchQuery = '');
                      },
                    )
                  : null,
              border: const OutlineInputBorder(),
              contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              isDense: true,
            ),
            onChanged: (value) {
              setState(() => _searchQuery = value);
            },
          ),
          const SizedBox(height: 8),

          // 筛选按钮
          Row(
            children: [
              // 级别筛选
              Expanded(
                child: DropdownButtonFormField<LogLevel?>(
                  value: _selectedLevel,
                  decoration: const InputDecoration(
                    labelText: '级别',
                    border: OutlineInputBorder(),
                    contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    isDense: true,
                  ),
                  items: const [
                    DropdownMenuItem(value: null, child: Text('全部')),
                    DropdownMenuItem(value: LogLevel.debug, child: Text('DEBUG')),
                    DropdownMenuItem(value: LogLevel.info, child: Text('INFO')),
                    DropdownMenuItem(value: LogLevel.warning, child: Text('WARN')),
                    DropdownMenuItem(value: LogLevel.error, child: Text('ERROR')),
                  ],
                  onChanged: (value) {
                    setState(() => _selectedLevel = value);
                  },
                ),
              ),
              const SizedBox(width: 8),

              // 来源筛选
              Expanded(
                child: DropdownButtonFormField<String?>(
                  value: _selectedSource,
                  decoration: const InputDecoration(
                    labelText: '来源',
                    border: OutlineInputBorder(),
                    contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    isDense: true,
                  ),
                  items: const [
                    DropdownMenuItem(value: null, child: Text('全部')),
                    DropdownMenuItem(value: 'flutter', child: Text('Flutter')),
                    DropdownMenuItem(value: 'backend', child: Text('后端')),
                  ],
                  onChanged: (value) {
                    setState(() => _selectedSource = value);
                  },
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildLogEntry(LogEntry entry) {
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 2),
      child: ListTile(
        dense: true,
        leading: Icon(
          _getLevelIcon(entry.level),
          color: _getLevelColor(entry.level),
          size: 20,
        ),
        title: Text(
          entry.message,
          style: const TextStyle(fontSize: 13),
          maxLines: 3,
          overflow: TextOverflow.ellipsis,
        ),
        subtitle: Text(
          '${entry.formattedTimestamp} [${entry.source}]',
          style: TextStyle(fontSize: 11, color: Colors.grey[500]),
        ),
        trailing: IconButton(
          icon: const Icon(Icons.copy, size: 18),
          onPressed: () => _copyEntry(entry),
          tooltip: '复制',
        ),
        onLongPress: () => _copyEntry(entry),
      ),
    );
  }

  Widget _buildStatsBar() {
    return Consumer<LogService>(
      builder: (context, logService, _) {
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          decoration: BoxDecoration(
            color: Colors.grey[900],
            border: Border(top: BorderSide(color: Colors.grey[800]!)),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                '共 ${logService.entryCount} 条日志',
                style: TextStyle(fontSize: 12, color: Colors.grey[500]),
              ),
              Row(
                children: [
                  _buildStatChip('ERROR', logService.filterByLevel(LogLevel.error).length, Colors.red),
                  const SizedBox(width: 8),
                  _buildStatChip('WARN', logService.filterByLevel(LogLevel.warning).length, Colors.orange),
                  const SizedBox(width: 8),
                  _buildStatChip('INFO', logService.filterByLevel(LogLevel.info).length, Colors.blue),
                ],
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildStatChip(String label, int count, Color color) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 8,
          height: 8,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 4),
        Text(
          '$label: $count',
          style: TextStyle(fontSize: 11, color: Colors.grey[500]),
        ),
      ],
    );
  }

  Future<void> _showClearConfirmDialog(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('清空日志'),
        content: const Text('确定要清空所有日志吗？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            child: const Text('清空'),
          ),
        ],
      ),
    );

    if (confirmed == true && mounted) {
      context.read<LogService>().clear();
    }
  }
}
