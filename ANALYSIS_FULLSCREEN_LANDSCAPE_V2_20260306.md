# 移动端全屏播放没有横屏问题分析（结合官方文档）

## 官方文档关键信息

### 文档1：TCPlayer 配置参数 (https://cloud.tencent.com/document/product/881/30820)

#### 关键参数发现

| 参数名 | 类型 | 默认值 | 说明 |
|-------|------|--------|------|
| `fakeFullscreen` | Boolean | false | **设置开启伪全屏，通过样式控制来实现全屏效果** |
| `controlBar.fullscreenRotate` | Boolean | false | **是否显示画面旋转按钮** |

#### TCPlayer 全屏相关方法
- `requestFullscreen()`: 进入全屏模式
- `exitFullscreen()`: 退出全屏模式
- `isFullscreen()`: 返回是否进入了全屏模式
- `fullscreenchange` 事件：全屏状态切换时触发

### 文档2：常见问题 (https://cloud.tencent.com/document/product/881/20219)

#### 全屏模式说明
**屏幕全屏**：在屏幕范围内全屏，全屏后只有视频画面内容，看不到浏览器地址栏。

**网页全屏（伪全屏）**：在网页显示区域范围内全屏，仍可以看到浏览器地址栏，由 CSS 实现。

**全屏优先级**：Fullscreen API > webkitEnterFullScreen > 网页全屏

#### 移动端全屏现状
| 平台 | Fullscreen API | webkitEnterFullScreen | 全屏表现 |
|------|----------------|----------------------|---------|
| iOS (微信/Safari/QQ) | ❌ 不支持 | ✅ 支持 | 进入 iOS 系统 UI 全屏 |
| Android Chrome | ✅ 支持 | - | 进入带 TCPlayer UI 的屏幕全屏 |
| x5 内核(微信/QQ浏览器) | ❌ 不支持 | ✅ 支持 | 进入 x5 内核屏幕全屏 |

---

## 结合文档的问题分析

### 当前移动端代码配置
```javascript
player = TCPlayer('player-container-id', {
    appID: playerConfig.appID,
    fileID: playerConfig.fileID,
    psign: playerConfig.psign,
    width: playerSize.width,
    height: playerSize.height,
    controlBar: {
        playToggle: true,
        progressControl: true,
        currentTimeDisplay: true,
        durationDisplay: true,
        timeDivider: true,
        playbackRateMenuButton: false,
        volumePanel: true,
        fullscreenToggle: true    // ✅ 启用了全屏按钮
        // ❌ 缺少: fullscreenRotate: true
    },
    // ❌ 缺少: fakeFullscreen: true
});
```

### 根本原因分析

#### 1. TCPlayer 没有提供屏幕方向锁定功能
根据官方文档，TCPlayer **没有**提供以下功能的配置参数：
- ❌ 屏幕方向锁定（orientation lock）
- ❌ 全屏时自动横屏
- ❌ 强制横屏播放

TCPlayer 的 `fullscreenchange` 事件仅通知全屏状态变化，**不包含屏幕方向控制**。

#### 2. 移动端全屏的行为差异

**iOS 平台**：
- 不支持 Fullscreen API
- 通过 `webkitEnterFullScreen` 进入系统全屏
- **系统强制控制播放界面，无法通过代码控制横屏**
- 用户需要手动旋转设备

**Android 平台**：
- Chrome 支持 Fullscreen API
- 但 TCPlayer 的 `requestFullscreen()` 仅作用于播放器容器
- **不会自动触发屏幕方向锁定**

#### 3. 当前代码缺少关键配置

| 缺失配置 | 文档说明 | 影响 |
|---------|---------|------|
| `fakeFullscreen: true` | 通过样式控制实现全屏效果 | 无法使用 CSS 自定义全屏样式 |
| `fullscreenRotate: true` | 显示画面旋转按钮 | 用户无法通过播放器按钮旋转画面 |
| 屏幕方向锁定代码 | 文档未提供，需自行实现 | 全屏后无法自动横屏 |

#### 4. 技术限制
根据文档，TCPlayer 的全屏功能设计为：
1. **优先使用浏览器原生全屏 API**
2. **不支持自定义全屏时的屏幕方向**
3. **移动端依赖浏览器劫持播放**

这意味着：
- TCPlayer 仅负责触发全屏
- 屏幕方向控制超出 TCPlayer 能力范围
- 需要通过浏览器原生 API (`screen.orientation`) 额外实现

---

## 解决方案（基于文档建议）

### 方案1：启用 TCPlayer 伪全屏 + 屏幕方向锁定（推荐）

```javascript
// TCPlayer 配置修改
player = TCPlayer('player-container-id', {
    // ... 其他配置
    fakeFullscreen: true,  // 启用伪全屏，通过 CSS 控制
    controlBar: {
        fullscreenToggle: true,
        fullscreenRotate: true  // 显示旋转按钮
    }
});

// 监听全屏变化，手动控制屏幕方向
player.on('fullscreenchange', function(e) {
    const playPage = document.getElementById('playPage');
    
    if (e.detail.isFullscreen) {
        playPage.classList.add('fullscreen');
        
        // 尝试锁定横屏（需要用户交互触发）
        if (screen.orientation && screen.orientation.lock) {
            screen.orientation.lock('landscape').catch(err => {
                console.log('无法锁定屏幕方向:', err);
            });
        }
    } else {
        playPage.classList.remove('fullscreen');
        
        // 解锁屏幕方向
        if (screen.orientation && screen.orientation.unlock) {
            screen.orientation.unlock();
        }
    }
});
```

### 方案2：使用原生 webkitEnterFullScreen（iOS 兼容）

```javascript
// 针对 iOS 的特殊处理
const videoEl = document.getElementById('player-container-id');

if (videoEl.webkitEnterFullScreen) {
    // iOS 设备使用原生全屏
    videoEl.addEventListener('webkitbeginfullscreen', function() {
        // iOS 系统会强制全屏播放，无法控制横屏
        console.log('iOS 全屏开始');
    });
    
    videoEl.addEventListener('webkitendfullscreen', function() {
        console.log('iOS 全屏结束');
    });
}
```

### 方案3：CSS 伪全屏 + 横屏检测（兼容性最好）

```css
/* 横屏时的播放器样式 */
@media screen and (orientation: landscape) {
    .play-page.fullscreen .player-wrapper {
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        z-index: 9999;
    }
}
```

```javascript
// 监听方向变化
window.addEventListener('orientationchange', function() {
    if (window.matchMedia('(orientation: landscape)').matches) {
        // 横屏时自动进入全屏
        if (player && player.requestFullscreen) {
            player.requestFullscreen();
        }
    }
});
```

---

## 浏览器兼容性说明

### Screen Orientation API 兼容性
| 浏览器 | 支持情况 |
|-------|---------|
| Android Chrome | ✅ 支持 |
| iOS Safari | ⚠️ 有限支持（需用户交互） |
| 微信内置浏览器 | ⚠️ 部分支持 |
| QQ浏览器 | ⚠️ 部分支持 |

### 伪全屏 (fakeFullscreen) 兼容性
- 纯 CSS/JS 实现
- 不依赖浏览器全屏 API
- **所有浏览器都支持**

---

## 结论

### 问题根本原因
根据腾讯云官方文档，**TCPlayer 本身不提供屏幕方向控制功能**。移动端全屏后没有横屏的原因是：

1. **TCPlayer 设计限制**：TCPlayer 只负责触发全屏，屏幕方向控制需要额外实现
2. **iOS 系统限制**：iOS 强制使用系统播放器，无法通过代码控制横屏
3. **当前代码配置不完整**：缺少 `fakeFullscreen` 和 `fullscreenRotate` 配置
4. **缺少屏幕方向锁定代码**：需要使用浏览器原生 `screen.orientation` API

### 建议方案
1. **启用 `fakeFullscreen: true`**：获得 CSS 控制权
2. **启用 `fullscreenRotate: true`**：给用户手动旋转画面的按钮
3. **添加 `screen.orientation.lock('landscape')`**：尝试自动锁定横屏
4. **监听 `orientationchange` 事件**：设备旋转时自动进入/退出全屏

**注意**：由于 iOS 系统限制，无法强制自动横屏，用户需要手动旋转设备。
