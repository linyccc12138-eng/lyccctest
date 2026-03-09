/**
 * Service Worker - 静态资源缓存
 * 缓存 CSS、JS、字体等静态资源，避免重复加载
 */

const CACHE_NAME = 'course-platform-v1';
const STATIC_ASSETS = [
    '/static/css/mobile-mucha.css',
    '/static/css/style.css',
    '/static/css/style-transcode.css',
    '/static/vendor/phosphor-icons/index.js',
    '/static/js/main.js',
    '/static/vendor/phosphor-icons/regular/style.css',
    '/static/vendor/phosphor-icons/fill/style.css',
    '/static/vendor/phosphor-icons/bold/style.css',
    '/static/vendor/phosphor-icons/light/style.css',
    '/static/vendor/phosphor-icons/thin/style.css',
    '/static/vendor/phosphor-icons/duotone/style.css',
];

// 安装时缓存静态资源
self.addEventListener('install', function(event) {
    event.waitUntil(
        caches.open(CACHE_NAME).then(function(cache) {
            console.log('[SW] 缓存静态资源');
            return cache.addAll(STATIC_ASSETS).catch(function(err) {
                console.log('[SW] 部分资源缓存失败:', err);
            });
        }).then(function() {
            return self.skipWaiting();
        })
    );
});

// 激活时清理旧缓存
self.addEventListener('activate', function(event) {
    event.waitUntil(
        caches.keys().then(function(cacheNames) {
            return Promise.all(
                cacheNames.filter(function(name) {
                    return name !== CACHE_NAME;
                }).map(function(name) {
                    console.log('[SW] 清理旧缓存:', name);
                    return caches.delete(name);
                })
            );
        }).then(function() {
            return self.clients.claim();
        })
    );
});

// 拦截请求，优先从缓存获取
self.addEventListener('fetch', function(event) {
    const request = event.request;
    const url = new URL(request.url);
    
    // 只处理 GET 请求
    if (request.method !== 'GET') {
        return;
    }
    
    // 只缓存静态资源
    const isStaticAsset = 
        url.pathname.startsWith('/static/') ||
        url.pathname.startsWith('/vendor/') ||
        url.host.includes('fonts.googleapis.com') ||
        url.host.includes('fonts.gstatic.com') ||
        url.pathname.includes('.css') ||
        url.pathname.includes('.js') ||
        url.pathname.includes('.woff') ||
        url.pathname.includes('.woff2') ||
        url.pathname.includes('.ttf') ||
        url.pathname.includes('.svg');
    
    if (!isStaticAsset) {
        return;
    }
    
    event.respondWith(
        caches.match(request).then(function(cachedResponse) {
            // 缓存命中，直接返回
            if (cachedResponse) {
                // 后台更新缓存（Stale-while-revalidate 策略）
                fetch(request).then(function(networkResponse) {
                    if (networkResponse.ok) {
                        caches.open(CACHE_NAME).then(function(cache) {
                            cache.put(request, networkResponse);
                        });
                    }
                }).catch(function() {
                    // 网络请求失败，使用缓存
                });
                return cachedResponse;
            }
            
            // 缓存未命中，从网络获取并缓存
            return fetch(request).then(function(networkResponse) {
                if (!networkResponse || networkResponse.status !== 200 || networkResponse.type !== 'basic') {
                    return networkResponse;
                }
                
                const responseToCache = networkResponse.clone();
                caches.open(CACHE_NAME).then(function(cache) {
                    cache.put(request, responseToCache);
                });
                
                return networkResponse;
            });
        })
    );
});
