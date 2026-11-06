/* Demo banner. Loaded by every page; it does nothing on a normal deployment (/api/demo/info answers {"enabled": false}).
   On the demo site it adds a slim notice at the very top so nobody mistakes the sample data for real records. */
(function () {
  'use strict';
  fetch('/api/demo/info').then(r => r.json()).then(d => {
    if (!d || !d.enabled || document.getElementById('demo-banner')) return;
    const mins = d.next_reset_in_minutes, when = mins >= 90 ? 'in about ' + Math.round(mins / 60) + ' hours' : mins > 1 ? 'in about ' + mins + ' minutes' : 'shortly';
    const bar = document.createElement('div');
    bar.id = 'demo-banner';
    bar.setAttribute('role', 'note');
    bar.style.cssText = 'background:#ffe9a8;color:#4a3500;font:600 13px/1.4 Inter,system-ui,sans-serif;padding:7px 14px;text-align:center;border-bottom:1px solid #e6c768;';
    bar.innerHTML = '<span style="background:#4a3500;color:#ffe9a8;border-radius:4px;padding:1px 7px;margin-right:8px;letter-spacing:.06em">DEMO</span>' +
      'Sample data only: every name and number is invented. It is reset automatically (next reset ' + when + ').' +
      (location.pathname === '/' ? '' : ' <a href="/" style="color:#4a3500;margin-left:8px">Demo accounts</a>');
    document.body.insertBefore(bar, document.body.firstChild);
  }).catch(() => { /* no demo endpoint: a normal deployment */ });
})();
