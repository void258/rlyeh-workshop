/* 逐帧渲染用的虚拟时钟，由 replay render 在页面脚本之前注入（普通播放不加载）。
 * 接管 setTimeout / setInterval / requestAnimationFrame / performance.now / Date.now / Math.random，
 * 所有 CSS 动画和过渡都暂停，每帧按虚拟时间直接设 currentTime。
 * 渲染时每帧调用 await window.__advance(毫秒)，再截图——画面只取决于虚拟时间，不会掉帧。
 */
(() => {
  let vt = 0;
  let seq = 0;
  const timers = new Map();
  let rafs = [];
  const dateOrigin = Date.now();
  performance.now = () => vt;
  Date.now = () => dateOrigin + vt;
  window.__vt = () => vt;

  // 固定种子的随机数，每次渲染结果一样
  let s = 20261022 >>> 0;
  Math.random = () => {
    s = (s + 0x6D2B79F5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };

  window.setTimeout = (fn, ms = 0, ...args) => { const id = ++seq; timers.set(id, { id, due: vt + Math.max(0, +ms || 0), fn, args }); return id; };
  window.setInterval = (fn, ms = 0, ...args) => { const id = ++seq; const iv = Math.max(1, +ms || 0); timers.set(id, { id, due: vt + iv, fn, args, iv }); return id; };
  window.clearTimeout = window.clearInterval = id => { timers.delete(id); };
  window.requestAnimationFrame = fn => { const id = ++seq; rafs.push({ id, fn }); return id; };
  window.cancelAnimationFrame = id => { rafs = rafs.filter(r => r.id !== id); };

  // 让出一个宏任务：前面回调里 resolve 的 Promise 续体（await 之后的代码）都会先跑完
  const mc = new MessageChannel();
  const waiting = [];
  mc.port1.onmessage = () => { const r = waiting.shift(); if (r) r(); };
  const yieldTask = () => new Promise(r => { waiting.push(r); mc.port2.postMessage(0); });

  const started = new WeakMap();
  window.__advance = async dt => {
    const target = vt + dt;
    for (let guard = 0; guard < 20000; guard++) {      // 按到期先后、创建先后依次触发
      let next = null;
      for (const t of timers.values()) {
        if (t.due <= target && (!next || t.due < next.due || (t.due === next.due && t.id < next.id))) next = t;
      }
      if (!next) break;
      vt = Math.max(vt, next.due);
      if (next.iv) next.due += next.iv; else timers.delete(next.id);
      try { next.fn(...next.args); } catch (e) { console.error(e); }
      await yieldTask();
    }
    const prev = target - dt;
    vt = target;
    const list = rafs;
    rafs = [];
    for (const r of list) { try { r.fn(vt); } catch (e) { console.error(e); } }
    await yieldTask();
    // CSS 动画、过渡：第一次见到时把起点记在上一帧，之后每帧按虚拟时间定位
    for (const a of document.getAnimations()) {
      if (!started.has(a)) started.set(a, prev);
      if (a.playState !== 'paused') a.pause();
      a.currentTime = vt - started.get(a);
    }
    return vt;
  };
})();
