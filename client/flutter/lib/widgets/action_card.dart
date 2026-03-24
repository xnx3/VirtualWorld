import 'package:flutter/material.dart';
import '../core/theme/app_theme.dart';
import '../core/constants/app_icons.dart';

/// 行动卡片组件
class ActionCard extends StatelessWidget {
  final String actionType;
  final String? target;
  final String details;

  const ActionCard({
    super.key,
    required this.actionType,
    this.target,
    required this.details,
  });

  Color get actionColor {
    switch (actionType) {
      case 'speak':
        return Colors.green;
      case 'teach':
        return Colors.lightGreen;
      case 'learn':
        return Colors.cyan;
      case 'create':
        return Colors.purple;
      case 'explore':
        return Colors.blue;
      case 'compete':
        return Colors.red;
      case 'meditate':
        return Colors.deepPurple;
      case 'move':
        return Colors.teal;
      case 'build_shelter':
        return Colors.orange;
      case 'deep_think':
        return Colors.purpleAccent;
      default:
        return Colors.white;
    }
  }

  @override
  Widget build(BuildContext context) {
    final icon = AppIcons.getActionIcon(actionType);
    final actionName = _formatActionName(actionType);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(icon, style: const TextStyle(fontSize: 18)),
                const SizedBox(width: 8),
                Text(
                  actionName,
                  style: Theme.of(context).textTheme.titleSmall?.copyWith(
                        color: actionColor,
                        fontWeight: FontWeight.bold,
                      ),
                ),
              ],
            ),
            if (target != null && target!.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(
                'Target: $target',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: Colors.white60,
                    ),
              ),
            ],
            if (details.isNotEmpty) ...[
              const SizedBox(height: 8),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: actionColor.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  details,
                  style: TextStyle(color: actionColor.withOpacity(0.9)),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  String _formatActionName(String action) {
    // 转换下划线为空格，首字母大写
    return action
        .split('_')
        .map((word) => word.isEmpty ? '' : '${word[0].toUpperCase()}${word.substring(1)}')
        .join(' ');
  }
}