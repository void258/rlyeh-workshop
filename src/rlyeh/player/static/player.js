/* 拉莱耶工坊 · 视觉小说播放器。数据来自 data.js（replay build 生成）。
 * 操作：点击 / 空格 / 回车 下一句，A 自动，S 或按住 Ctrl 快进，L / 滚轮上 记录，H 隐藏界面，R 重听，M 静音，F 全屏。
 * 地址参数：#c1-0100 从这句开始；?auto 自动播放；?rec 渲染模式（不显示按钮和鼠标，载入完等渲染脚本调 __go 开始）；
 * ?rec&chapter=N 只渲染第 N 章（从 0 数）。
 * 渲染模式不真正放声音：配音按 data.js 里的时长计时，配音、音效、BGM 的时间点记在 window.__rec.events，
 * 由 replay render 渲染完画面后照着这份记录离线混音。
 */
'use strict';
(() => {
  const R = window.REPLAY;
  const W = 1920, H = 1080;
  const $ = (s, root = document) => root.querySelector(s);
  const make = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const rand = (a, b) => a + Math.random() * (b - a);
  const pick = arr => arr[Math.floor(Math.random() * arr.length)];
  const reflow = node => void node.offsetWidth;
  const ABORT = Symbol('abort');
  const params = new URLSearchParams(location.search);
  const REC = params.has('rec');
  const CHAPTER = params.has('chapter') ? +params.get('chapter') : null;

  // ───────── 界面文字 ─────────
  const TEXT = {
    zh: { oocHead: '场外 · OOC', ooc: '场外', narrator: '旁白', combat: '战斗中 · ', round1: '第一轮', battleStart: '战斗开始',
      battleEnd: '战斗结束', end: '完', loading: '载入素材', start: '开始', cont: '继续', auto: '自动', skip: '快进', logBtn: '记录',
      hide: '隐藏', mute: '静音', full: '全屏', titleBtn: '标题', log: '对话记录', logHint: 'Esc / 右键 关闭 · 点名字旁的 ▶ 重听 · 点 ↺ 从这句开始',
      replay: '重听', jump: '从这句开始', autoChip: '自动 ▶', skipChip: '快进 ▶▶',
      results: { hit: '命中', miss: '未中', success: '成功', failure: '失败', critical: '大成功', fumble: '大失败' } },
    en: { oocHead: 'OOC · TABLE TALK', ooc: 'OOC', narrator: 'Narrator', combat: 'In combat · ', round1: 'Round 1', battleStart: 'Battle',
      battleEnd: 'Battle over', end: 'Fin', loading: 'Loading', start: 'Start', cont: 'Continue', auto: 'Auto', skip: 'Skip', logBtn: 'Log',
      hide: 'Hide', mute: 'Mute', full: 'Full', titleBtn: 'Title', log: 'Log', logHint: 'Esc / right click to close · ▶ replays a line · ↺ starts from it',
      replay: 'Replay', jump: 'Start here', autoChip: 'AUTO ▶', skipChip: 'SKIP ▶▶',
      results: { hit: 'Hit', miss: 'Miss', success: 'Success', failure: 'Failure', critical: 'Critical', fumble: 'Fumble' } },
  };
  const L = (R.lang || 'zh-CN').startsWith('en') ? 'en' : 'zh';
  const T = TEXT[L];
  document.documentElement.lang = L === 'en' ? 'en' : 'zh-CN';
  document.title = [R.title, R.subtitle].filter(Boolean).join(' · ');
  document.querySelectorAll('[data-i]').forEach(e => { e.textContent = T[e.dataset.i]; });

  const stage = $('#stage'), world = $('#world'), bgLayer = $('#bg'), charsEl = $('#chars'), cgEl = $('#cg'), coldEl = $('#cold'),
    flashEl = $('#flash'), hud = $('#hud'), ui = $('#ui'), box = $('#box'), plate = $('.nameplate', box), nameEl = $('.name', box),
    subEl = $('.sub', box), textEl = $('.text', box), nextEl = $('.next', box), chatEl = $('#chat'), chatList = $('.chat-list'),
    sceneEl = $('#scene-title'), combatEl = $('#combat'), chipEl = $('#mode-chip'), card = $('#card'), creditsEl = $('#credits'),
    logEl = $('#log'), logList = $('.log-list'), titleEl = $('#title'), progEl = $('#progress i');

  // ───────── 舞台缩放 ─────────
  let scale = 1;
  function fit() { scale = Math.min(innerWidth / W, innerHeight / H); stage.style.transform = `translate(-50%, -50%) scale(${scale})`; }
  addEventListener('resize', fit); fit();
  function stagePoint(node, fy = .5) {
    const r = node.getBoundingClientRect(), s = stage.getBoundingClientRect();
    return { x: (r.left + r.width / 2 - s.left) / scale, y: (r.top + r.height * fy - s.top) / scale };
  }

  // ───────── 角色 ─────────
  const charOf = key => R.chars[key] ? key : R.who[key] || null;               // 角色 ID 或显示名 → 角色 ID
  const nameOf = key => { const id = charOf(key); return id ? R.chars[id].name : key; };

  // ───────── 剧本 ─────────
  const STEPS = [], CH_START = [];
  R.chapters.forEach((ch, ci) => { CH_START.push(STEPS.length); ch.steps.forEach(s => STEPS.push(Object.assign({ ci }, s))); });
  CH_START.push(STEPS.length);
  const isText = s => s.k === 'nar' || s.k === 'line' || s.k === 'ooc';
  const S = { pc: 0, gen: 0, auto: params.has('auto') || REC, skip: false, muted: false, typing: false, title: true, combat: null,
    chapterTitle: '', preBattle: null, lastSkill: '', speaker: null };
  const RECLOG = window.__rec = { events: [], done: false };
  const log = e => { if (REC) RECLOG.events.push(Object.assign({ t: performance.timeOrigin + performance.now() }, e)); };

  // 可被点击加速的等待；换章节或回标题时，旧流程在下一次等待处被中止
  const waiters = new Set();
  function wait(ms) {
    if (S.skip) ms = Math.min(ms, 50);
    return new Promise(res => {
      const done = () => { clearTimeout(t); waiters.delete(done); res(); };
      const t = setTimeout(done, ms);
      waiters.add(done);
    });
  }
  function hurry() { [...waiters].forEach(f => f()); }
  async function W_(ms) { const g = S.gen; await wait(ms); if (g !== S.gen) throw ABORT; }
  // 片尾这种长段落不让一次误点就跳过；要退出按 Esc 回标题
  async function firm(ms) { const g = S.gen; await new Promise(res => setTimeout(res, ms)); if (g !== S.gen) throw ABORT; }

  // ───────── 配音 ─────────
  const voiceCache = new Map();
  let curAudio = null;
  function audioFor(src) {
    let a = voiceCache.get(src);
    if (!a) { a = new Audio(src); a.preload = 'auto'; voiceCache.set(src, a); }
    return a;
  }
  function preloadAhead() {
    if (REC) return;
    for (let i = S.pc, n = 0; i < STEPS.length && n < 4; i++) if (STEPS[i].voice) { audioFor(STEPS[i].voice); n++; }
  }
  function playVoice(src, onEnd, sec) {
    stopVoice();
    if (!src || S.skip) { onEnd(); return; }
    music.duck = true;
    if (REC) { log({ type: 'voice', src, sec }); const t = setTimeout(() => { music.duck = false; onEnd(); }, sec * 1000); curAudio = { pause: () => clearTimeout(t) }; return; }
    const a = audioFor(src);
    voiceCache.delete(src);
    a.currentTime = 0; a.volume = S.muted ? 0 : 1; curAudio = a;
    let fired = false;
    const fin = () => { if (fired) return; fired = true; a.onended = a.onerror = null; if (curAudio === a) curAudio = null; music.duck = false; onEnd(); };
    a.onended = fin; a.onerror = fin;
    a.play().catch(fin);
  }
  function stopVoice() { music.duck = false; if (curAudio) { const a = curAudio; curAudio = null; a.onended = a.onerror = null; a.pause(); } }

  // ───────── 音效、BGM ─────────
  const SFX_VOL = .9, BGM_VOL = .32;
  const lastPlayed = new Map();
  function sfx(name, vol = 1) {
    const e = R.sfx[name];
    if (!e || S.skip) return;
    const now = performance.now();
    if (e.min_gap && now - (lastPlayed.get(name) ?? -1e12) < e.min_gap * 1000) return;     // 同一个音效隔太近就不放
    lastPlayed.set(name, now);
    const g = (e.gain ?? .7) * vol;
    log({ type: 'sfx', name, src: e.src, gain: g });
    if (REC) return;
    const a = new Audio(e.src);
    a.volume = S.muted ? 0 : Math.min(1, g * SFX_VOL);
    a.play().catch(() => {});
  }
  // BGM：同时可能有一首在淡入、几首在淡出；说话时压低
  const music = { cue: null, el: null, all: new Set(), duck: false };
  function bgm(cue, fade = 2.5) {
    cue = cue || null;
    if (music.cue === cue) return;
    music.cue = cue;
    log({ type: 'bgm', cue, src: cue && R.bgm[cue], fade });
    for (const a of music.all) { a._target = 0; a._rate = 1 / Math.max(.1, fade); }
    music.el = null;
    if (REC || !cue || !R.bgm[cue]) return;
    const a = new Audio(R.bgm[cue]);
    a.loop = true; a.volume = 0; a._g = 0; a._target = 1; a._rate = 1 / Math.max(.1, fade);
    a.play().catch(() => {});
    music.el = a; music.all.add(a);
  }
  function musicFrame(dt) {
    for (const a of music.all) {
      a._g += Math.sign(a._target - a._g) * Math.min(Math.abs(a._target - a._g), a._rate * dt);
      a.volume = S.muted ? 0 : Math.max(0, Math.min(1, a._g * BGM_VOL * (music.duck ? .6 : 1)));
      if (a._target === 0 && a._g <= 0) { a.pause(); music.all.delete(a); }
    }
  }

  // ───────── 文字 ─────────
  const textLen = rich => rich.reduce((n, [, s]) => n + [...s].length, 0);
  const renderRich = rich => rich.map(([t, s]) => t === 't' ? esc(s) : `<span class="${t === 'b' ? 'bleep' : 'act'}">${esc(s)}</span>`).join('');
  function typeInto(target, rich, interval) {
    target.classList.remove('instant');
    target.innerHTML = '';
    let i = 0;
    for (const [t, s] of rich) {
      const host = t === 't' ? target : target.appendChild(make('span', t === 'b' ? 'bleep' : 'act'));
      for (const c of s) {
        const sp = make('span', 'ch');
        sp.textContent = c;
        if (interval) sp.style.animationDelay = (i * interval).toFixed(3) + 's';
        host.appendChild(sp);
        i++;
      }
    }
    if (!interval) target.classList.add('instant');
  }

  let cur = null, advanceFn = null, typeTimer = 0, autoTimer = 0;
  function showText(s) {
    const n = Math.max(1, textLen(s.rich));
    const interval = S.skip ? 0 : s.sec ? Math.min(.05, Math.max(.015, s.sec * .62 / n)) : .028;
    if (s.k === 'line') stageSpeak(s);
    else if (s.k === 'nar') setSpeaker(null);
    let target;
    if (s.k === 'ooc') { target = pushBubble(s); if (!box.classList.contains('empty')) box.classList.add('muted'); }
    else { hideChat(); target = setBox(s); }
    typeInto(target, s.rich, interval);
    const c = cur = { s, target, voiceDone: false };
    clearTimeout(typeTimer); clearTimeout(autoTimer);
    nextEl.classList.remove('on');
    S.typing = interval > 0;
    if (S.typing) typeTimer = setTimeout(() => { S.typing = false; ready(); }, n * interval * 1000 + 250);
    playVoice(s.voice, () => { c.voiceDone = true; if (cur === c) ready(); }, s.sec);
    addLog(S.pc - 1, s); preloadAhead(); progress(); save();
  }
  function ready() {
    if (!cur || S.typing) return;
    nextEl.classList.add('on');
    clearTimeout(autoTimer);
    if (logEl.classList.contains('on')) return;
    if (S.skip) autoTimer = setTimeout(advance, 30);
    else if (S.auto && cur.voiceDone) {
      const s = cur.s;
      autoTimer = setTimeout(advance, s.voice ? (s.k === 'ooc' ? 260 : s.k === 'nar' ? 450 : 380) : 900 + 55 * textLen(s.rich));
    }
  }
  function finishTyping() { clearTimeout(typeTimer); if (cur) cur.target.classList.add('instant'); S.typing = false; ready(); }
  function advance() { if (advanceFn) { const f = advanceFn; advanceFn = null; f(); } }
  function waitAdvance() {
    const g = S.gen;
    return new Promise((res, rej) => {
      advanceFn = () => { clearTimeout(autoTimer); if (g === S.gen) res(); else rej(ABORT); };
      ready();
    });
  }

  function setBox(s) {
    box.classList.remove('empty', 'muted');
    if (s.k === 'nar') { box.classList.add('nar'); return textEl; }
    const id = charOf(s.who), c = id ? R.chars[id] : {}, name = id ? c.name : s.who;
    if (box.classList.contains('nar') || nameEl.textContent !== name) { plate.classList.remove('pop'); reflow(plate); plate.classList.add('pop'); }
    box.classList.remove('nar');
    box.style.setProperty('--c', c.color || '#777');
    nameEl.textContent = name;
    subEl.textContent = c.player ? 'PL · ' + c.player : '';
    return textEl;
  }

  // ───────── 场外弹幕（聊天栏） ─────────
  const GM_AVATAR = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><radialGradient id="g" cx="50%" cy="38%"><stop offset="0" stop-color="#43357c"/><stop offset="1" stop-color="#120e24"/></radialGradient></defs><rect width="100" height="100" fill="url(#g)"/><g fill="none" stroke="#c4b8ff" stroke-width="2.4" stroke-linejoin="round"><polygon points="50,14 81,32 81,68 50,86 19,68 19,32"/><polygon points="50,30 67,60 33,60"/><path d="M50,14 50,30 M81,32 50,30 M19,32 50,30 M81,32 67,60 M81,68 67,60 M50,86 67,60 M50,86 33,60 M19,68 33,60 M19,32 33,60"/></g><text x="50" y="54.5" font-family="serif" font-size="12" font-weight="700" fill="#efeaff" text-anchor="middle">GM</text></svg>');
  function playerInfo(who) {
    const p = R.players[who] || {};
    return { color: p.color || '#999', avatar: p.avatar || (p.gm ? GM_AVATAR : null), char: p.char ? nameOf(p.char) : null, gm: !!p.gm };
  }
  function pushBubble(s) {
    chatEl.classList.add('on');
    const p = playerInfo(s.who);
    [...chatList.children].forEach(b => b.classList.add('old'));
    const b = make('div', 'bub' + (p.gm ? ' gm' : ''),
      `<div class="av"></div><div><div class="who">${esc(s.who)}${p.char ? `<small>${esc(p.char)}</small>` : ''}</div><div class="msg"></div></div>`);
    b.style.setProperty('--c', p.color);
    if (p.avatar) b.querySelector('.av').style.backgroundImage = `url("${p.avatar}")`;
    chatList.appendChild(b);
    // 先按条数淘汰（带动画），再按高度兜底
    const live = [...chatList.children].filter(x => !x.classList.contains('gone'));
    if (live.length > 4) { const old = live[0]; old.classList.add('gone'); setTimeout(() => old.remove(), 360); }
    while (chatList.offsetHeight > 660 && chatList.children.length > 1) chatList.firstElementChild.remove();
    return b.querySelector('.msg');
  }
  function hideChat(instant) {
    box.classList.remove('muted');
    if (!chatEl.classList.contains('on')) return;
    chatEl.classList.remove('on');
    const items = [...chatList.children];
    if (instant) items.forEach(n => n.remove()); else setTimeout(() => items.forEach(n => n.remove()), 520);
  }

  // ───────── 立绘调度：谁说话谁上场，最多三人 ─────────
  const cast = [];
  let tick = 0;
  const remembered = new Map();          // 登场时写的状态（hurt、ghost），退场前一直保持
  const SLOTS = [[], [50], [33, 67], [21, 50, 79]];
  const INTENSE = /吼|大喊|咆哮|尖叫|呼救|大叫|破口大骂|暴怒|狂笑|大笑|惊呼|痛呼|shout|scream|yell|roar|furious|laugh/i;
  const stateFace = (id, state) => state && (R.chars[id]?.state_faces || {})[state];
  function spriteSrc(id, face) {
    const c = R.chars[id];
    if (!c || !c.faces || !Object.keys(c.faces).length) return null;
    return c.faces[face] || c.faces[c.default] || Object.values(c.faces)[0];
  }
  const castFind = id => cast.find(c => c.id === id);
  function layout() { const xs = SLOTS[cast.length]; cast.forEach((c, i) => { c.node.style.left = xs[i] + '%'; }); }
  function castAdd(id, { face, pos, state, pinned, instant } = {}) {
    let c = castFind(id);
    if (c) return c;
    state = state || remembered.get(id);
    face = stateFace(id, state) || face;
    const src = spriteSrc(id, face);
    if (!src) return null;
    if (cast.length >= 3) {
      const victim = cast.filter(x => !x.pinned).sort((a, b) => a.last - b.last)[0];
      if (!victim) return null;
      castRemove(victim.id, instant);
    }
    const cfg = R.chars[id];
    const node = make('div', 'char', '<div class="lift"><div class="jolt"><div class="body"><img class="on" alt=""><img alt=""></div></div></div>');
    node.style.setProperty('--sc', cfg.scale);
    node.querySelector('img').src = src;
    if (state) node.classList.add('st-' + state);
    c = { id, node, face: face && cfg.faces[face] ? face : cfg.default, pinned: !!pinned, last: ++tick };
    if (pos === 'left') cast.unshift(c);
    else if (pos === 'center') cast.splice(Math.floor(cast.length / 2 + .5), 0, c);
    else cast.push(c);
    layout();
    charsEl.appendChild(node);
    if (instant) node.classList.add('in');
    else requestAnimationFrame(() => requestAnimationFrame(() => node.classList.add('in')));
    return c;
  }
  function castRemove(id, instant) {
    const i = cast.findIndex(c => c.id === id);
    if (i < 0) return;
    const [c] = cast.splice(i, 1);
    if (instant) c.node.remove();
    else { c.node.classList.remove('in', 'speaking'); c.node.classList.add('out'); setTimeout(() => c.node.remove(), 700); }
    layout();
  }
  function castClear(instant) { [...cast].forEach(c => castRemove(c.id, instant)); }
  function setFace(c, face) {
    if (!face || face === c.face) return;
    const src = spriteSrc(c.id, face);
    if (!src) return;
    c.face = face;
    const imgs = c.node.querySelectorAll('img');
    const on = imgs[0].classList.contains('on') ? imgs[0] : imgs[1], off = on === imgs[0] ? imgs[1] : imgs[0];
    const swap = () => { if (c.face !== face) return; off.classList.add('on'); on.classList.remove('on'); };
    off.onload = null;
    off.src = src;
    if (off.complete) swap(); else off.onload = swap;
  }
  function setSpeaker(id) {
    if (id) S.speaker = id;
    cast.forEach(c => c.node.classList.toggle('speaking', c.id === id));
    charsEl.classList.toggle('lit', !id);
  }
  function stageSpeak(s, instant) {
    const id = charOf(s.who);
    if (id && spriteSrc(id)) {
      const c = castFind(id) || castAdd(id, { face: s.face, instant });
      if (c) { c.last = ++tick; setFace(c, stateFace(id, remembered.get(id)) || s.face); }
    }
    setSpeaker(id || s.who);
    if (!instant && s.tone && INTENSE.test(s.tone)) {
      const c = id && castFind(id);
      if (c) { c.node.classList.remove('jolt-on'); reflow(c.node); c.node.classList.add('jolt-on'); }
      box.classList.remove('shock'); reflow(box); box.classList.add('shock');
    }
  }
  // 立绘上的一个点（按当前显示的那张图算，含呼吸、跳动的位移），xy 是相对立绘宽高的比例
  function spritePoint(c, [fx, fy]) {
    const img = c.node.querySelector('img.on') || c.node;
    const r = img.getBoundingClientRect(), s = stage.getBoundingClientRect();
    return { x: (r.left - s.left + r.width * fx) / scale, y: (r.top - s.top + r.height * fy) / scale };
  }
  const headPoint = c => spritePoint(c, R.chars[c.id].head || [.5, .2]);

  // ───────── 背景 ─────────
  let bgNow = { name: null, tags: [] };
  function setBg(name, tags, instant) {
    const node = make('div', 'bg' + (Math.random() < .5 ? ' kb2' : ''));
    let extra = '';
    if (tags.includes('dawn') || tags.includes('mist')) extra += '<div class="rays"></div>';
    if (tags.includes('shadows')) extra += '<div class="shadows"><i></i><i></i><i></i></div>';
    node.innerHTML = `<div class="pan">${R.bg[name] ? `<img src="${R.bg[name]}" alt="">` : ''}<div class="grade"></div><div class="tint"></div>${extra}</div>`;
    tags.forEach(t => node.classList.add('v-' + t));
    const old = [...bgLayer.children];
    bgLayer.appendChild(node);
    if (instant) { node.classList.add('on'); old.forEach(n => n.remove()); }
    else { requestAnimationFrame(() => requestAnimationFrame(() => node.classList.add('on'))); setTimeout(() => old.forEach(n => n.remove()), 1700); }
    bgNow = { name, tags };
    world.classList.toggle('siege', tags.includes('siege'));
    atmo.set(name, tags);
  }

  // ───────── CG、寒气、闪光、震屏 ─────────
  function showCG(name) {
    if (!R.cg[name]) return;
    const n = make('div', 'cg-img');
    n.style.setProperty('--img', `url("${R.cg[name]}")`);
    cgEl.replaceChild(n, cgEl.querySelector('.cg-img'));
    cgEl.classList.add('on');
    charsEl.classList.add('hide');
  }
  function hideCG() { cgEl.classList.remove('on'); charsEl.classList.remove('hide'); }
  const coldOn = () => coldEl.classList.add('on');
  const coldOff = () => coldEl.classList.remove('on');
  function flash(bg, dur = .7, peak = 1) {
    flashEl.style.background = bg;
    flashEl.style.setProperty('--dur', dur + 's');
    flashEl.style.setProperty('--peak', peak);
    flashEl.classList.remove('go'); reflow(flashEl); flashEl.classList.add('go');
  }
  function shake(kind = 'shake') {
    world.classList.remove('shake', 'shake-big', 'thud', 'dash'); reflow(world); world.classList.add(kind);
    clearTimeout(world._t); world._t = setTimeout(() => world.classList.remove(kind), 1000);
  }

  // ───────── 氛围粒子（雾、浮尘、孢子、围城落灰），按背景变体来 ─────────
  const AMBIENT = Object.entries(R.sfx).filter(([, e]) => e.ambient === 'siege').map(([k]) => k);
  const atmo = (() => {
    const cv = $('#atmo'), cx = cv.getContext('2d');
    const sprites = new Map();
    let fog = [], motes = [], spores = [], dust = [];
    let fogTint = '215,220,230', moteTint = '200,215,255', siege = false, thudT = 0;
    function soft(rgb, size = 64, mid = .35) {
      const key = rgb + '|' + size + '|' + mid;
      if (sprites.has(key)) return sprites.get(key);
      const c = document.createElement('canvas');
      c.width = c.height = size;
      const g = c.getContext('2d'), gr = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
      gr.addColorStop(0, `rgba(${rgb},1)`); gr.addColorStop(mid, `rgba(${rgb},.45)`); gr.addColorStop(1, `rgba(${rgb},0)`);
      g.fillStyle = gr; g.fillRect(0, 0, size, size);
      sprites.set(key, c);
      return c;
    }
    const newMote = anyY => ({ x: rand(0, W), y: anyY ? rand(0, H) : H + 10, r: rand(1.5, 4.2), vx: rand(-8, 8), vy: rand(-14, -4), ph: rand(0, 6.28), sp: rand(.5, 1.6) });
    const newSpore = anyY => ({ x: rand(0, W), y: anyY ? rand(0, H) : H + 10, r: rand(2.5, 6), vx: rand(-6, 6), vy: rand(-22, -8), ph: rand(0, 6.28), sp: rand(.4, 1.2) });
    function set(name, tags = []) {
      const t = new Set(tags);
      const nFog = t.has('fog') ? 16 : t.has('mist') ? 13 : t.has('dormant') ? 10 : 0;
      fogTint = t.has('dusk') ? '215,180,200' : t.has('dormant') ? '175,205,185' : '215,220,230';
      fog = Array.from({ length: nFog }, () => ({ x: rand(-400, W + 400), y: rand(H * .3, H * 1.05), r: rand(280, 620), a: rand(.05, .12), vx: rand(8, 28) * (Math.random() < .5 ? -1 : 1) }));
      moteTint = t.has('warm') || t.has('dawn') || t.has('dusk') ? '255,205,140' : '200,215,255';
      motes = Array.from({ length: !name ? 0 : t.has('warm') ? 70 : t.has('dawn') ? 60 : t.has('night') ? 24 : 34 }, () => newMote(true));
      spores = Array.from({ length: t.has('dormant') ? 55 : 0 }, () => newSpore(true));
      dust = []; siege = t.has('siege'); thudT = rand(3, 6);
    }
    function frame(dt, time) {
      cx.clearRect(0, 0, W, H);
      const fs = soft(fogTint, 256, .5);
      for (const f of fog) {
        f.x += f.vx * dt;
        if (f.x - f.r > W + 200) f.x = -f.r - 200;
        if (f.x + f.r < -200) f.x = W + f.r + 200;
        cx.globalAlpha = f.a;
        cx.drawImage(fs, f.x - f.r, f.y - f.r * .6, f.r * 2, f.r * 1.2);
      }
      cx.globalCompositeOperation = 'lighter';
      const ms = soft(moteTint, 32);
      for (const m of motes) {
        m.x += (m.vx + Math.sin(time * m.sp + m.ph) * 10) * dt; m.y += m.vy * dt;
        if (m.y < -10) Object.assign(m, newMote(false));
        cx.globalAlpha = .35 + .35 * Math.sin(time * m.sp * 2 + m.ph);
        cx.drawImage(ms, m.x - m.r * 3, m.y - m.r * 3, m.r * 6, m.r * 6);
      }
      const ss = soft('140,255,170', 32);
      for (const s of spores) {
        s.x += (s.vx + Math.sin(time * s.sp + s.ph) * 14) * dt; s.y += s.vy * dt;
        if (s.y < -10) Object.assign(s, newSpore(false));
        cx.globalAlpha = .4 + .4 * Math.sin(time * s.sp * 1.7 + s.ph);
        cx.drawImage(ss, s.x - s.r * 3, s.y - s.r * 3, s.r * 6, s.r * 6);
      }
      cx.globalCompositeOperation = 'source-over';
      if (siege) {   // 外面有东西在撞门：隔几秒一震，房梁落灰；偶尔混进 sfx.yaml 里标了 ambient: siege 的音效
        thudT -= dt;
        if (thudT <= 0) {
          thudT = rand(5.5, 9);
          if (!S.title && !/shake|dash/.test(world.className)) shake('thud');
          if (!S.title) {
            sfx('door_bang', rand(.7, 1));
            if (AMBIENT.length && Math.random() < .5) { const name = pick(AMBIENT); setTimeout(() => sfx(name, .5), 600); }
          }
          for (let i = 0; i < 40; i++) dust.push({ x: rand(0, W), y: rand(-40, H * .2), vy: rand(60, 160), vx: rand(-10, 10), life: rand(1.5, 3), r: rand(1, 2.4) });
        }
        cx.fillStyle = 'rgb(200,190,170)';
        dust = dust.filter(d => (d.life -= dt) > 0);
        for (const d of dust) { d.x += d.vx * dt; d.y += d.vy * dt; cx.globalAlpha = Math.min(1, d.life) * .7; cx.fillRect(d.x, d.y, d.r, d.r * 1.6); }
      }
      cx.globalAlpha = 1;
    }
    return { set, frame, soft };
  })();

  // ───────── 特效粒子（喷火、火焰、寒雾、冲刺线、碎木、迸溅） ─────────
  const fx = (() => {
    const cv = $('#fxc'), cx = cv.getContext('2d');
    const FIRE = ['255,244,200', '255,170,60', '235,80,25'];
    let ps = [], ems = [], dirty = false;
    const add = p => { p.max = p.life; ps.push(p); };
    function burst(x, y, o = {}) {
      const [s0, s1] = o.speed || [200, 600], [z0, z1] = o.size || [4, 10], col = (o.color || [255, 220, 150]).join(',');
      for (let i = 0, n = o.n || 24; i < n; i++) {
        const a = rand(0, Math.PI * 2), v = rand(s0, s1);
        add({ kind: 'glow', x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, drag: 2.6, g: o.g == null ? 120 : o.g, life: rand(.45, 1), size: rand(z0, z1), col });
      }
      add({ kind: 'ring', x, y, life: .5, size: 20, grow: 900, col });
    }
    const emit = (dur, fn) => ems.push({ dur, t: 0, fn });
    function fire(x, y, dir, dur) {
      emit(dur, dt => {
        for (let i = 0, n = Math.round(260 * dt); i < n; i++) {
          const a = (dir > 0 ? 0 : Math.PI) + rand(-.2, .2), v = rand(700, 1300);
          add({ kind: 'fire', x: x + rand(-4, 4), y: y + rand(-4, 4), vx: Math.cos(a) * v, vy: Math.sin(a) * v - 40, drag: 1.6, g: -60, life: rand(.45, .85), size: rand(6, 14), grow: 150 });
        }
      });
    }
    function flames(dur) {
      emit(dur, dt => {
        for (let i = 0, n = Math.round(160 * dt); i < n; i++)
          add({ kind: 'fire', x: rand(-50, W + 50), y: H + 30, vx: rand(-30, 30), vy: rand(-420, -220), drag: .6, g: -40, life: rand(.8, 1.5), size: rand(40, 90), grow: 30 });
      });
    }
    function mist(dur) {
      emit(dur, dt => {
        if (Math.random() < dt * 14) {
          const left = Math.random() < .5;
          add({ kind: 'mist', x: left ? -100 : W + 100, y: rand(H * .1, H * .9), vx: (left ? 1 : -1) * rand(80, 200), vy: rand(-20, 20), drag: .3, life: rand(2, 3.5), size: rand(160, 300), grow: 60, col: '200,240,255' });
        }
      });
    }
    function speedLines(dur) {
      emit(dur, dt => {
        for (let i = 0, n = Math.round(90 * dt); i < n; i++) {
          const a = rand(0, Math.PI * 2), r0 = rand(250, 500), v = rand(2200, 3400);
          add({ kind: 'line', x: W / 2 + Math.cos(a) * r0, y: H / 2 + Math.sin(a) * r0, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: rand(.18, .32), size: rand(1.5, 4), len: rand(120, 300) });
        }
      });
    }
    function debris() {
      for (let i = 0; i < 46; i++) {
        const a = rand(0, Math.PI * 2), v = rand(300, 1100);
        add({ kind: 'rect', x: W / 2 + rand(-120, 120), y: H * .45 + rand(-120, 120), vx: Math.cos(a) * v, vy: Math.sin(a) * v - 200, g: 900, drag: .4,
          life: rand(.8, 1.4), size: rand(10, 34), grow: 40, rot: rand(0, 6), vr: rand(-12, 12), col: pick(['92,62,38', '120,84,50', '70,48,30']) });
      }
      burst(W / 2, H * .45, { n: 30, color: [255, 230, 190], speed: [300, 900] });
    }
    function frame(dt) {
      ems = ems.filter(e => { e.t += dt; e.fn(dt, e.t); return e.t < e.dur; });
      if (!ps.length) { if (dirty) { cx.clearRect(0, 0, W, H); dirty = false; } return; }
      dirty = true;
      cx.clearRect(0, 0, W, H);
      ps = ps.filter(p => (p.life -= dt) > 0);
      for (const p of ps) {
        const k = Math.exp(-(p.drag || 0) * dt);
        p.vx *= k; p.vy = p.vy * k + (p.g || 0) * dt;
        p.x += p.vx * dt; p.y += p.vy * dt; p.size += (p.grow || 0) * dt;
        const f = p.life / p.max;
        if (p.kind === 'glow' || p.kind === 'fire' || p.kind === 'mist') {
          let col = p.col, a = f;
          if (p.kind === 'fire') { const age = 1 - f; col = age < .25 ? FIRE[0] : age < .55 ? FIRE[1] : FIRE[2]; a = Math.min(1, f * 1.6); }
          if (p.kind === 'mist') { a = Math.sin(f * Math.PI) * .22; cx.globalCompositeOperation = 'source-over'; }
          else cx.globalCompositeOperation = 'lighter';
          cx.globalAlpha = a;
          cx.drawImage(atmo.soft(col, 64), p.x - p.size, p.y - p.size, p.size * 2, p.size * 2);
        } else if (p.kind === 'ring') {
          cx.globalCompositeOperation = 'lighter'; cx.globalAlpha = f;
          cx.strokeStyle = `rgb(${p.col})`; cx.lineWidth = 4 * f + 1;
          cx.beginPath(); cx.arc(p.x, p.y, p.size, 0, Math.PI * 2); cx.stroke();
        } else if (p.kind === 'line') {
          const sp = Math.hypot(p.vx, p.vy) || 1;
          cx.globalCompositeOperation = 'lighter'; cx.globalAlpha = f * .8;
          cx.strokeStyle = '#fff'; cx.lineWidth = p.size;
          cx.beginPath(); cx.moveTo(p.x, p.y); cx.lineTo(p.x - p.vx / sp * p.len, p.y - p.vy / sp * p.len); cx.stroke();
        } else if (p.kind === 'rect') {
          p.rot += p.vr * dt;
          cx.globalCompositeOperation = 'source-over'; cx.globalAlpha = Math.min(1, f * 2);
          cx.fillStyle = `rgb(${p.col})`;
          cx.save(); cx.translate(p.x, p.y); cx.rotate(p.rot); cx.fillRect(-p.size / 2, -p.size / 5, p.size, p.size / 2.5); cx.restore();
        }
      }
      cx.globalAlpha = 1; cx.globalCompositeOperation = 'source-over';
    }
    const clear = () => { ps = []; ems = []; };
    return { burst, fire, flames, mist, speedLines, debris, frame, clear };
  })();

  // ───────── 幕名、章节卡 ─────────
  async function doScene(title) {
    const [a, b] = title.split(/[\s　]+/);
    sceneEl.className = '';
    sceneEl.innerHTML = `<div class="a">${esc(a)}</div><div class="line"></div><div class="b">${esc(b || '')}</div>`;
    reflow(sceneEl);
    sceneEl.className = 'on';
    clearTimeout(sceneEl._t);
    sceneEl._t = setTimeout(() => { sceneEl.className = 'on fade'; }, 4200);
    castClear(); hideChat();
    sfx('scene');
    await W_(500);
  }
  function resetChapter() {
    castClear(true); remembered.clear(); hideCG(); coldOff();
    S.combat = null; updateCombat();
    world.classList.remove('combat', 'ended', 'siege');
    bgLayer.innerHTML = ''; bgNow = { name: null, tags: [] }; atmo.set(null, []);
    hud.innerHTML = ''; box.className = 'empty'; hideChat(true);
  }
  function resetWorld() {
    resetChapter(); fx.clear();
    sceneEl.className = ''; card.className = ''; card.innerHTML = '';
    creditsEl.className = ''; creditsEl.innerHTML = '';
  }
  const chapterName = full => (full || '').split(/[\s　]+/).filter(Boolean);
  const spaced = s => L === 'zh' ? [...s].join(' ') : s;

  // ───────── 战斗 HUD ─────────
  function updateCombat() { combatEl.textContent = S.combat ? T.combat + S.combat.round : ''; combatEl.classList.toggle('on', !!S.combat); }
  async function showBanner(big, small, cls, ms) {
    const b = make('div', 'banner ' + (cls || ''), `<b>${esc(big)}</b><small>${esc(small)}</small>`);
    hud.appendChild(b);
    try { await W_(ms); } finally { b.classList.add('out'); setTimeout(() => b.remove(), 500); }
  }
  const D20 = '<svg viewBox="0 0 200 200"><polygon class="face" points="100,8 182,54 182,146 100,192 18,146 18,54" fill="url(#dieDark)" stroke="#f6e2a8" stroke-width="3" stroke-linejoin="round"/>'
    + '<g fill="none" stroke="rgba(246,226,168,.55)" stroke-width="2" stroke-linejoin="round"><polygon points="100,46 152,136 48,136"/>'
    + '<path d="M100,8 100,46 M182,54 100,46 M18,54 100,46 M182,54 152,136 M182,146 152,136 M100,192 152,136 M100,192 48,136 M18,146 48,136 M18,54 48,136"/></g></svg>';
  const DIE = R.die ?? 20;
  const outcome = res => res === 'fumble' ? 'fumble' : res === 'failure' || res === 'miss' ? 'bad' : 'good';
  async function doDice(batch) {
    const panel = make('div', 'dice-panel');
    const cols = batch.map(s => {
      const [who, skill, val, res] = s.args;
      const id = charOf(who), c = id ? R.chars[id] : {};
      const col = make('div', 'die-col rolling',
        `<div class="die-who">${c.avatar ? `<img src="${c.avatar}" alt="">` : ''}<b>${esc(nameOf(who))}</b></div><div class="die-skill">${esc(skill)}</div>`
        + `<div class="d20">${D20}<div class="ring"></div><div class="num">?</div></div><div class="die-nat"></div><div class="die-res">${esc(T.results[res] || res)}</div>`);
      col.style.setProperty('--c', c.color || '#888');
      panel.appendChild(col);
      return { col, num: col.querySelector('.num'), val: +val, res, id };
    });
    hud.appendChild(panel);
    requestAnimationFrame(() => panel.classList.add('on'));
    sfx('dice_roll');
    if (batch.length > 1) setTimeout(() => sfx('dice_roll', .6), 90);
    S.lastSkill = batch.length === 1 ? batch[0].args[1] || '' : '';
    if (batch.length === 1 && cols[0].id && !charsEl.classList.contains('hide')) {   // 单人掷骰：掷骰的人上台并点亮
      const c = castFind(cols[0].id) || castAdd(cols[0].id);
      if (c) { c.last = ++tick; setSpeaker(cols[0].id); }
    }
    const iv = setInterval(() => cols.forEach(c => { if (c.col.classList.contains('rolling')) c.num.textContent = 1 + Math.floor(Math.random() * (DIE || 20)); }), 60);
    try {
      await W_(800);
      for (const c of cols) {
        const o = outcome(c.res), crit = c.res === 'critical' || (DIE === 20 && c.val === 20);
        c.col.classList.remove('rolling');
        c.num.textContent = c.val;
        c.col.classList.add('landed', o);
        if (crit) c.col.classList.add('crit');
        if (DIE === 20 && c.val === 20) c.col.querySelector('.die-nat').textContent = 'NATURAL 20';
        if (DIE === 20 && c.val === 1) c.col.querySelector('.die-nat').textContent = 'NATURAL 1';
        const p = stagePoint(c.col.querySelector('.d20'));
        fx.burst(p.x, p.y, { n: crit ? 70 : 28, color: o === 'fumble' ? [255, 70, 50] : o === 'bad' ? [160, 180, 210] : [255, 215, 120], speed: [180, crit ? 900 : 520] });
        if (o === 'fumble' || crit) shake();
        sfx(crit ? 'dice_crit' : o === 'fumble' ? 'dice_fumble' : o === 'bad' ? 'dice_bad' : 'dice_good', cols.length > 1 ? .7 : 1);
        if (c.res === 'miss') sfx('miss');
        if (cols.length > 1) await W_(200);
      }
      await W_(1100);
    } finally {
      clearInterval(iv);
      panel.classList.add('out');
      setTimeout(() => panel.remove(), 500);
    }
  }

  // ───────── 舞台指令 ─────────
  // 喷火从谁嘴里出：最近说话的人、再是台上任何一个写了 mouth 的角色
  function mouthPoint() {
    if (charsEl.classList.contains('hide')) return null;
    const c = [castFind(S.speaker), ...cast].find(x => x && R.chars[x.id].mouth);
    return c ? spritePoint(c, R.chars[c.id].mouth) : null;
  }
  const EFFECTS = {
    async shake() { shake(); sfx('rumble'); await W_(450); },
    async flash() { flash('#fff', .9); sfx('flash'); await W_(500); },
    async dash() { shake('dash'); fx.speedLines(.8); sfx('dash'); await W_(700); },
    async 'breath-fire'() {
      const p = mouthPoint() || { x: 420, y: 300 };
      const dir = p.x < W / 2 ? 1 : -1;
      fx.fire(p.x + dir * 12, p.y, dir, 1.4);
      flash('rgba(255,140,40,.6)', .9, .7); shake();
      sfx('fire_breath');
      await W_(1300);
    },
    async flames() { fx.flames(2.8); flash('rgba(255,120,30,.45)', 1.6, .6); sfx('flames'); await W_(1500); },
    async chill() { coldOn(); fx.mist(3); sfx('ghost'); await W_(1200); },
    async 'dawn-light'() { flash('rgba(255,236,190,.85)', 2.2, .85); sfx('dawn'); await W_(1300); },
    async 'door-break'() { shake('shake-big'); flash('rgba(255,255,255,.7)', .5, .8); fx.debris(); sfx('door_break'); await W_(1000); },
  };
  const hitSound = skill => (R.hit_sounds.find(([, re]) => new RegExp(re, 'i').test(skill)) || ['hit_heavy'])[0];
  const D = {
    async chapter([full]) {
      const [num, ...rest] = chapterName(full);
      const name = rest.join(' ');
      S.chapterTitle = [num, name].filter(Boolean).join(' · ');
      card.innerHTML = `<div class="cc-num">${esc(num)}</div><div class="cc-lines"><i></i><em></em><i></i></div>`
        + `<div class="cc-name">${[...name].map((c, i) => `<span style="animation-delay:${(.5 + i * .14).toFixed(2)}s">${esc(c)}</span>`).join('')}</div>`
        + `<div class="cc-sub">${esc(spaced(R.title))} · TRPG REPLAY</div>`;
      card.className = 'on';
      sfx('chapter');
      await W_(700);
      resetChapter();
      await W_(2600);
      card.className = '';
      await W_(700);
    },
    async 'chapter-end'() {
      card.innerHTML = `<div class="cc-num">${esc(S.chapterTitle)}</div><div class="cc-lines"><i></i><em></em><i></i></div><div class="cc-end">${esc(T.end)}</div>`;
      card.className = 'on';
      sfx('chapter', .8); bgm(null, 2.5);
      await W_(700);
      castClear(true); hideCG(); box.className = 'empty'; hideChat(true);
      S.combat = null; updateCombat(); world.classList.remove('combat');
      world.classList.add('ended');
      await W_(2200);
      card.className = '';
      await W_(700);
    },
    async bg([name, ...tags]) {
      const moved = bgNow.name !== name;
      if (moved) castClear();
      coldOff(); world.classList.remove('ended');
      setBg(name, tags);
      await W_(moved ? 1100 : 500);
    },
    async enter([who, pos, state]) {
      const id = charOf(who);
      if (!id) return;
      if (state) remembered.set(id, state);
      const c = castAdd(id, { pos, state, pinned: true });
      if (c && state === 'ghost') {
        const p = headPoint(c);
        fx.burst(p.x, p.y + 200, { n: 40, color: [140, 255, 210], speed: [60, 300], g: -80, size: [6, 14] });
        if (!coldEl.classList.contains('on')) sfx('ghost', .8);
      }
      await W_(650);
    },
    async exit([who]) { const id = charOf(who) || who; remembered.delete(id); castRemove(id); coldOff(); await W_(400); },
    async fx([name]) { if (EFFECTS[name]) await EFFECTS[name](); },
    async sfx([name]) { sfx(name); await W_(350); },
    async bgm([cue]) { bgm(cue); },
    async cg([name]) { showCG(name); flash('#fff', 1.1, .9); sfx('cg'); await W_(1300); },
    async 'cg-end'() { hideCG(); await W_(700); },
    async 'battle-start'() {
      S.combat = { round: T.round1 };
      world.classList.add('combat');
      flash('rgba(200,20,10,.55)', .8, .8); shake();
      fx.burst(W / 2, H / 2, { n: 60, color: [255, 120, 60], speed: [400, 1400], g: 0 });
      sfx('battle_start');
      S.preBattle = music.cue; if (R.battle) bgm(R.battle, .5);
      await showBanner(T.battleStart, 'ENCOUNTER', '', 1700);
      updateCombat();
    },
    async round([name]) { if (S.combat) S.combat.round = name; updateCombat(); sfx('gong'); await showBanner(name, 'ROUND', 'round', 1100); },
    async 'battle-end'() {
      S.combat = null; updateCombat();
      world.classList.remove('combat');
      flash('rgba(255,240,200,.5)', 1, .6);
      sfx('battle_end'); if (R.battle) bgm(S.preBattle, 2.5);
      await showBanner(T.battleEnd, 'VICTORY', 'end', 1500);
    },
    async damage([target, amt]) {
      const id = charOf(target);
      let c = id && castFind(id);
      if (!c && id && !charsEl.classList.contains('hide') && spriteSrc(id)) {   // 挨打的人有立绘就先请上台
        c = castAdd(id);
        if (c) { setSpeaker(id); await W_(450); }
      }
      const p = c && !charsEl.classList.contains('hide') ? headPoint(c) : { x: W * .62, y: H * .36 };
      const d = make('div', 'dmg', `<div class="slash"></div><div class="num">-${esc(amt)}</div><div class="who">${esc(nameOf(target))}</div>`);
      d.style.left = p.x + 'px'; d.style.top = p.y + 'px';
      hud.appendChild(d);
      setTimeout(() => d.remove(), 1500);
      fx.burst(p.x, p.y, { n: 24 + 4 * (+amt || 1), color: [255, 110, 50], speed: [250, 900], size: [5, 12] });
      if (c) { c.node.classList.remove('hit'); reflow(c.node); c.node.classList.add('hit'); }
      flash('radial-gradient(ellipse at center, transparent 40%, rgba(200,0,0,.6))', .6);
      sfx(hitSound(S.lastSkill));     // 按前面那次掷骰的技能挑打击声；没有就是被怪物打
      S.lastSkill = '';
      await W_(900);
    },
    async contest([l, r, res = '']) {
      const parse = s => { const m = s.trim().split(/\s+/); return { who: m[0], stat: m[1] || '', val: +m[2] || 0 }; };
      const A = parse(l), B = parse(r);
      const side = (x, cls) => {
        const id = charOf(x.who), c = id ? R.chars[id] : {};
        return `<div class="vs-side ${cls}" style="--c:${c.color || '#888'}">${c.avatar ? `<img src="${c.avatar}" alt="">` : ''}`
          + `<div class="vs-info"><b>${esc(nameOf(x.who))}</b><span>${esc(x.stat)}</span><em>0</em></div></div>`;
      };
      const panel = make('div', 'vs-panel', side(A, 'l') + '<div class="vs-mid">VS</div>' + side(B, 'r') + `<div class="vs-res">${esc(res)}</div>`);
      hud.appendChild(panel);
      sfx('dash', .6);
      setTimeout(() => sfx('clash', .8), 400);
      const ems = panel.querySelectorAll('em'), t0 = performance.now();
      const count = () => {
        const k = Math.min(1, (performance.now() - t0 - 500) / 800);
        if (k > 0) { ems[0].textContent = Math.round(A.val * k); ems[1].textContent = Math.round(B.val * k); }
        if (k < 1 && panel.isConnected) requestAnimationFrame(count);
      };
      requestAnimationFrame(count);
      try {
        await W_(1300);
        ems[0].textContent = A.val; ems[1].textContent = B.val;
        sfx('hit_heavy', .8);
        const r0 = res.replace(/\s/g, ''), starts = x => r0.startsWith(x.who) || r0.startsWith(nameOf(x.who));
        const winA = starts(A), winB = !winA && starts(B);
        const sides = panel.querySelectorAll('.vs-side');
        if (winA || winB) {
          sides[winA ? 0 : 1].classList.add('win'); sides[winA ? 1 : 0].classList.add('lose');
          const p = stagePoint(sides[winA ? 0 : 1]);
          fx.burst(p.x, p.y, { n: 40, color: [255, 215, 120], speed: [200, 700] });
        }
        panel.classList.add('done'); shake();
        await W_(1300);
      } finally { panel.classList.add('out'); setTimeout(() => panel.remove(), 450); }
    },
    async item([name]) {
      const n = make('div', 'item-show', `<div class="halo"></div>${R.items[name] ? `<img src="${R.items[name]}" alt="">` : ''}<div class="iname"><small>ITEM</small>${esc(name)}</div>`);
      hud.appendChild(n);
      fx.burst(W / 2, H * .43, { n: 50, color: [255, 220, 150], speed: [100, 500], g: -40 });
      sfx('item');
      try { await W_(2000); } finally { n.classList.add('out'); setTimeout(() => n.remove(), 520); }
    },
    async credits() {
      hideChat(); box.className = 'empty';
      const C = R.credits;
      const p = ([name, sub]) => `<div class="cr-p">${esc(name)}${sub ? `<small>${esc(sub)}</small>` : ''}</div>`;
      const bg = C.bg && R.bg[C.bg];
      creditsEl.innerHTML = (bg ? `<div class="bgimg" style="--img:url('${bg}')"></div>` : '') + '<div class="roll">'
        + `<div class="cr-title">${esc(R.title)}</div><div class="cr-sub">${esc(R.subtitle ? R.subtitle + ' · ' : '')}TRPG REPLAY</div>`
        + C.sections.map(s => `<div class="cr-h">${esc(spaced(s.h))}</div>` + s.items.map(p).join('')).join('')
        + `<div class="cr-end">${esc(C.end)}</div></div>`;
      creditsEl.className = 'on';
      const roll = creditsEl.querySelector('.roll');           // 滚动时长跟着内容走：每秒约 75 像素，18 到 60 秒
      const dur = Math.max(18, Math.min(60, (roll.offsetHeight + H) / 75));
      roll.style.setProperty('--dur', dur.toFixed(1) + 's');
      await firm(dur * 1000 + 2000);
      bgm(null, 4);
      card.innerHTML = ''; card.className = 'on';      // 收尾黑场
      await firm(REC ? 4200 : 1500);
      creditsEl.className = '';
    },
  };

  // ───────── 主循环 ─────────
  async function run(g) {
    try {
      while (g === S.gen && S.pc < STEPS.length && !(REC && CHAPTER != null && S.pc >= CH_START[CHAPTER + 1])) {
        const s = STEPS[S.pc++];
        if (isText(s)) { showText(s); await waitAdvance(); stopVoice(); }
        else if (s.k === 'scene') await doScene(s.title);
        else if (s.name === 'roll') {
          const batch = [s];
          while (S.pc < STEPS.length && STEPS[S.pc].name === 'roll' && batch.length < 4) batch.push(STEPS[S.pc++]);
          await doDice(batch);
        } else if (D[s.name]) await D[s.name](s.args || []);
        else console.warn('unknown direction', s.name, s.args);
      }
    } catch (e) {
      if (e === ABORT) return;
      throw e;
    }
    if (g !== S.gen) return;
    if (REC) { log({ type: 'end' }); RECLOG.done = true; return; }
    showTitle();
  }
  function abortRun() {
    S.gen++;
    clearTimeout(typeTimer); clearTimeout(autoTimer);
    stopVoice();
    const f = advanceFn; advanceFn = null;
    if (f) f();
    hurry();
    S.typing = false; cur = null;
  }
  // 从章节开头静默重放到第 to 步之前，恢复背景、立绘、CG、战斗状态
  function fastForward(from, to) {
    let cue = null, pre = null;
    for (let i = from; i < to; i++) {
      const s = STEPS[i], a = s.args || [];
      if (isText(s)) { addLog(i, s); if (s.k === 'line') stageSpeak(s, true); continue; }
      if (s.k === 'scene') { castClear(true); continue; }
      const id = charOf(a[0]);
      switch (s.name) {
        case 'chapter': S.chapterTitle = chapterName(a[0]).join(' · '); cue = null; break;
        case 'bgm': cue = a[0] || null; break;
        case 'bg': if (bgNow.name !== a[0]) castClear(true); coldOff(); world.classList.remove('ended'); setBg(a[0], a.slice(1), true); break;
        case 'enter': if (id) { if (a[2]) remembered.set(id, a[2]); castAdd(id, { pos: a[1], state: a[2], pinned: true, instant: true }); } break;
        case 'exit': remembered.delete(id || a[0]); castRemove(id || a[0], true); coldOff(); break;
        case 'cg': showCG(a[0]); break;
        case 'cg-end': hideCG(); break;
        case 'battle-start': S.combat = { round: T.round1 }; world.classList.add('combat'); if (R.battle) { pre = cue; cue = R.battle; } break;
        case 'round': if (S.combat) S.combat.round = a[0]; break;
        case 'battle-end': S.combat = null; world.classList.remove('combat'); if (R.battle) cue = pre; break;
        case 'chapter-end': castClear(true); world.classList.add('ended'); cue = null; break;
        case 'fx': if (a[0] === 'chill') coldOn(); break;
        case 'damage': if (id && !castFind(id) && !charsEl.classList.contains('hide') && spriteSrc(id)) castAdd(id, { instant: true }); break;
      }
    }
    setSpeaker(null);
    updateCombat();
    S.preBattle = pre;
    bgm(cue, 1.2);
  }
  function startAt(i) {
    abortRun(); resetWorld(); bgm(null, .6);
    log({ type: 'start', step: i });
    logItems.length = 0;
    S.title = false;
    titleEl.classList.remove('on');
    ui.classList.remove('off', 'hidden');
    fastForward(CH_START[STEPS[i].ci], i);
    S.pc = i;
    run(S.gen);
  }
  function showTitle() {
    abortRun(); resetWorld();
    S.title = true;
    closeLog();
    ui.classList.add('off');
    if (REC) return;                       // 渲染模式不显示标题画面，载入完直接开始
    const ts = R.title_screen || {};
    if (ts.bg) setBg(ts.bg, ts.variants || [], true);
    bgm(ts.bgm, 1.5);
    titleEl.querySelector('[data-go="continue"]').hidden = saved() == null;
    titleEl.classList.add('on');
  }

  // ───────── 进度、存档、记录 ─────────
  function progress() {
    const ci = STEPS[Math.max(0, S.pc - 1)].ci, a = CH_START[ci], b = CH_START[ci + 1];
    progEl.style.width = ((S.pc - a) / (b - a) * 100).toFixed(2) + '%';
  }
  const SAVE_KEY = 'rlyeh.' + (R.id || 'replay') + '.pc';
  function save() { try { localStorage.setItem(SAVE_KEY, String(S.pc - 1)); } catch (e) { /* 存不了就算了 */ } }
  function saved() {
    try { const v = parseInt(localStorage.getItem(SAVE_KEY), 10); return Number.isFinite(v) && v > 0 && v < STEPS.length ? v : null; }
    catch (e) { return null; }
  }
  const logItems = [];
  function addLog(i, s) { if (logItems.length && logItems[logItems.length - 1].i === i) return; logItems.push({ i, s }); if (logItems.length > 500) logItems.shift(); }
  let logAudio = null;
  function logRow({ i, s }) {
    let name, color, av, sub = '';
    if (s.k === 'nar') { name = T.narrator; color = '#c9b98f'; }
    else if (s.k === 'ooc') { const p = playerInfo(s.who); name = s.who; color = p.color; av = p.avatar; sub = T.ooc + (p.char ? ' · ' + p.char : ''); }
    else { const id = charOf(s.who), c = id ? R.chars[id] : {}; name = id ? c.name : s.who; color = c.color; av = c.avatar; sub = c.player ? 'PL · ' + c.player : ''; }
    const row = make('div', 'log-row ' + s.k,
      `<div class="av${av ? '' : ' none'}"></div><div><div class="nm">${esc(name)}<small>${esc(sub)}</small>`
      + `${s.voice ? `<button data-v title="${esc(T.replay)}">▶</button>` : ''}<button data-j title="${esc(T.jump)}">↺</button></div><div class="tx">${renderRich(s.rich)}</div></div>`);
    row.style.setProperty('--c', color || '#888');
    if (av) row.querySelector('.av').style.backgroundImage = `url("${av}")`;
    const vb = row.querySelector('[data-v]');
    if (vb) vb.onclick = e => { e.stopPropagation(); if (logAudio) logAudio.pause(); logAudio = new Audio(s.voice); logAudio.volume = S.muted ? 0 : 1; logAudio.play(); };
    row.querySelector('[data-j]').onclick = e => { e.stopPropagation(); closeLog(); startAt(i); };
    return row;
  }
  function openLog() {
    if (S.title) return;
    logList.innerHTML = '';
    logItems.slice(-200).forEach(it => logList.appendChild(logRow(it)));
    logEl.classList.add('on');
    clearTimeout(autoTimer);
    requestAnimationFrame(() => { logList.scrollTop = logList.scrollHeight; });
  }
  function closeLog() {
    if (!logEl.classList.contains('on')) return;
    logEl.classList.remove('on');
    if (logAudio) { logAudio.pause(); logAudio = null; }
    ready();
  }

  // ───────── 操作 ─────────
  const btn = act => $(`#controls [data-act="${act}"]`);
  function chip() {
    chipEl.textContent = S.skip ? T.skipChip : S.auto ? T.autoChip : '';
    chipEl.classList.toggle('on', S.skip || S.auto);
  }
  function setAuto(v) { S.auto = v; btn('auto').classList.toggle('on', v); chip(); if (v) ready(); }
  function setSkip(v) {
    if (S.skip === v) return;
    S.skip = v; btn('skip').classList.toggle('on', v); chip();
    if (v) { stopVoice(); if (cur) cur.voiceDone = true; if (S.typing) finishTyping(); else ready(); hurry(); }
  }
  function toggleMute() { S.muted = !S.muted; btn('mute').classList.toggle('on', S.muted); if (curAudio) curAudio.volume = S.muted ? 0 : 1; }
  function toggleFull() { if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen().catch(() => {}); }
  function userNext() {
    if (S.title || logEl.classList.contains('on')) return;
    if (ui.classList.contains('hidden')) { ui.classList.remove('hidden'); return; }
    if (S.skip) { setSkip(false); return; }
    if (S.typing) { finishTyping(); return; }
    if (advanceFn) { stopVoice(); advance(); return; }
    hurry();
  }

  $('#controls').addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    e.stopPropagation();
    ({ auto: () => setAuto(!S.auto), skip: () => setSkip(!S.skip), log: openLog, hide: () => ui.classList.add('hidden'),
      mute: toggleMute, full: toggleFull, title: showTitle })[b.dataset.act]();
  });
  stage.addEventListener('click', e => { if (!e.target.closest('#controls, #log, #title')) userNext(); });
  stage.addEventListener('contextmenu', e => {
    e.preventDefault();
    if (logEl.classList.contains('on')) closeLog();
    else if (!S.title) ui.classList.toggle('hidden');
  });
  stage.addEventListener('wheel', e => { if (!S.title && e.deltaY < 0 && !logEl.classList.contains('on')) openLog(); }, { passive: true });
  logEl.addEventListener('wheel', e => {
    if (e.deltaY > 0 && logList.scrollTop + logList.clientHeight >= logList.scrollHeight - 2) closeLog();
  }, { passive: true });
  addEventListener('keydown', e => {
    if (e.key === 'f' || e.key === 'F') { toggleFull(); return; }
    if (S.title) return;
    if (e.key === 'Escape' && creditsEl.classList.contains('on')) { showTitle(); return; }
    if (logEl.classList.contains('on')) { if (['Escape', 'l', 'L'].includes(e.key)) closeLog(); return; }
    switch (e.key) {
      case ' ': case 'Enter': case 'ArrowRight': case 'PageDown': e.preventDefault(); userNext(); break;
      case 'a': case 'A': setAuto(!S.auto); break;
      case 's': case 'S': setSkip(!S.skip); break;
      case 'Control': if (!e.repeat) setSkip(true); break;
      case 'l': case 'L': case 'ArrowUp': openLog(); break;
      case 'h': case 'H': ui.classList.toggle('hidden'); break;
      case 'm': case 'M': toggleMute(); break;
      case 'r': case 'R': if (cur && cur.s.voice) playVoice(cur.s.voice, () => {}); break;
      case 'Escape': ui.classList.remove('hidden'); break;
    }
  });
  addEventListener('keyup', e => { if (e.key === 'Control') setSkip(false); });

  function hashStart() {
    const id = decodeURIComponent(location.hash.slice(1));
    const i = id ? STEPS.findIndex(s => s.id === id) : -1;
    return i >= 0 ? i : null;
  }
  titleEl.addEventListener('click', e => {
    if (music.el && music.el.paused) music.el.play().catch(() => {});   // 浏览器要先有一次点击才肯出声
    const b = e.target.closest('button');
    if (!b || b.disabled) return;
    e.stopPropagation();
    const go = b.dataset.go;
    if (go === 'start') startAt(hashStart() ?? 0);
    else if (go === 'continue') startAt(saved() ?? 0);
    else startAt(CH_START[+go]);
  });

  // ───────── 启动 ─────────
  document.body.insertAdjacentHTML('afterbegin', '<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>'
    + '<linearGradient id="dieDark" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5e4220"/><stop offset="1" stop-color="#1b120a"/></linearGradient>'
    + '<linearGradient id="dieGrey" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3c4352"/><stop offset="1" stop-color="#11141b"/></linearGradient>'
    + '<linearGradient id="dieRed" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8f1d14"/><stop offset="1" stop-color="#2a0604"/></linearGradient>'
    + '<linearGradient id="dieGold" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff1b8"/><stop offset="1" stop-color="#c8901e"/></linearGradient>'
    + '</defs></svg>');
  $('.t-logo').innerHTML = [...R.title].map((c, i) => `<span style="animation-delay:${(.4 + i * .18).toFixed(2)}s">${esc(c)}</span>`).join('');
  $('.t-kicker').textContent = R.kicker || 'TRPG REPLAY';
  $('.t-sub span').textContent = R.subtitle || '';
  $('.t-sub').hidden = !R.subtitle;
  $('.t-foot').textContent = R.foot || '';
  const menuEl = $('.t-menu');
  R.chapters.forEach((ch, i) => { const b = make('button'); b.textContent = ch.label; b.dataset.go = String(i); menuEl.appendChild(b); });
  if (REC) document.body.classList.add('rec');
  setAuto(S.auto);

  let last = performance.now();
  function loop(now) {
    const dt = Math.min(.05, (now - last) / 1000);
    last = now;
    atmo.frame(dt, now / 1000);
    musicFrame(dt);
    fx.frame(dt);
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);

  showTitle();
  const menu = [...titleEl.querySelectorAll('.t-menu button')];
  menu.forEach(b => { b.disabled = true; });
  const urls = new Set();
  Object.values(R.chars).forEach(c => { Object.values(c.faces || {}).forEach(u => urls.add(u)); if (c.avatar) urls.add(c.avatar); });
  [R.bg, R.cg, R.items].forEach(t => Object.values(t).forEach(u => urls.add(u)));
  const loadBar = $('.t-load i'), loadText = $('.t-load span');
  let loaded = 0;
  Promise.all([...urls].map(u => new Promise(res => {
    const im = new Image();
    im.onload = im.onerror = () => { loaded++; loadBar.style.width = (loaded / urls.size * 100) + '%'; loadText.textContent = `${T.loading} ${loaded} / ${urls.size}`; res(); };
    im.src = u;
  }))).then(() => {
    $('.t-load').classList.add('done');
    menu.forEach(b => { b.disabled = false; });
    if (REC) window.__go = () => startAt(CHAPTER != null ? CH_START[CHAPTER] : hashStart() ?? 0);   // 渲染脚本准备好后再调用，免得开头被截掉
  });
})();
