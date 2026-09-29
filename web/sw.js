/**
 * Service worker tối giản.
 *
 * Chỉ cache vỏ app (HTML/CSS/JS) để mở lại nhanh khi sóng yếu. KHÔNG cache lời
 * gọi /api — hàng chờ và trạng thái phát phải luôn là dữ liệu tươi, hiện nhầm
 * hàng chờ cũ còn tệ hơn là báo mất kết nối.
 */

const CACHE = 'karaoke-shell-v1';
const SHELL = ['./', 'index.html', 'styles.css', 'app.js', 'manifest.webmanifest'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith('/api')) return; // luôn đi thẳng ra mạng
  event.respondWith(
    caches.match(event.request).then((hit) => hit || fetch(event.request))
  );
});
