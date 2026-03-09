#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证Mobile端修复结果的脚本
"""

import re
from datetime import datetime

def check_file_fixes():
    """检查修复是否已应用"""
    print("=" * 60)
    print(f"修复验证 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    fixes_applied = []
    issues_found = []
    
    # 检查1: mobile/play-mobile.html 中的元素ID修复
    print("\n[检查1] Mobile端元素ID修复...")
    try:
        with open('/www/course-platform/app/templates/mobile/play-mobile.html', 'r') as f:
            content = f.read()
        
        # 检查是否还有旧的错误ID
        wrong_id_count = content.count("getElementById('player-wrapper')")
        correct_id_count = content.count("getElementById('playerWrapper')")
        
        if wrong_id_count == 0 and correct_id_count >= 3:
            print(f"  ✓ 元素ID已修复 (正确ID使用次数: {correct_id_count})")
            fixes_applied.append("mobile/play-mobile.html: 元素ID修复")
        else:
            print(f"  ✗ 元素ID修复不完整")
            print(f"    错误ID使用次数: {wrong_id_count}")
            print(f"    正确ID使用次数: {correct_id_count}")
            issues_found.append("mobile/play-mobile.html: 元素ID仍需修复")
    except Exception as e:
        print(f"  ✗ 检查失败: {e}")
        issues_found.append(f"检查mobile/play-mobile.html失败: {e}")
    
    # 检查2: mobile/play-mobile.html 中的TCPlayer优化
    print("\n[检查2] TCPlayer加载优化...")
    try:
        with open('/www/course-platform/app/templates/mobile/play-mobile.html', 'r') as f:
            content = f.read()
        
        # 检查是否增加了尝试次数
        if 'maxAttempts = maxAttempts || 100' in content:
            print("  ✓ TCPlayer等待时间已优化 (100次尝试)")
            fixes_applied.append("mobile/play-mobile.html: TCPlayer优化")
        else:
            print("  ✗ TCPlayer等待时间未优化")
            issues_found.append("TCPlayer优化未完成")
        
        # 检查是否有预加载检测
        if 'TCPlayer 已加载' in content:
            print("  ✓ 已添加TCPlayer预加载检测")
        else:
            print("  ✗ 缺少TCPlayer预加载检测")
    except Exception as e:
        print(f"  ✗ 检查失败: {e}")
    
    # 检查3: base.html favicon
    print("\n[检查3] Favicon添加...")
    try:
        with open('/www/course-platform/app/templates/base.html', 'r') as f:
            content = f.read()
        
        if 'data:image/svg+xml' in content and '🎓' in content:
            print("  ✓ base.html已添加favicon")
            fixes_applied.append("base.html: favicon添加")
        else:
            print("  ✗ base.html未添加favicon")
            issues_found.append("base.html缺少favicon")
    except Exception as e:
        print(f"  ✗ 检查失败: {e}")
    
    # 检查4: mobile/play-mobile.html favicon
    print("\n[检查4] Mobile play页面favicon...")
    try:
        with open('/www/course-platform/app/templates/mobile/play-mobile.html', 'r') as f:
            content = f.read()
        
        if 'data:image/svg+xml' in content and '🎓' in content:
            print("  ✓ mobile/play-mobile.html已添加favicon")
            fixes_applied.append("mobile/play-mobile.html: favicon添加")
        else:
            print("  ✗ mobile/play-mobile.html未添加favicon")
            issues_found.append("mobile/play-mobile.html缺少favicon")
    except Exception as e:
        print(f"  ✗ 检查失败: {e}")
    
    # 总结
    print("\n" + "=" * 60)
    print("验证结果总结")
    print("=" * 60)
    
    if fixes_applied:
        print(f"\n✓ 已应用的修复 ({len(fixes_applied)}项):")
        for fix in fixes_applied:
            print(f"  - {fix}")
    
    if issues_found:
        print(f"\n✗ 发现的问题 ({len(issues_found)}项):")
        for issue in issues_found:
            print(f"  - {issue}")
    
    if not issues_found:
        print("\n✓ 所有修复已成功应用!")
        return True
    else:
        print(f"\n⚠ 还有 {len(issues_found)} 个问题需要处理")
        return False


def show_pc_player_advice():
    """显示PC端播放器比例调整建议"""
    print("\n" + "=" * 60)
    print("PC端播放器比例说明")
    print("=" * 60)
    print("""
当前PC端播放器比例是动态计算的，考虑了窗口高度限制(75%)。
视频原始比例是16:9 (1920x1080)，但显示比例会自适应容器。

如果需要严格16:9比例，可以修改:
/www/course-platform/app/templates/user/play.html

在第156行附近修改 maxHeightPercent:
  // 原代码:
  var maxHeightPercent = isMobile ? 0.5 : 0.75;
  
  // 改为:
  var maxHeightPercent = isMobile ? 0.5 : 0.9;  // 允许更高比例

或者完全按照视频原始比例（移除高度限制）:
  // 注释掉或删除第164-167行的限制代码:
  // if (targetHeight > maxHeight) {
  //     targetHeight = maxHeight;
  //     targetWidth = targetHeight * aspectRatio;
  // }
""")


if __name__ == "__main__":
    result = check_file_fixes()
    show_pc_player_advice()
    
    exit(0 if result else 1)
