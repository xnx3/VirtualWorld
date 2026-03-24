import 'package:flutter/material.dart';
import '../core/theme/app_theme.dart';

/// 思考气泡组件
class ThinkBubble extends StatelessWidget {
  final String beingName;
  final String thought;

  const ThinkBubble({
    super.key,
    required this.beingName,
    required this.thought,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Colors.deepPurple.shade900.withOpacity(0.3),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Text('💭 ', style: TextStyle(fontSize: 18)),
                Text(
                  'Think',
                  style: Theme.of(context).textTheme.titleSmall?.copyWith(
                        color: AppTheme.thinkColor,
                        fontWeight: FontWeight.bold,
                      ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.black26,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                  color: AppTheme.thinkColor.withOpacity(0.3),
                ),
              ),
              child: SelectableText(
                thought,
                style: const TextStyle(
                  fontStyle: FontStyle.italic,
                  color: Colors.white70,
                  height: 1.5,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}