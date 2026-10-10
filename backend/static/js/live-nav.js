/* تحديث حي لعدّادات الشريط الجانبي وتنبيه الرسائل الواردة (بلا إعادة تحميل الصفحة).
   - استعلام خفيف كل 5 ثوانٍ والتبويب ظاهر، و20 ثانية إن كان مخفيًا، وفورًا عند العودة إليه.
   - عند ازدياد الرسائل غير المقروءة: نبضة على العدّاد، وعنوان التبويب (N)، وتنبيه منبثق وصوت قصير.
   - انقطاع الاتصال يظهر بنقطة برتقالية، ويعود تلقائيًا. */
(function () {
    'use strict';
    var URL = '/live/badges/';
    var baseTitle = document.title.replace(/^\(\d+\)\s*/, '');
    var prev = null, lastMsgId = null, timer = null, failures = 0;

    function soundOn() { try { return localStorage.getItem('sb-sound') !== 'off'; } catch (e) { return true; } }

    function setDot(ok) {
        document.querySelectorAll('[data-live-dot]').forEach(function (el) {
            el.classList.toggle('is-off', !ok);
            el.title = ok ? 'متصل: التحديث مباشر' : 'انقطع الاتصال: تُعاد المحاولة تلقائيًا';
        });
    }

    function beep() {
        if (!soundOn()) return;
        try {
            var Ctx = window.AudioContext || window.webkitAudioContext;
            if (!Ctx) return;
            var ctx = new Ctx(), now = ctx.currentTime;
            [660, 880].forEach(function (f, i) {
                var o = ctx.createOscillator(), g = ctx.createGain();
                o.frequency.value = f; o.type = 'sine';
                g.gain.setValueAtTime(0.0001, now + i * 0.13);
                g.gain.exponentialRampToValueAtTime(0.12, now + i * 0.13 + 0.02);
                g.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.13 + 0.12);
                o.connect(g); g.connect(ctx.destination); o.start(now + i * 0.13); o.stop(now + i * 0.13 + 0.13);
            });
            setTimeout(function () { ctx.close(); }, 600);
        } catch (e) { /* المتصفح يمنع الصوت قبل أول تفاعل */ }
    }

    function toast(m) {
        var old = document.querySelector('.sb-toast'); if (old) old.remove();
        var a = document.createElement('a');
        a.className = 'sb-toast'; a.href = m.url;
        var s = document.createElement('strong'); s.textContent = 'رسالة جديدة · ' + m.name;
        var p = document.createElement('span'); p.textContent = m.preview;
        a.appendChild(s); a.appendChild(p); document.body.appendChild(a);
        setTimeout(function () { a.remove(); }, 7000);
    }

    function render(d) {
        var badges = d.badges || {};
        document.querySelectorAll('[data-badge]').forEach(function (el) {
            var b = badges[el.dataset.badge], n = b ? b.count : 0, old = prev ? ((prev[el.dataset.badge] || {}).count || 0) : n;
            el.hidden = !n;
            el.textContent = n > 99 ? '99+' : String(n);
            el.className = 'sb-badge sb-badge--' + (b ? b.tone : 'info');
            if (n > old) { el.classList.add('is-bumped'); }
        });
        document.querySelectorAll('[data-badge-group]').forEach(function (g) {      // مجموع العدّادات الفرعية على عنوان المجموعة
            var kids = g.closest('.sb-group').querySelectorAll('.sb-sub [data-badge]'), sum = 0, danger = false;
            kids.forEach(function (k) { if (!k.hidden) { sum += parseInt(k.textContent, 10) || 0; danger = danger || k.classList.contains('sb-badge--danger'); } });
            g.hidden = !sum;
            g.textContent = sum > 99 ? '99+' : String(sum);
            g.className = 'sb-badge sb-badge--' + (danger ? 'danger' : 'info');
        });
        var inbox = (badges.inbox || {}).count || 0;
        document.title = (inbox ? '(' + inbox + ') ' : '') + baseTitle;

        var m = d.inbox_latest;
        if (m) {
            if (lastMsgId !== null && m.id > lastMsgId && location.pathname.indexOf(m.url) !== 0) { toast(m); beep(); }
            lastMsgId = Math.max(lastMsgId || 0, m.id);
        } else if (lastMsgId === null) { lastMsgId = 0; }
        prev = badges;
    }

    function schedule() {
        clearTimeout(timer);
        var delay = document.hidden ? 20000 : 5000;
        if (failures) delay = Math.min(30000, delay * (1 + failures));      // تراجع تدريجي عند الأخطاء
        timer = setTimeout(tick, delay);
    }

    function tick() {
        fetch(URL, { credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } })
            .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
            .then(function (d) { failures = 0; setDot(true); render(d); })
            .catch(function () { failures += 1; setDot(false); })
            .then(schedule);
    }

    window.liveNav = {
        refresh: tick,
        toggleSound: function () {
            var on = !soundOn();
            try { localStorage.setItem('sb-sound', on ? 'on' : 'off'); } catch (e) {}
            document.querySelectorAll('[data-sound-toggle]').forEach(function (el) {
                el.setAttribute('aria-pressed', String(on)); el.classList.toggle('opacity-50', !on);
                el.title = on ? 'إيقاف صوت التنبيه' : 'تشغيل صوت التنبيه';
            });
            if (on) beep();
        },
    };

    document.addEventListener('visibilitychange', function () { if (!document.hidden) tick(); });
    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-sound-toggle]').forEach(function (el) {
            el.classList.toggle('opacity-50', !soundOn());
            el.title = soundOn() ? 'إيقاف صوت التنبيه' : 'تشغيل صوت التنبيه';
        });
        // القراءة الأولى لتحديد آخر رسالة معروفة دون تنبيه
        tick();
    });
})();
