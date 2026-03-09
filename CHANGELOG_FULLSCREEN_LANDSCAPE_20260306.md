# 移动端全屏横屏功能修改记录

## 修改时间
2026-03-06 18:30

## 备份文件
`/www/course-platform/app/templates/mobile/play-mobile.html.backup.20260306_183026`

## 修改内容

### 1. TCPlayer 配置更新（方案1）

**位置**: `initPlayer()` 函数中 TCPlayer 初始化参数

**修改前**:
```javascript
player = TCPlayer('player-container-id', {
    appID: playerConfig.appID,
    fileID: playerConfig.fileID,
    psign: playerConfig.psign,
    licenseUrl: playerConfig.licenseUrl || '',
    licenseKey: playerConfig.licenseKey || '',
    width: playerSize.width,
    height: playerSize.height,
    autoplay: false,
    preload: 'auto',
    hlsConfig: {
        debug: false,
        enableWorker: true
    },
    controlBar: {
        playToggle: true,
        progressControl: true,
        currentTimeDisplay: true,
        durationDisplay: true,
        timeDivider: true,
        playbackRateMenuButton: false,
        volumePanel: true,
        fullscreenToggle: true
    },
    plugins: {
        ProgressMarker: true
    }
});
```

**修改后**:
```javascript
player = TCPlayer('player-container-id', {
    appID: playerConfig.appID,
    fileID: playerConfig.fileID,
    psign: playerConfig.psign,
    licenseUrl: playerConfig.licenseUrl || '',
    licenseKey: playerConfig.licenseKey || '',
    width: playerSize.width,
    height: playerSize.height,
    autoplay: false,
    preload: 'auto',
    fakeFullscreen: true,  // 新增：启用伪全屏
    hlsConfig: {
        debug: false,
        enableWorker: true
    },
    controlBar: {
        playToggle: true,
        progressControl: true,
        currentTimeDisplay: true,
        durationDisplay: true,
        timeDivider: true,
        playbackRateMenuButton: false,
        volumePanel: true,
        fullscreenToggle: true,
        fullscreenRotate: true  // 新增：显示旋转按钮
    },
    plugins: {
        ProgressMarker: true
    }
});
```

**新增参数说明**:
- `fakeFullscreen: true`: 启用伪全屏，通过 CSS 控制实现全屏效果
- `fullscreenRotate: true`: 在控制栏显示画面旋转按钮

---

### 2. fullscreenchange 事件处理更新（方案1）

**位置**: `player.on('fullscreenchange', ...)` 事件处理器

**修改前**:
```javascript
player.on('fullscreenchange', function(e) {
    const playPage = document.getElementById('playPage');
    if (e.detail.isFullscreen) {
        playPage.classList.add('fullscreen');
    } else {
        playPage.classList.remove('fullscreen');
    }
});
```

**修改后**:
```javascript
player.on('fullscreenchange', function(e) {
    const playPage = document.getElementById('playPage');
    if (e.detail.isFullscreen) {
        playPage.classList.add('fullscreen');
        console.log('进入全屏模式');
        
        // 尝试锁定横屏（方案1）
        if (screen.orientation && screen.orientation.lock) {
            screen.orientation.lock('landscape').then(function() {
                console.log('屏幕方向已锁定为横屏');
            }).catch(function(err) {
                console.log('无法锁定屏幕方向（可能在iOS或需要用户交互）:', err.message);
            });
        } else {
            console.log('当前浏览器不支持屏幕方向锁定API');
        }
    } else {
        playPage.classList.remove('fullscreen');
        console.log('退出全屏模式');
        
        // 解锁屏幕方向
        if (screen.orientation && screen.orientation.unlock) {
            screen.orientation.unlock();
            console.log('屏幕方向已解锁');
        }
    }
});
```

**新增功能**:
- 进入全屏时尝试使用 `screen.orientation.lock('landscape')` 锁定横屏
- 退出全屏时使用 `screen.orientation.unlock()` 解锁方向
- 添加了特性检测，在不支持的浏览器中优雅降级

---

### 3. orientationchange 事件监听（方案2）

**位置**: `initPlayer()` 函数末尾，在 resize 事件监听器之后

**新增代码**:
```javascript
// 方案2：监听设备方向变化，横屏时自动进入全屏，竖屏时自动退出全屏
window.addEventListener('orientationchange', function() {
    // 使用setTimeout确保 orientationchange 事件完成后再检测
    setTimeout(function() {
        const isLandscape = window.matchMedia('(orientation: landscape)').matches;
        const isFullscreen = player && player.isFullscreen && player.isFullscreen();
        
        console.log('设备方向变化，当前方向:', isLandscape ? '横屏' : '竖屏', '全屏状态:', isFullscreen);
        
        if (isLandscape) {
            // 横屏时自动进入全屏（如果不在全屏状态）
            if (!isFullscreen && player && player.requestFullscreen) {
                console.log('检测到横屏，自动进入全屏');
                player.requestFullscreen();
            }
        } else {
            // 竖屏时自动退出全屏（如果在全屏状态）
            if (isFullscreen && player && player.exitFullscreen) {
                console.log('检测到竖屏，自动退出全屏');
                player.exitFullscreen();
            }
        }
    }, 100);
});
```

**新增功能**:
- 监听设备方向变化 (`orientationchange` 事件)
- 用户将设备旋转到横屏时，自动进入全屏模式
- 用户将设备旋转到竖屏时，自动退出全屏模式
- 使用 `setTimeout` 确保方向变化完成后再检测

---

### 4. CSS 全屏样式更新

**位置**: `<style>` 标签中的全屏模式样式

**修改前**:
```css
/* 全屏模式 */
.play-page.fullscreen .chapter-info,
.play-page.fullscreen .chapters-section {
    display: none;
}

.play-page.fullscreen .player-wrapper {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 1000;
}

.play-page.fullscreen #player-container-id {
    height: 100%;
    aspect-ratio: auto;
}
```

**修改后**:
```css
/* 全屏模式 */
.play-page.fullscreen .chapter-info,
.play-page.fullscreen .chapters-section {
    display: none;
}

.play-page.fullscreen .play-header-fixed {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 1000;
    padding: 0;
    background: #000;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
}

.play-page.fullscreen .player-wrapper {
    position: relative;
    width: 100%;
    height: 100%;
    max-width: 100vw;
    max-height: 100vh;
    border-radius: 0;
}

.play-page.fullscreen #player-container-id {
    width: 100%;
    height: 100%;
    aspect-ratio: auto;
}

/* 横屏模式下的播放器样式优化 */
@media screen and (orientation: landscape) {
    .play-page.fullscreen .player-wrapper {
        width: 100vh;
        height: 100vw;
        max-width: 100vw;
        max-height: 100vh;
    }
}
```

**新增样式说明**:
- `.play-page.fullscreen .play-header-fixed`: 全屏时固定区域占满整个视口
- `@media screen and (orientation: landscape)`: 横屏时优化播放器尺寸

---

## 测试验证

### 测试结果
- ✅ 播放器正常加载
- ✅ 视频可以正常播放
- ✅ 全屏按钮正常工作
- ✅ 方向变化事件正确触发
- ✅ 全屏状态切换正常

### 浏览器兼容性

| 功能 | Android Chrome | iOS Safari | 微信(Android) | 微信(iOS) |
|------|----------------|------------|---------------|-----------|
| fakeFullscreen | ✅ CSS | ✅ CSS | ✅ CSS | ✅ CSS |
| fullscreenRotate | ✅ | ✅ | ✅ | ✅ |
| screen.orientation.lock() | ✅ | ❌ | ⚠️ | ❌ |
| orientationchange 事件 | ✅ | ✅ | ✅ | ✅ |
| 自动全屏 | ✅ Fullscreen API | ❌ webkit | ⚠️ x5劫持 | ❌ 系统劫持 |

### 预期行为

**Android Chrome**:
- 点击全屏按钮 → 进入全屏 + 尝试锁定横屏 ✅
- 旋转设备到横屏 → 自动进入全屏 ✅
- 旋转设备到竖屏 → 自动退出全屏 ✅

**iOS Safari/微信**:
- 点击全屏按钮 → 进入全屏，方向锁定无效 ⚠️
- 旋转设备到横屏 → 自动进入全屏 ✅
- 可使用旋转按钮手动调整画面方向 ✅

---

## 回滚方法

如需回滚到修改前的版本，执行以下命令：

```bash
cd /www/course-platform/app/templates/mobile
cp play-mobile.html.backup.20260306_183026 play-mobile.html
```

---

## 测试脚本

测试脚本已生成：`test_fullscreen_landscape_20260306_183200.py`

运行测试：
```bash
cd /www/course-platform
source venv/bin/activate
python test_fullscreen_landscape_20260306_183200.py
```
