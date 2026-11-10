/* Сайт студии «ГАРАЖ»: живая сцена, окна и форма заявки. Без библиотек. */
(function () {
  'use strict';

  var cfg = JSON.parse(document.getElementById('cfg').textContent);
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  document.documentElement.classList.add('js');

  /* ================= окна ================= */

  var backdrop = $('#backdrop');
  var openWinEl = null, lastFocus = null;

  function winFor(el) {
    return el.classList.contains('slot') ? $('.win', el) : el.closest('.win');
  }

  function openWin(targetId) {
    var target = document.getElementById(targetId);
    if (!target) return;
    var win = winFor(target);
    if (!win) return;
    if (openWinEl && openWinEl !== win) closeWin(true);
    if (!openWinEl) {
      lastFocus = document.activeElement;
      // место окна на странице остаётся занятым, чтобы она не прыгала
      win.parentNode.style.minHeight = win.parentNode.offsetHeight + 'px';
      win.classList.add('open');
      win.setAttribute('role', 'dialog');
      win.setAttribute('aria-modal', 'true');
      $('.win-x', win).hidden = false;
      backdrop.hidden = false;
      document.body.classList.add('modal');
      openWinEl = win;
    }
    $$('.hit', win).forEach(function (n) { n.classList.remove('hit'); });
    var body = $('.win-body', win);
    if (target.classList.contains('gear-item')) {
      target.classList.add('hit');
      body.scrollTop = Math.max(0, target.offsetTop - body.offsetTop - 12);
      target.focus({preventScroll: true});
    } else {
      body.scrollTop = 0;
      $('.win-x', win).focus({preventScroll: true});
    }
  }

  function closeWin(keepFocus) {
    var win = openWinEl;
    if (!win) return;
    win.classList.remove('open');
    win.removeAttribute('role');
    win.removeAttribute('aria-modal');
    win.parentNode.style.minHeight = '';
    $('.win-x', win).hidden = true;
    $$('.hit', win).forEach(function (n) { n.classList.remove('hit'); });
    backdrop.hidden = true;
    document.body.classList.remove('modal');
    openWinEl = null;
    if (!keepFocus && lastFocus && lastFocus.focus) lastFocus.focus({preventScroll: true});
  }

  document.addEventListener('click', function (e) {
    var opener = e.target.closest('[data-open]');
    if (opener) { e.preventDefault(); openWin(opener.getAttribute('data-open')); return; }
    if (e.target.closest('.win-x') || e.target === backdrop) closeWin();
  });

  document.addEventListener('keydown', function (e) {
    if (!openWinEl) return;
    if (e.key === 'Escape') { e.preventDefault(); closeWin(); return; }
    if (e.key !== 'Tab') return;
    // фокус не выходит из открытого окна
    var items = $$('a[href],button,input,select,textarea', openWinEl).filter(function (n) {
      return !n.disabled && n.tabIndex !== -1 && n.offsetParent !== null;
    });
    if (!items.length) return;
    var first = items[0], last = items[items.length - 1];
    if (!openWinEl.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
    else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  /* ================= сцена ================= */

  var room = $('#room'), inner = $('#room-inner'), img = $('#scene-img'), panHint = $('#pan-hint');
  var W = cfg.scene.width, H = cfg.scene.height, IDS = cfg.scene.ids;
  var spots = {};
  $$('.hs').forEach(function (a) { spots[a.getAttribute('data-obj')] = a; });
  var centered = false;

  function layout() {
    var style = getComputedStyle(room);
    var avail = room.clientWidth;
    if (!room.classList.contains('pan')) avail -= parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
    else avail -= 32;
    var vh = window.innerHeight, fit = avail / W, scale;
    if (fit >= 2.4) {
      // целый масштаб: пиксели остаются ровными; сцена целиком помещается в первый экран
      scale = Math.max(2, Math.floor(Math.min(fit, (vh - 230) / H)));
    } else {
      // телефон: комната крупнее экрана, её двигают пальцем
      scale = Math.max(2, Math.min(3, Math.floor(vh * 0.58 / H)));
    }
    inner.style.width = W * scale + 'px';
    var pan = W * scale > avail + 33;
    room.classList.toggle('pan', pan);
    panHint.hidden = !pan;
    if (pan && !centered) {
      // стартуем с рабочего стола: там экран с заявкой
      var box = cfg.scene.boxes.screen;
      room.scrollLeft = Math.max(0, (box[0] + box[2] / 2) * scale - room.clientWidth / 2);
      centered = true;
    }
  }
  layout();
  window.addEventListener('resize', layout);

  var canvas = document.createElement('canvas');
  canvas.width = W; canvas.height = H;
  canvas.className = 'scene';
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', img.alt);
  var ctx = canvas.getContext('2d', {willReadFrequently: true});
  var base = null, frame = null, idAt = null;
  var pixels = {}, outlines = {}, blinkPx = [], glowPx = [];
  var active = {}, hoverId = null, blinkOff = false, glowUp = false;

  function setActive(key, id) {
    if (active[key] === id) return;
    var old = active[key];
    active[key] = id;
    [old, id].forEach(function (n) {
      if (!n || !spots[n]) return;
      var on = Object.keys(active).some(function (k) { return active[k] === n; });
      spots[n].classList.toggle('on', on);
    });
    render();
  }

  function render() {
    if (!base) return;
    var d = frame.data, i, k, p;
    d.set(base.data);
    if (blinkOff) for (i = 0; i < blinkPx.length; i++) { p = blinkPx[i] * 4; d[p] *= 0.3; d[p + 1] *= 0.3; d[p + 2] *= 0.3; }
    if (glowUp) for (i = 0; i < glowPx.length; i++) { p = glowPx[i] * 4; d[p] += 16; d[p + 1] += 10; d[p + 2] += 3; }
    var lit = {};
    for (k in active) if (active[k]) lit[active[k]] = true;
    for (var id in lit) {
      var px = pixels[id], ol = outlines[id];
      if (!px) continue;
      for (i = 0; i < px.length; i++) { p = px[i] * 4; d[p] += 34; d[p + 1] += 27; d[p + 2] += 16; }
      for (i = 0; i < ol.length; i++) { p = ol[i] * 4; d[p] = 255; d[p + 1] = 179; d[p + 2] = 71; }
    }
    ctx.putImageData(frame, 0, 0);
  }

  function prepare(mapImg) {
    ctx.drawImage(img, 0, 0);
    base = ctx.getImageData(0, 0, W, H);
    frame = ctx.createImageData(W, H);
    var mc = document.createElement('canvas');
    mc.width = W; mc.height = H;
    var mctx = mc.getContext('2d');
    mctx.drawImage(mapImg, 0, 0);
    var m = mctx.getImageData(0, 0, W, H).data;
    idAt = new Uint8Array(W * H);
    var i, n;
    for (i = 0; i < W * H; i++) {
      n = Math.round(m[i * 4] / 20);
      idAt[i] = n;
      if (n) (pixels[IDS[n - 1]] || (pixels[IDS[n - 1]] = [])).push(i);
      if (m[i * 4 + 1] > 127) blinkPx.push(i);
      if (m[i * 4 + 2] > 127) glowPx.push(i);
    }
    // контур предмета: соседние пиксели, которые ему не принадлежат
    var seen = new Uint8Array(W * H);
    IDS.forEach(function (name, idx) {
      var px = pixels[name] || [], out = [], id = idx + 1;
      seen.fill(0);
      for (var j = 0; j < px.length; j++) {
        var x = px[j] % W, y = (px[j] / W) | 0;
        [[x - 1, y], [x + 1, y], [x, y - 1], [x, y + 1]].forEach(function (q) {
          if (q[0] < 0 || q[1] < 0 || q[0] >= W || q[1] >= H) return;
          var t = q[1] * W + q[0];
          if (idAt[t] !== id && !seen[t]) { seen[t] = 1; out.push(t); }
        });
      }
      outlines[name] = out;
    });
    img.replaceWith(canvas);
    render();
    wireScene();
  }

  function pick(e, radius) {
    var r = canvas.getBoundingClientRect();
    var x = Math.floor((e.clientX - r.left) / r.width * W), y = Math.floor((e.clientY - r.top) / r.height * H);
    var best = 0, bestD = 1e9;
    for (var dy = -radius; dy <= radius; dy++) for (var dx = -radius; dx <= radius; dx++) {
      var xx = x + dx, yy = y + dy;
      if (xx < 0 || yy < 0 || xx >= W || yy >= H) continue;
      var n = idAt[yy * W + xx], dist = dx * dx + dy * dy;
      if (n && dist < bestD) { best = n; bestD = dist; }
    }
    return best ? IDS[best - 1] : null;
  }

  function wireScene() {
    var lastPointer = 'mouse';
    canvas.addEventListener('pointerdown', function (e) { lastPointer = e.pointerType || 'mouse'; });
    canvas.addEventListener('pointermove', function (e) {
      if (e.pointerType === 'touch') return;
      hoverId = pick(e, 1);
      if (hoverId && !cfg.targets[hoverId]) hoverId = null;
      canvas.style.cursor = hoverId ? 'pointer' : '';
      setActive('hover', hoverId);
    });
    canvas.addEventListener('pointerleave', function () { hoverId = null; canvas.style.cursor = ''; setActive('hover', null); });
    canvas.addEventListener('click', function (e) {
      var id = pick(e, lastPointer === 'touch' ? 4 : 1);
      if (id && cfg.targets[id]) { setActive('hover', null); openWin(cfg.targets[id]); }
    });
    Object.keys(spots).forEach(function (id) {
      var a = spots[id];
      a.addEventListener('pointerenter', function (e) { if (e.pointerType !== 'touch') setActive('hover', id); });
      a.addEventListener('pointerleave', function () { setActive('hover', null); });
      a.addEventListener('focus', function () { setActive('focus', id); });
      a.addEventListener('blur', function () { setActive('focus', null); });
    });

    if (reduceMotion) return;
    // огонёк REC и свет лампы
    var tick = 0;
    setInterval(function () {
      if (document.hidden) return;
      tick++;
      blinkOff = tick % 3 === 2;
      glowUp = Math.random() < 0.5;
      render();
    }, 520);
    // при первом показе по очереди подсвечиваем всё, на что можно нажать
    var order = Object.keys(spots).sort(function (a, b) { return cfg.scene.boxes[a][0] - cfg.scene.boxes[b][0]; });
    var step = 0;
    setTimeout(function next() {
      if (openWinEl || hoverId) { setActive('intro', null); return; }
      setActive('intro', order[step] || null);
      if (step++ < order.length) setTimeout(next, 260);
    }, 700);
  }

  if (canvas.getContext && window.Uint8Array) {
    var mapImg = new Image();
    var ready = function () { if (img.complete && img.naturalWidth && mapImg.complete && mapImg.naturalWidth) prepare(mapImg); };
    mapImg.onload = ready;
    if (!img.complete) img.addEventListener('load', ready);
    mapImg.src = '/static/scene-map.png?v=' + cfg.v;
  }

  /* ================= адрес ================= */

  var copyBtn = $('#copy-address');
  if (copyBtn && navigator.clipboard) {
    copyBtn.hidden = false;
    copyBtn.addEventListener('click', function () {
      navigator.clipboard.writeText(copyBtn.getAttribute('data-text')).then(function () {
        var old = copyBtn.textContent;
        copyBtn.textContent = 'Скопировано';
        setTimeout(function () { copyBtn.textContent = old; }, 1600);
      });
    });
  }

  /* ================= форма заявки ================= */

  var form = $('#req'), done = $('#done');
  if (!form) return;
  form.hidden = false;
  var hoursSel = $('#f-hours'), daysBox = $('#days'), timesBox = $('#times'), estimate = $('#estimate'), errorBox = $('#form-error');
  var submitBtn = $('button[type=submit]', form);
  var chosenDate = null, chosenStart = null, daysToken = 0, slotsToken = 0;

  for (var h = 1; h <= cfg.maxHours; h++) {
    var o = document.createElement('option');
    o.value = h; o.textContent = h + ' ' + plural(h, 'час', 'часа', 'часов');
    if (h === 2) o.selected = true;
    hoursSel.appendChild(o);
  }

  function plural(n, one, few, many) {
    if (n % 10 === 1 && n % 100 !== 11) return one;
    if (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14)) return few;
    return many;
  }
  function pad(n) { return n < 10 ? '0' + n : '' + n; }
  function service() {
    var id = form.elements.service_id.value;
    return cfg.services.filter(function (s) { return s.id === id; })[0];
  }
  function message(box, text) { box.innerHTML = ''; var p = document.createElement('p'); p.className = 'dim'; p.textContent = text; box.appendChild(p); }
  function getJSON(url) {
    return fetch(url, {headers: {Accept: 'application/json'}}).then(function (r) {
      return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || 'Ошибка'); return j; });
    });
  }

  function syncKind() {
    var kind = service().kind;
    $$('[data-for]', form).forEach(function (g) { g.hidden = g.getAttribute('data-for') !== kind; });
    showError('');
    if (kind === 'booking' && !daysBox.querySelector('input')) loadDays();
    updateEstimate();
  }

  function updateEstimate() {
    var s = service(), n = +hoursSel.value;
    estimate.innerHTML = '';
    if (s.kind !== 'booking' || !s.price_per_hour) return;
    estimate.appendChild(document.createTextNode('Ориентировочно: '));
    var b = document.createElement('b');
    b.textContent = (s.price_per_hour * n).toLocaleString('ru-RU') + ' ₽';
    estimate.appendChild(b);
    if (chosenDate && chosenStart !== null) {
      estimate.appendChild(document.createTextNode(' · ' + pad(chosenStart) + ':00–' + pad(chosenStart + n) + ':00'));
    }
  }

  function loadDays() {
    var token = ++daysToken, hours = +hoursSel.value;
    getJSON('/api/days?hours=' + hours).then(function (data) {
      if (token !== daysToken) return;
      daysBox.innerHTML = '';
      var keep = false;
      data.days.forEach(function (d) {
        var label = document.createElement('label');
        label.className = 'day';
        var input = document.createElement('input');
        input.type = 'radio'; input.name = 'date'; input.value = d.date; input.disabled = !d.free;
        if (d.free && d.date === chosenDate) { input.checked = true; keep = true; }
        var span = document.createElement('span');
        span.innerHTML = '<small></small><b></b><small></small>';
        span.children[0].textContent = d.weekday;
        span.children[1].textContent = d.day;
        span.children[2].textContent = d.month;
        label.title = d.free ? '' : 'Свободного времени нет';
        label.appendChild(input); label.appendChild(span);
        daysBox.appendChild(label);
      });
      if (!data.days.some(function (d) { return d.free; })) message(daysBox, 'Свободных дней на столько часов пока нет. Попробуйте меньше часов.');
      if (keep) loadSlots(); else { chosenDate = null; chosenStart = null; message(timesBox, 'Сначала выберите день.'); updateEstimate(); }
    }).catch(function () {
      if (token === daysToken) message(daysBox, 'Не удалось загрузить дни. Обновите страницу.');
    });
  }

  function loadSlots() {
    var token = ++slotsToken, hours = +hoursSel.value, day = chosenDate;
    message(timesBox, 'Смотрим свободное время…');
    getJSON('/api/slots?date=' + day + '&hours=' + hours).then(function (data) {
      if (token !== slotsToken) return;
      timesBox.innerHTML = '';
      if (!data.starts.length) { chosenStart = null; message(timesBox, 'На этот день свободного времени уже нет.'); updateEstimate(); return; }
      if (data.starts.indexOf(chosenStart) === -1) chosenStart = null;
      data.starts.forEach(function (s) {
        var label = document.createElement('label');
        label.className = 'time';
        var input = document.createElement('input');
        input.type = 'radio'; input.name = 'start'; input.value = s; input.checked = s === chosenStart;
        var span = document.createElement('span');
        span.textContent = pad(s) + ':00–' + pad(s + hours) + ':00';
        label.appendChild(input); label.appendChild(span);
        timesBox.appendChild(label);
      });
      updateEstimate();
    }).catch(function () {
      if (token === slotsToken) message(timesBox, 'Не удалось загрузить время. Выберите день ещё раз.');
    });
  }

  function showError(text, field) {
    errorBox.textContent = text;
    $$('.bad', form).forEach(function (n) { n.classList.remove('bad'); });
    if (!text || !field) return;
    var el = form.elements[field];
    if (el && el.classList) { el.classList.add('bad'); el.focus(); }
    else if (field === 'date') daysBox.scrollIntoView({block: 'nearest'});
    else if (field === 'start') timesBox.scrollIntoView({block: 'nearest'});
  }

  form.addEventListener('change', function (e) {
    var t = e.target;
    if (t.name === 'service_id') syncKind();
    else if (t === hoursSel) { loadDays(); updateEstimate(); }
    else if (t.name === 'date') { chosenDate = t.value; chosenStart = null; loadSlots(); updateEstimate(); }
    else if (t.name === 'start') { chosenStart = +t.value; updateEstimate(); }
  });
  form.addEventListener('input', function (e) { if (e.target.classList.contains('bad')) showError(''); });

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var s = service(), f = form.elements;
    var data = {
      service_id: s.id, name: f.name.value.trim(), contact: f.contact.value.trim(),
      comment: f.comment.value.trim(), website: f.website.value,
    };
    if (s.kind === 'booking') {
      if (!chosenDate) return showError('Выберите день.', 'date');
      if (chosenStart === null) return showError('Выберите время.', 'start');
      data.hours = +hoursSel.value; data.date = chosenDate; data.start = chosenStart;
    } else if (s.kind === 'genre') {
      data.genre = f.genre.value.trim();
      if (!data.genre) return showError('Напишите жанр.', 'genre');
    } else {
      data.link = f.link.value.trim();
    }
    if (!data.name) return showError('Напишите, как к вам обращаться.', 'name');
    if (data.contact.length < 3) return showError('Оставьте Telegram или телефон, чтобы мы могли ответить.', 'contact');

    showError('');
    submitBtn.disabled = true;
    fetch('/api/requests', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)})
      .then(function (r) { return r.json().then(function (j) { return {ok: r.ok, status: r.status, body: j}; }); })
      .then(function (res) {
        submitBtn.disabled = false;
        if (!res.ok) {
          showError(res.body.error || 'Не удалось отправить заявку.', res.body.field);
          if (res.status === 409) { chosenStart = null; loadDays(); if (chosenDate) loadSlots(); }
          return;
        }
        $('#done-id').textContent = res.body.id;
        form.hidden = true; done.hidden = false; done.focus();
        chosenStart = null;
      })
      .catch(function () {
        submitBtn.disabled = false;
        showError('Нет связи с сервером. Проверьте интернет и попробуйте ещё раз.');
      });
  });

  $('#again').addEventListener('click', function () {
    done.hidden = true; form.hidden = false;
    form.elements.comment.value = '';
    if (service().kind === 'booking') loadDays();
    form.elements.service_id[0].focus();
  });

  syncKind();
})();
