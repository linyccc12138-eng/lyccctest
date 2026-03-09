#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PC端播放器测试脚本
测试目标: https://magic.lyccc.xyz/play/25
测试内容:
1. 用户登录
2. 访问播放页面
3. 检查播放器比例是否正确 (应为16:9)
4. 检查console和network是否有报错
"""

import asyncio
from datetime import datetime
from playwright.async_api import async_playwright

# 测试配置
BASE_URL = "https://magic.lyccc.xyz"
LOGIN_URL = f"{BASE_URL}/login"
PLAY_URL = f"{BASE_URL}/play/25"
TEST_USER = {
    "phone": "13256833186",
    "password": "123456"
}

# 存储所有console消息和network错误
console_messages = []
network_errors = []


async def run_test():
    """运行PC端播放器测试"""
    print("=" * 60)
    print(f"PC端播放器测试开始 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    async with async_playwright() as p:
        # 启动浏览器 (PC端 viewport)
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        page = await context.new_page()
        
        # 监听console消息
        page.on("console", lambda msg: console_messages.append({
            "type": msg.type,
            "text": msg.text,
            "time": datetime.now().strftime('%H:%M:%S')
        }))
        
        # 监听网络请求错误
        page.on("requestfailed", lambda request: network_errors.append({
            "url": request.url,
            "error": request.failure['errorText'] if request.failure else 'Unknown',
            "time": datetime.now().strftime('%H:%M:%S')
        }))
        
        # 监听response，检查状态码
        failed_responses = []
        async def handle_response(response):
            if response.status >= 400:
                failed_responses.append({
                    "url": response.url,
                    "status": response.status,
                    "time": datetime.now().strftime('%H:%M:%S')
                })
        page.on("response", handle_response)
        
        try:
            # 1. 访问登录页面
            print("\n[Step 1] 访问登录页面...")
            await page.goto(LOGIN_URL, wait_until="networkidle")
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(1)
            
            # 2. 输入登录信息
            print("[Step 2] 输入登录信息...")
            await page.fill("input[name='phone']", TEST_USER["phone"])
            await page.fill("input[name='password']", TEST_USER["password"])
            
            # 3. 点击登录按钮
            print("[Step 3] 点击登录按钮...")
            await page.click("button[type='submit']")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            
            # 检查是否登录成功
            current_url = page.url
            if "/dashboard" in current_url or "/login" not in current_url:
                print("  ✓ 登录成功")
            else:
                print(f"  ✗ 登录失败，当前URL: {current_url}")
                return False
            
            # 4. 访问播放页面
            print(f"[Step 4] 访问播放页面: {PLAY_URL}...")
            await page.goto(PLAY_URL, wait_until="networkidle")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(5)  # 等待播放器加载
            
            # 5. 检查播放器尺寸
            print("[Step 5] 检查播放器尺寸...")
            player_info = await page.evaluate("""
                () => {
                    const wrapper = document.getElementById('player-wrapper');
                    const videoEl = document.getElementById('player-container');
                    const videoHtml5El = document.getElementById('player-container_html5_api');
                    
                    if (!wrapper) return { error: '找不到player-wrapper元素' };
                    
                    const wrapperRect = wrapper.getBoundingClientRect();
                    
                    // 获取实际视频元素
                    let videoRect = null;
                    let videoTag = null;
                    
                    if (videoHtml5El) {
                        videoRect = videoHtml5El.getBoundingClientRect();
                        videoTag = {
                            videoWidth: videoHtml5El.videoWidth,
                            videoHeight: videoHtml5El.videoHeight,
                            clientWidth: videoHtml5El.clientWidth,
                            clientHeight: videoHtml5El.clientHeight,
                            offsetWidth: videoHtml5El.offsetWidth,
                            offsetHeight: videoHtml5El.offsetHeight
                        };
                    } else if (videoEl) {
                        videoRect = videoEl.getBoundingClientRect();
                    }
                    
                    return {
                        wrapper: {
                            width: wrapperRect.width,
                            height: wrapperRect.height,
                            aspectRatio: wrapperRect.width / wrapperRect.height
                        },
                        videoElement: videoRect ? {
                            width: videoRect.width,
                            height: videoRect.height,
                            aspectRatio: videoRect.width / videoRect.height
                        } : null,
                        videoTag: videoTag,
                        // TCPlayer内部信息
                        tcPlayerInfo: (() => {
                            const tcpPlayer = document.querySelector('.tcp-player');
                            if (tcpPlayer) {
                                const rect = tcpPlayer.getBoundingClientRect();
                                return {
                                    width: rect.width,
                                    height: rect.height,
                                    aspectRatio: rect.width / rect.height
                                };
                            }
                            return null;
                        })()
                    };
                }
            """)
            
            print(f"  播放器容器(wrapper):")
            if 'error' in player_info:
                print(f"    错误: {player_info['error']}")
            else:
                wrapper = player_info.get('wrapper', {})
                print(f"    尺寸: {wrapper.get('width', 0):.0f} x {wrapper.get('height', 0):.0f}")
                print(f"    宽高比: {wrapper.get('aspectRatio', 0):.4f} (目标: 1.7778 = 16:9)")
                
                expected_ratio = 16 / 9
                actual_ratio = wrapper.get('aspectRatio', 0)
                ratio_diff = abs(actual_ratio - expected_ratio)
                
                if ratio_diff < 0.05:
                    print(f"    ✓ 比例正确 (误差: {ratio_diff:.4f})")
                else:
                    print(f"    ✗ 比例不正确! 误差: {ratio_diff:.4f}")
                    print(f"      期望: {expected_ratio:.4f}, 实际: {actual_ratio:.4f}")
                
                if player_info.get('videoElement'):
                    video = player_info['videoElement']
                    print(f"\n  视频元素(video):")
                    print(f"    尺寸: {video.get('width', 0):.0f} x {video.get('height', 0):.0f}")
                    print(f"    宽高比: {video.get('aspectRatio', 0):.4f}")
                
                if player_info.get('tcPlayerInfo'):
                    tcp = player_info['tcPlayerInfo']
                    print(f"\n  TCPlayer容器:")
                    print(f"    尺寸: {tcp.get('width', 0):.0f} x {tcp.get('height', 0):.0f}")
                    print(f"    宽高比: {tcp.get('aspectRatio', 0):.4f}")
                
                if player_info.get('videoTag'):
                    vt = player_info['videoTag']
                    print(f"\n  Video标签属性:")
                    print(f"    videoWidth/videoHeight: {vt.get('videoWidth')} x {vt.get('videoHeight')}")
                    print(f"    clientWidth/clientHeight: {vt.get('clientWidth')} x {vt.get('clientHeight')}")
                    print(f"    offsetWidth/offsetHeight: {vt.get('offsetWidth')} x {vt.get('offsetHeight')}")
                    
                    # 检查视频原始分辨率比例
                    if vt.get('videoWidth') and vt.get('videoHeight'):
                        video_ratio = vt['videoWidth'] / vt['videoHeight']
                        print(f"    视频原始比例: {video_ratio:.4f}")
            
            # 6. 检查Console错误
            print("\n[Step 6] 检查Console消息...")
            errors = [m for m in console_messages if m['type'] in ['error', 'warning']]
            if errors:
                print(f"  发现 {len(errors)} 条错误/警告:")
                for err in errors:
                    print(f"    [{err['type'].upper()}] {err['text'][:150]}")
            else:
                print("  ✓ 没有发现console错误")
            
            # 7. 检查Network错误
            print("\n[Step 7] 检查Network错误...")
            if network_errors:
                print(f"  发现 {len(network_errors)} 个网络请求失败:")
                for err in network_errors[:10]:  # 只显示前10个
                    print(f"    [{err['status']}] {err['url'][:100]}...")
            else:
                print("  ✓ 没有发现网络请求失败")
            
            if failed_responses:
                print(f"\n  发现 {len(failed_responses)} 个HTTP错误响应:")
                for resp in failed_responses[:10]:
                    print(f"    [{resp['status']}] {resp['url'][:100]}...")
            else:
                print("  ✓ 没有发现HTTP错误响应")
            
            # 8. 截图保存
            screenshot_path = f"/www/course-platform/tests/pc_player_screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"\n[Step 8] 截图已保存: {screenshot_path}")
            
            # 总结
            print("\n" + "=" * 60)
            print("测试完成")
            print("=" * 60)
            
            has_errors = bool(errors) or bool(network_errors) or bool(failed_responses)
            if has_errors:
                print("⚠ 发现问题，请检查上述输出")
            else:
                print("✓ 所有检查通过")
            
            return not has_errors
            
        except Exception as e:
            print(f"\n✗ 测试执行出错: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            await browser.close()


if __name__ == "__main__":
    result = asyncio.run(run_test())
    exit(0 if result else 1)
