#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mobile端播放器测试脚本
测试目标: https://magic.lyccc.xyz/mobile/play/25
测试内容:
1. 移动端用户登录
2. 访问移动端播放页面
3. 检查播放器是否正常加载 (是否有TCPlayer加载超时错误)
4. 检查console和network是否有报错
"""

import asyncio
from datetime import datetime
from playwright.async_api import async_playwright

# 测试配置
BASE_URL = "https://magic.lyccc.xyz"
MOBILE_LOGIN_URL = f"{BASE_URL}/mobile/login"
MOBILE_PLAY_URL = f"{BASE_URL}/mobile/play/25"
TEST_USER = {
    "phone": "13256833186",
    "password": "123456"
}

# 存储所有console消息和network错误
console_messages = []
network_errors = []


async def run_test():
    """运行Mobile端播放器测试"""
    print("=" * 60)
    print(f"Mobile端播放器测试开始 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    async with async_playwright() as p:
        # 启动浏览器 (Mobile端 viewport - iPhone 12 Pro)
        browser = await p.chromium.launch(headless=True)
        
        # iPhone 12 Pro 尺寸
        mobile_viewport = {"width": 390, "height": 844}
        
        context = await browser.new_context(
            viewport=mobile_viewport,
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
        )
        
        page = await context.new_page()
        
        # 监听console消息
        page.on("console", lambda msg: console_messages.append({
            "type": msg.type,
            "text": msg.text,
            "time": datetime.now().strftime('%H:%M:%S')
        }))
        
        # 监听网络请求错误
        def handle_request_failed(request):
            error_text = 'Unknown'
            if request.failure:
                if isinstance(request.failure, dict):
                    error_text = request.failure.get('errorText', 'Unknown')
                else:
                    error_text = str(request.failure)
            network_errors.append({
                "url": request.url,
                "error": error_text,
                "time": datetime.now().strftime('%H:%M:%S')
            })
        page.on("requestfailed", handle_request_failed)
        
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
            # 1. 访问移动端登录页面
            print("\n[Step 1] 访问移动端登录页面...")
            await page.goto(MOBILE_LOGIN_URL, wait_until="networkidle")
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(1)
            
            # 2. 输入登录信息
            print("[Step 2] 输入登录信息...")
            # 尝试不同的选择器
            try:
                await page.fill("input[name='phone']", TEST_USER["phone"])
                await page.fill("input[name='password']", TEST_USER["password"])
            except:
                # 如果name选择器失败，尝试其他选择器
                inputs = await page.query_selector_all("input")
                if len(inputs) >= 2:
                    await inputs[0].fill(TEST_USER["phone"])
                    await inputs[1].fill(TEST_USER["password"])
            
            # 3. 点击登录按钮
            print("[Step 3] 点击登录按钮...")
            try:
                await page.click("button[type='submit']")
            except:
                # 尝试其他选择器
                buttons = await page.query_selector_all("button")
                for btn in buttons:
                    text = await btn.inner_text()
                    if "登录" in text or "登入" in text:
                        await btn.click()
                        break
            
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            
            # 检查是否登录成功
            current_url = page.url
            print(f"  登录后URL: {current_url}")
            if "/dashboard" in current_url or "/mobile/dashboard" in current_url:
                print("  ✓ 登录成功")
            else:
                print(f"  登录后页面: {current_url}")
                # 检查是否有错误提示
                page_content = await page.content()
                if "错误" in page_content or "失败" in page_content:
                    print("  ✗ 可能登录失败，请检查")
                else:
                    print("  ✓ 登录可能成功")
            
            # 4. 访问移动端播放页面
            print(f"[Step 4] 访问移动端播放页面: {MOBILE_PLAY_URL}...")
            await page.goto(MOBILE_PLAY_URL, wait_until="networkidle")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(8)  # 等待播放器加载，TCPlayer可能需要较长时间
            
            # 5. 检查页面元素和播放器状态
            print("\n[Step 5] 检查播放器状态...")
            player_status = await page.evaluate("""
                () => {
                    // 检查关键元素
                    const wrapper = document.getElementById('playerWrapper');
                    const videoEl = document.getElementById('player-container-id');
                    const loadingOverlay = document.getElementById('loadingOverlay');
                    const errorOverlay = document.getElementById('errorOverlay');
                    
                    // 检查TCPlayer是否加载
                    const tcPlayerLoaded = typeof TCPlayer !== 'undefined';
                    
                    // 检查video标签是否存在
                    const videoTag = document.querySelector('video');
                    
                    return {
                        elements: {
                            playerWrapper: wrapper ? {
                                exists: true,
                                id: wrapper.id,
                                width: wrapper.style.width,
                                height: wrapper.style.height,
                                clientWidth: wrapper.clientWidth,
                                clientHeight: wrapper.clientHeight
                            } : { exists: false },
                            videoElement: videoEl ? {
                                exists: true,
                                tagName: videoEl.tagName,
                                width: videoEl.style.width,
                                height: videoEl.style.height
                            } : { exists: false },
                            videoTag: videoTag ? {
                                exists: true,
                                videoWidth: videoTag.videoWidth,
                                videoHeight: videoTag.videoHeight,
                                clientWidth: videoTag.clientWidth,
                                clientHeight: videoTag.clientHeight
                            } : { exists: false }
                        },
                        tcPlayer: {
                            loaded: tcPlayerLoaded,
                            type: typeof TCPlayer
                        },
                        overlays: {
                            loading: loadingOverlay ? !loadingOverlay.classList.contains('hidden') : null,
                            error: errorOverlay ? errorOverlay.classList.contains('show') : null
                        },
                        // 检查控制台相关变量
                        videoConfig: (() => {
                            try {
                                if (typeof window.videoConfig !== 'undefined') {
                                    return window.videoConfig;
                                }
                                return null;
                            } catch(e) {
                                return null;
                            }
                        })()
                    };
                }
            """)
            
            print("  元素状态:")
            elements = player_status.get('elements', {})
            print(f"    playerWrapper: {'✓ 存在' if elements.get('playerWrapper', {}).get('exists') else '✗ 不存在'}")
            if elements.get('playerWrapper', {}).get('exists'):
                pw = elements['playerWrapper']
                print(f"      尺寸: {pw.get('clientWidth')} x {pw.get('clientHeight')}")
            
            print(f"    video元素: {'✓ 存在' if elements.get('videoElement', {}).get('exists') else '✗ 不存在'}")
            print(f"    TCPlayer: {'✓ 已加载' if player_status.get('tcPlayer', {}).get('loaded') else '✗ 未加载'}")
            
            overlays = player_status.get('overlays', {})
            if overlays.get('loading'):
                print(f"    加载状态: 正在加载...")
            if overlays.get('error'):
                print(f"    错误状态: ✗ 显示错误覆盖层")
            
            if player_status.get('videoConfig'):
                vc = player_status['videoConfig']
                print(f"\n  视频配置:")
                print(f"    chapterId: {vc.get('chapterId')}")
                print(f"    fileId: {vc.get('fileId')}")
                print(f"    videoWidth: {vc.get('videoWidth')}")
                print(f"    videoHeight: {vc.get('videoHeight')}")
            
            # 6. 检查特定的TCPlayer加载超时错误
            print("\n[Step 6] 检查TCPlayer加载超时错误...")
            tcplayer_errors = [m for m in console_messages 
                              if 'TCPlayer' in m['text'] or 'tcplayer' in m['text'].lower()]
            
            if tcplayer_errors:
                print(f"  发现 {len(tcplayer_errors)} 条TCPlayer相关消息:")
                for err in tcplayer_errors:
                    print(f"    [{err['type'].upper()}] {err['text'][:150]}")
            else:
                print("  ✓ 没有发现TCPlayer相关错误")
            
            # 7. 检查所有Console错误
            print("\n[Step 7] 检查所有Console消息...")
            errors = [m for m in console_messages if m['type'] in ['error', 'warning']]
            
            # 过滤掉已知的非关键警告
            critical_errors = []
            for e in errors:
                text = e['text']
                # 跳过某些非关键警告
                if 'cdn.tailwindcss.com' in text and 'should not be used in production' in text:
                    continue
                if '[VSC]' in text:
                    continue
                if 'favicon.ico' in text:
                    continue
                critical_errors.append(e)
            
            if critical_errors:
                print(f"  发现 {len(critical_errors)} 条关键错误/警告:")
                for err in critical_errors:
                    print(f"    [{err['type'].upper()}] {err['text'][:150]}")
            else:
                print("  ✓ 没有发现关键console错误")
            
            # 8. 检查Network错误
            print("\n[Step 8] 检查Network错误...")
            if network_errors:
                print(f"  发现 {len(network_errors)} 个网络请求失败:")
                for err in network_errors[:10]:
                    print(f"    [{err.get('error', 'Unknown')}] {err.get('url', '')[:100]}...")
            else:
                print("  ✓ 没有发现网络请求失败")
            
            if failed_responses:
                print(f"\n  发现 {len(failed_responses)} 个HTTP错误响应:")
                for resp in failed_responses[:10]:
                    print(f"    [{resp['status']}] {resp['url'][:100]}...")
            else:
                print("  ✓ 没有发现HTTP错误响应")
            
            # 9. 检查元素ID不匹配问题 (分析发现的问题)
            print("\n[Step 9] 检查代码中的元素ID问题...")
            id_check = await page.evaluate("""
                () => {
                    const wrapperByOldId = document.getElementById('player-wrapper');
                    const wrapperByNewId = document.getElementById('playerWrapper');
                    
                    return {
                        player_dash_wrapper: wrapperByOldId ? 'exists' : 'not found',
                        playerWrapper: wrapperByNewId ? 'exists' : 'not found',
                        html: document.getElementById('playerWrapper')?.outerHTML?.substring(0, 200) || 'N/A'
                    };
                }
            """)
            
            print(f"  'player-wrapper' (代码中使用的): {id_check.get('player_dash_wrapper')}")
            print(f"  'playerWrapper' (实际HTML中的): {id_check.get('playerWrapper')}")
            
            if id_check.get('player_dash_wrapper') == 'not found' and id_check.get('playerWrapper') == 'exists':
                print("  ⚠ 发现问题: JavaScript代码中使用的是 'player-wrapper'，但HTML中的ID是 'playerWrapper'")
                print("  ⚠ 这会导致播放器尺寸计算失败!")
            
            # 10. 截图保存
            screenshot_path = f"/www/course-platform/tests/mobile_player_screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"\n[Step 10] 截图已保存: {screenshot_path}")
            
            # 总结
            print("\n" + "=" * 60)
            print("测试完成")
            print("=" * 60)
            
            has_critical_errors = bool(critical_errors) or bool(network_errors) or bool(failed_responses)
            tcplayer_timeout = any('超时' in m['text'] or 'timeout' in m['text'].lower() 
                                   for m in tcplayer_errors if m['type'] == 'error')
            
            if has_critical_errors or tcplayer_timeout:
                print("⚠ 发现问题，请检查上述输出")
                if tcplayer_timeout:
                    print("  主要问题: TCPlayer加载超时")
            else:
                print("✓ 主要检查通过")
            
            return not (has_critical_errors or tcplayer_timeout)
            
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
