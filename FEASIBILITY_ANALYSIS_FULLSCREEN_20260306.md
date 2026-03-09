# 两个方案同时加入的可行性分析

## 方案概述

### 方案1：启用伪全屏 + 屏幕方向锁定
- 配置 `fakeFullscreen: true`
- 配置 `fullscreenRotate: true`
- 在 `fullscreenchange` 事件中调用 `screen.orientation.lock('landscape')`

### 方案2：监听设备方向自动全屏
- 监听 `orientationchange` 事件
- 横屏时自动调用 `player.requestFullscreen()`
- 竖屏时自动调用 `player.exitFullscreen()`

---

## 可行性分析

### ✅ 可以同时加入，互不影响

两个方案针对的是不同的用户行为和场景：

| 场景 | 方案1 | 方案2 |
|------|-------|-------|
| 用户点击全屏按钮 | ✅ 触发 | ❌ 不触发 |
| 用户旋转设备到横屏 | ❌ 不触发 | ✅ 触发 |
| 用户旋转设备到竖屏 | ❌ 不触发 | ✅ 触发 |

### 🔍 代码层面的兼容性

#### 1. TCPlayer 配置兼容性
```javascript
player = TCPlayer('player-container-id', {
    // 方案1配置
    fakeFullscreen: true,
    controlBar: {
        fullscreenToggle: true,
        fullscreenRotate: true  // 方案1：显示旋转按钮
    }
});
```
- `fakeFullscreen` 和 `fullscreenRotate` 是独立参数，无冲突
- `fullscreenRotate` 提供手动旋转按钮，作为自动旋转失败的备选

#### 2. 事件监听兼容性
```javascript
// 方案1：监听全屏变化
player.on('fullscreenchange', function(e) {
    if (e.detail.isFullscreen) {
        playPage.classList.add('fullscreen');
        // 尝试锁定横屏
        lockLandscape();
    } else {
        playPage.classList.remove('fullscreen');
        unlockOrientation();
    }
});

// 方案2：监听方向变化
window.addEventListener('orientationchange', function() {
    if (isLandscape()) {
        player.requestFullscreen();
    } else {
        player.exitFullscreen();
    }
});
```

**关键问题：事件循环调用风险**

场景：用户旋转设备到横屏
1. `orientationchange` 触发 → 调用 `player.requestFullscreen()`
2. 全屏状态改变 → `fullscreenchange` 触发 → 调用 `lockLandscape()`
3. 屏幕已锁定为横屏 → 无变化

✅ **不会循环调用**，因为 `lockLandscape()` 不会触发 `orientationchange`

场景：用户点击全屏按钮
1. `fullscreenchange` 触发 → 调用 `lockLandscape()`
2. 屏幕方向锁定为横屏 → **不会触发 `orientationchange`**（屏幕物理方向未变）

✅ **不会冲突**

---

## 潜在问题与解决方案

### 问题1：iOS 系统不支持 `screen.orientation.lock()`

**现象**：iOS Safari 和微信内置浏览器不支持 Screen Orientation API

**影响**：
- 方案1的方向锁定在 iOS 上无效
- 但方案2仍然有效（用户旋转设备可以触发全屏）

**解决**：添加特性检测和降级处理
```javascript
function lockLandscape() {
    if (screen.orientation && screen.orientation.lock) {
        screen.orientation.lock('landscape').catch(err => {
            console.log('无法锁定屏幕方向，使用CSS伪全屏');
        });
    } else {
        // iOS 降级：依赖用户手动旋转
        console.log('当前浏览器不支持屏幕方向锁定');
    }
}
```

### 问题2：两个方案同时触发时的状态同步

**场景**：
1. 用户旋转设备到横屏 → 方案2触发 → 自动全屏
2. 用户点击退出全屏 → `fullscreenchange` 触发 → 方案1解锁方向
3. 但设备仍处于横屏状态

**影响**：用户退出全屏后，设备横屏但播放器已退出全屏，可能造成 UI 不一致

**解决**：退出全屏时不强制恢复竖屏，只解锁方向锁定
```javascript
player.on('fullscreenchange', function(e) {
    if (e.detail.isFullscreen) {
        playPage.classList.add('fullscreen');
        lockLandscape();
    } else {
        playPage.classList.remove('fullscreen');
        // 只解锁，不强制恢复竖屏（让用户自然持握）
        unlockOrientation();
    }
});
```

### 问题3：`fakeFullscreen` 与 `requestFullscreen()` 的行为差异

**现象**：
- `fakeFullscreen: true` 时，TCPlayer 使用 CSS 实现全屏
- 但方案2调用的 `player.requestFullscreen()` 可能尝试使用 Fullscreen API

**影响**：可能导致全屏行为不一致

**解决**：确保 CSS 全屏样式与 Fullscreen API 兼容
```css
/* 同时支持 CSS 伪全屏和 Fullscreen API */
.play-page.fullscreen .player-wrapper,
.play-page:fullscreen .player-wrapper,
.play-page:-webkit-full-screen .player-wrapper {
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    z-index: 9999;
}
```

### 问题4：Android 微信浏览器的 x5 内核限制

**现象**：x5 内核不支持 Fullscreen API，强制使用 `webkitEnterFullScreen`

**影响**：
- 方案1的方向锁定可能无效
- 方案2的 `requestFullscreen()` 可能被劫持

**解决**：检测 x5 内核，调整策略
```javascript
function isX5Browser() {
    return /TBS\/|X5/i.test(navigator.userAgent);
}

// 方案2调整
window.addEventListener('orientationchange', function() {
    if (isLandscape()) {
        if (isX5Browser()) {
            // x5 内核自动处理全屏，不需要手动调用
            console.log('x5 内核，跳过自动全屏');
        } else {
            player.requestFullscreen();
        }
    }
});
```

---

## 推荐实现方案

### 整合后的代码结构

```javascript
// ========== 方案1 + 方案2 整合 ==========

// 1. TCPlayer 配置（方案1）
player = TCPlayer('player-container-id', {
    // ... 其他配置
    fakeFullscreen: true,
    controlBar: {
        fullscreenToggle: true,
        fullscreenRotate: true  // 手动旋转按钮
    }
});

// 2. 方案1：监听全屏变化 + 屏幕方向锁定
player.on('fullscreenchange', function(e) {
    const playPage = document.getElementById('playPage');
    
    if (e.detail.isFullscreen) {
        playPage.classList.add('fullscreen');
        
        // 尝试锁定横屏（带降级处理）
        if (screen.orientation && screen.orientation.lock) {
            screen.orientation.lock('landscape').catch(err => {
                console.log('无法锁定屏幕方向:', err);
            });
        }
    } else {
        playPage.classList.remove('fullscreen');
        
        // 解锁方向
        if (screen.orientation && screen.orientation.unlock) {
            screen.orientation.unlock();
        }
    }
});

// 3. 方案2：监听设备方向变化
window.addEventListener('orientationchange', function() {
    // 检测是否横屏
    const isLandscape = window.matchMedia('(orientation: landscape)').matches;
    
    if (isLandscape) {
        // 横屏时自动进入全屏（如果不在全屏状态）
        if (!player.isFullscreen()) {
            player.requestFullscreen();
        }
    } else {
        // 竖屏时自动退出全屏（如果在全屏状态）
        if (player.isFullscreen()) {
            player.exitFullscreen();
        }
    }
});
```

---

## 浏览器兼容性矩阵

| 功能 | Android Chrome | iOS Safari | 微信(Android) | 微信(iOS) |
|------|----------------|------------|---------------|-----------|
| fakeFullscreen | ✅ CSS | ✅ CSS | ✅ CSS | ✅ CSS |
| fullscreenRotate | ✅ | ✅ | ✅ | ✅ |
| screen.orientation.lock() | ✅ | ❌ | ⚠️ 部分 | ❌ |
| orientationchange 事件 | ✅ | ✅ | ✅ | ✅ |
| requestFullscreen() | ✅ Fullscreen API | ❌ webkit | ⚠️ x5劫持 | ❌ 系统劫持 |

**结论**：
- ✅ 两个方案在大多数浏览器可以共存
- ⚠️ iOS 上方向锁定无效，但方案2的自动全屏仍可用
- ⚠️ 微信内置浏览器有劫持行为，需要特殊处理

---

## 最终结论

### ✅ 可以同时加入两个方案

**理由**：
1. 两个方案针对的用户行为不同（主动点击 vs 设备旋转）
2. 事件循环调用风险低，不会互相干扰
3. 代码层面无冲突，可以独立运行
4. 提供双重保障：自动旋转 + 手动按钮

**预期效果**：
- Android Chrome：全屏自动横屏 ✅
- Android 微信：自动全屏有效，方向锁定可能无效 ⚠️
- iOS Safari：自动全屏有效，方向锁定无效 ⚠️
- iOS 微信：系统劫持播放，代码控制有限 ⚠️

**建议**：同时实施两个方案，提供最佳用户体验，并为 iOS 和微信环境做好降级处理。
