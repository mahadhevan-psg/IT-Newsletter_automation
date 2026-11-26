/* What the guided tours say, for each application. The engine is in tour.js.
   Every tour is role-aware: people only get steps for tabs they can actually open, and the welcome card tells each person
   what THEIR role is for. Wording is ours; the only user data that reaches the page is the name, escaped. */
(function () {
  'use strict';
  const { esc, waitFor } = TourUtil;
  // 'Dr. S. Venkatesan' -> 'Venkatesan' (skip the title and initials); 'Kavin M' -> 'Kavin'
  const firstName = n => { const t = String(n || '').replace(/^(Dr|Prof|Mr|Mrs|Ms)\.?\s+/i, '').split(/\s+/).filter(Boolean); return t.find(w => !/^[A-Za-z]\.?$/.test(w)) || t[0] || 'there'; };
  const role = (name, text) => `<div class="tour-role"><b>${name}</b><span>${text}</span></div>`;
  const find = (selector, re) => () => [...document.querySelectorAll(selector)].find(e => re.test(e.textContent));
  const card = selector => () => document.querySelector(selector)?.closest('.card');

  // ================================================================ staff portal (/portal/)
  // These rely on the portal's own globals: me, current, show(), isEditor(), hasClasses()
  function portal(me, token) {
    const has = r => me.roles.includes(r);
    const goTab = id => async () => { if (current !== id || id === 'mine') show(id); };

    const welcome = () => {
      const blocks = [];
      if (has('ADMIN')) blocks.push(role('Admin', 'You run the system: add faculty and give them roles, choose each class\'s tutor, edit the forms in the Form builder, upload placement sheets, and see every analytic.'));
      if (has('HOD')) blocks.push(role('Head of Department', 'You see every student, faculty member and chart, can explore all of the department\'s work by type, and open the Newsletter studio. You also <b>approve the entries</b> faculty submit (see <b>Review &amp; submissions</b>).'));
      if (has('PC')) blocks.push(role('Programme Coordinator', 'You coordinate your programme. Like all faculty you can see every record in the department; your view is read-only.'));
      if (has('TUTOR')) blocks.push(role('Class tutor', 'You look after your own class: add or remove students, and follow its achievements, participation and placements. <b>You approve your students\' placement details</b> (see <b>Review &amp; submissions</b>).'));
      blocks.push(role('Faculty', blocks.length
        ? 'You also have your own page of everything you have entered (see <b>My activities</b>).'
        : 'You can see and download all the department\'s records: records, placements and everyone\'s activities. Your own page (<b>My activities</b>) lists what you have entered.'));
      return [{
        welcome: true, title: `Welcome, ${esc(firstName(me.name))}!`,
        body: `<p>This is the <b>IT Department Portal</b>: students, classes, faculty work, placements and analytics in one place. Here is what <b>your role${blocks.length > 1 ? 's' : ''}</b> can do:</p>${blocks.join('')}
          ${me.must_change ? '<p><b>First:</b> you are using a temporary password. Please change it on the Account tab.</p>' : ''}
          <p>A short tour will show you around. Skip it now if you like; <b>Help</b> at the top replays it, or just one page.</p>`,
      }];
    };

    const profileSteps = (pre) => [
      { before: pre, target: '.p-head', title: 'A person\'s page', body: '<p>Everything this person has entered, in one place. For faculty: designation, roles and contact. For students: their class and class journey.</p>', place: 'bottom' },
      { target: '.p-tools', title: 'Narrow it down', body: '<p>Pick an <b>academic year</b>, <b>search</b> within the page, <b>expand all</b> the cards, or <b>print</b> it.</p>', place: 'bottom' },
      { target: '#view .kpis', title: 'At a glance', body: '<p>Counts of papers, patents, awards, events and students mentored for faculty; achievements, participations, research, offers and prize money for students.</p>' },
      { target: '.snav', optional: true, title: 'Jump to a section', body: '<p>Work is sorted by kind: papers, patents, awards, events, outreach, mentoring. Only sections that have something show up. Click a chip to scroll to it.</p>', place: 'bottom' },
      { target: 'details.act', optional: true, title: 'Every activity is a card', body: '<p>The badges show the person\'s <b>role</b> (Lead author, Convener, Team lead &hellip;), status and level. <b>Click a card</b> to open all its details and evidence links.</p>', place: 'bottom' },
    ];

    const S = [];                                                   // sections, in tab order, only the ones this person can open
    S.push({ id: 'basics', label: 'Menu and top bar', hint: 'Menu, Help, sign out', steps: () => [
      { target: '#nav-toggle', before: () => { setNav(false); window.scrollTo(0, 0); }, title: 'The menu button', body: '<p>This button opens the menu. A red number on it means entries are waiting under <b>Review &amp; submissions</b>.</p>', place: 'bottom' },
      { before: async () => { setNav(true); await TourUtil.sleep(260); }, target: '#tabs', title: 'Your menu', body: '<p>Each item is a part of the portal. <b>What you see depends on your role</b>, so you only get what you can use. We will visit them one by one.</p>', place: 'right' },
      { before: () => setNav(false), target: '.tour-help', title: 'Help', body: '<p>Replay this tour, or have just the page you are on explained.</p>', place: 'bottom' },
      { target: '#who', title: 'Who you are', body: '<p>Your name and role(s). If you can open the Newsletter studio, its button sits right here.</p>', place: 'bottom' },
      { target: '#logout', title: 'Sign out', body: '<p>Always sign out on a shared computer.</p>', place: 'bottom' },
    ] });
    S.push({ id: 'dash', label: 'Dashboard', hint: 'The department at a glance', steps: () => [
      { before: goTab('dash'), target: '#view .filters', title: 'Choose what to look at', body: `<p>Pick an <b>academic year</b>${me.all_access ? ', a <b>programme</b>' : ''} and a <b>class</b>.${me.all_access ? ' Programme and class narrow the two student cards; the other four always show the whole department.' : ' Every number below follows your choice.'}</p>` },
      { target: '#dash-cards', title: 'The six categories at a glance', body: '<p>Each card shows a total and the most important figures of one category. <b>Click a card</b> to see its details on the right.</p>', place: 'right' },
      { target: '#dash-detail', title: 'The details', body: '<p>Charts and lists for the card you chose; this panel scrolls on its own. Where you see a roll number or an employee ID, click it to open that person\'s page.</p>', place: 'left' },
    ] });
    if (!has('ADMIN')) S.push({ id: 'entry', label: 'Add entry', hint: 'Record what happened', steps: () => [
      { before: goTab('entry'), target: '#en-q', title: 'Say what happened', body: '<p>Type a word (hackathon, paper, MoU, award) or pick a tile below. There are no forms to hunt for: each tile opens the right entry.</p>', place: 'bottom' },
      { target: '#en-tiles', title: 'Tiles by kind of work', body: '<p>Student achievements, research, your own achievements, department highlights and industry or outreach. Choose the one that fits.</p>', place: 'top' },
      { target: '#en-composer', optional: true, title: 'Fill a few details', body: '<p>Only the essentials show first; <b>More details</b> opens the rest. Add students by roll number, pick faculty by name, and add photos straight from your phone. A draft saves itself.</p>', place: 'top' },
    ] });
    if (has('ADMIN')) S.push({ id: 'builder', label: 'Form builder', hint: 'Change what people are asked', steps: () => [
      { before: goTab('builder'), target: '.bd-forms', title: 'Choose a form', body: '<p>Each form has categories (kinds of entry) and fields (what is asked). Pick the form to change.</p>', place: 'bottom' },
      { target: '.bd-cats', title: 'Categories and sections', body: '<p>Add, rename, reorder or delete categories, and add newsletter sections. A new category starts with a title, a date and a description.</p>', place: 'right' },
      { target: '.bd-fields', title: 'Fields', body: '<p>Click a field to change its name, kind, choices or newsletter role. Retire a field to hide it from new entries while keeping old answers.</p>', place: 'top' },
      { target: '#bd-edit', title: 'Draft, then publish', body: '<p>Your changes stay in a draft. <b>Publish changes</b> makes them live for everyone and updates the newsletter. History lets you go back to an earlier version.</p>', place: 'left' },
    ] });
    S.push({ id: 'review', label: 'Review & submissions', hint: 'Check, edit and approve entries', steps: () => [
      { before: goTab('review'), target: '#rv-tabs', title: 'Where entries wait', body: `<p>${me.roles.includes('ADMIN') || me.roles.includes('HOD') ? 'Entries wait here until you decide. <b>Nothing is used in the application before it is approved.</b>' : me.tutor_class_ids.length ? 'The placement details of your students wait here for your approval.' : 'Entries sent back to you for correction appear here, and you can follow what you submitted.'}</p><p>The red number on the tab is how many need you.</p>`, place: 'bottom' },
      { target: '#rv-list', title: 'The queue', body: '<p>Click an entry to read it. An orange mark means something needs a look (a roll number that matches nobody, a missing link). Tick several and use <b>Approve selected</b>, or <b>Approve all clean</b> for those with no marks.</p>', place: 'right' },
      { target: '#rv-detail', optional: true, title: 'Read, then decide', body: '<p>Answers are listed as in the form, and the people the IDs belong to are shown, so mistakes stand out. Hover a value and click the pencil to fix it.</p>', place: 'left' },
      { target: '#rv-foot', optional: true, title: 'Four ways to decide', body: '<p><b>Approve</b> as it is. <b>Edit &amp; approve</b> to fix it first (both versions are kept). <b>Reject with reason</b> sends it back to a faculty member you choose, who corrects it and resubmits. <b>Reject without reason</b> sets it aside.</p>', place: 'top' },
    ] });
    if (hasClasses()) S.push({ id: 'students', label: 'Students', hint: 'Find, add and open students', steps: () => [
      { before: goTab('students'), target: '#view .filters', title: 'Find students', body: `<p>${document.getElementById('f-grp') ? 'Choose <b>both groups, G1 or G2</b>, then a class, a status, or search by roll number or name.' : 'Pick a class, a status, or search by roll number or name.'}</p>`, place: 'bottom' },
      { target: '#st-list', title: 'The student list', body: `<p><b>Click a roll number</b> to open that student\'s page: achievements, participations, research, events and placement.</p>${isEditor() ? '<p><b>Move</b> shifts a student to another class; <b>Remove</b> takes them out of the class (their records are kept).</p>' : '<p>This list is view-only for your role.</p>'}</p>`, place: 'top' },
      { target: '#add-st', optional: true, title: 'Add a student', body: '<p>Enter a roll number and name for a student who joins your class.</p>', place: 'bottom' },
      { target: card('#view .drop'), optional: true, title: 'Upload a class list', body: '<p>Download the template, fill <b>Roll No</b> and <b>Full Name</b>, upload. Existing roll numbers are updated, and a tutor\'s students go into the tutor\'s own class.</p>', place: 'top' },
    ] });
    if (has('ADMIN')) S.push({ id: 'classes', label: 'Classes', hint: 'Tutor and semester of each class', steps: () => [
      { before: goTab('classes'), target: '#view [data-c]', title: 'One card per class', body: '<p>A class is known by its <b>tutor and semester</b>. Two semesters make a year, so the year and class code follow the semester. Students stay with their class as it moves up: nobody is promoted one by one.</p>', place: 'bottom' },
      { target: '#view [data-c] .sem', optional: true, title: 'Move a class on', body: '<p>Set the <b>semester</b> and <b>academic year</b> here, then Save.</p>', place: 'bottom' },
      { target: '#view [data-c] .tutor', optional: true, title: 'Choose the tutor', body: '<p>Only the <b>Admin</b> changes a class\'s tutor.</p>', place: 'bottom' },
      { target: '#add-class', optional: true, title: 'Add a class', body: '<p>For a new batch. Choose the programme, group, starting semester and tutor.</p>', place: 'bottom' },
      { target: '#view .graduate', optional: true, title: 'When a class finishes', body: '<p>In its last semester you can <b>mark it graduated</b>: its students become Graduated and the class closes. All records are kept.</p>', place: 'top' },
    ] });
    if (has('ADMIN')) S.push({ id: 'uploads', label: 'Data upload', hint: 'Excel uploads for all six forms', steps: () => [
      { before: goTab('uploads'), target: () => document.querySelectorAll('#view > .card')[0], title: 'One card per form', body: '<p>Each of the six forms has a card: download its Excel template, fill it and upload it. The five faculty forms have a sheet per category and their rows are saved as approved (a wrong one can be revoked under <b>Review &amp; submissions</b>). In the <b>placement</b> card, a student already in the system is replaced by the rows for that year.</p>', place: 'bottom' },
      { target: card('#unmatched'), title: 'Roll numbers that matched nobody', body: '<p>If a roll number or employee ID on an entry matches nobody, it is listed here so you can fix the student list or the entry. Nothing is lost.</p>', place: 'top' },
    ] });
    if (me.all_access) S.push({ id: 'faculty', label: has('ADMIN') ? 'Faculty & roles' : 'Faculty', hint: 'Directory, activity counts, roles', steps: () => [
      { before: goTab('faculty'), target: () => document.getElementById('ff-q')?.closest('.filters'), title: 'Find faculty', body: '<p>Search, or filter by <b>designation, status, role</b>, or by what they have entered (research, achievements, events, outreach, mentoring).</p>', place: 'bottom' },
      { target: '#fac-list', title: 'The faculty table', body: `<p>The counts show how much each person has entered. <b>Click a name</b> or <b>Activities</b> to open their page.</p>${has('ADMIN') ? '<p>As Admin you can also set <b>Roles</b>, <b>Edit</b>, <b>Reset password</b> or <b>Relieve</b> someone.</p>' : ''}`, place: 'top' },
      { target: '#add-fac', optional: true, title: 'Add faculty', body: '<p>Creates the login and shows a <b>one-time temporary password</b>. Share it privately; they must change it at first sign-in.</p>', place: 'bottom' },
      { target: card('#view .drop'), optional: true, title: 'Upload faculty', body: '<p>Upload an Excel list: existing employee IDs are updated and new ones get temporary passwords (shown once).</p>', place: 'top' },
    ] });
    S.push({ id: 'records', label: 'Records', hint: 'Every approved entry, with filters and downloads', steps: () => [
      { before: goTab('records'), target: '#wk-bar', title: 'All forms, or one', body: '<p><b>All forms</b> lists every approved entry together. Each drop-down opens one form (or one of its categories) with its own filters, totals and download. <b>Placements</b> shows the offers and who opted in or out; a class tutor records and uploads their class there.</p>', place: 'bottom' },
      { target: '#rec-body .filters', title: 'Narrow it down', body: '<p>Under <b>All forms</b> filter by year, category, class, level, roll number, dates or words in the title. For one form, the filters are about that work: indexing and quartile for papers, level for awards, amounts and so on.</p>', place: 'bottom' },
      { target: '#s-out', optional: true, title: 'Open a record', body: '<p><b>Click a row</b> for everything that was entered: the people involved, every detail, and the documents.</p>', place: 'top' },
      { target: '#s-dl', optional: true, title: 'Download', body: '<p>Set the <b>dates</b>, <b>tick the columns</b> you want and download a file for Excel. Choosing one form first gives you a column for every field of that form.</p>', place: 'bottom' },
    ] });
    S.push({ id: 'mine', label: 'My activities', hint: 'Your own page', steps: () => profileSteps(goTab('mine')) });
    S.push({ id: 'account', label: 'Account', hint: 'Change your password', steps: () => [
      { before: goTab('account'), target: card('#pw-old'), title: 'Your password', body: '<p>Choose a new password of at least 8 characters. A temporary password from the Admin must be changed after your first sign-in.</p>', place: 'bottom' },
    ] });

    const sections = () => [...S, ...(current === 'profile' ? [{ id: 'profile', label: 'This page', hint: 'A person\'s page', steps: () => profileSteps(null) }] : [])];
    const kit = TourKit.mount({
      app: 'portal', host: document.getElementById('help-host'), me, token, welcome, sections,
      current: () => current,
      snapshot: () => { const t = current === 'profile' ? 'dash' : current; return () => show(t); },
    });
    kit.autoStart();
    return kit;
  }

  // ================================================================ student diary (/diary/)
  function diary(me, token) {
    const onHome = () => !/^#\/company\//.test(location.hash);
    const toHome = async () => { if (!onHome()) location.hash = ''; await waitFor('#co-q'); };
    const toCompany = async () => {
      if (onHome()) { await waitFor('.co'); const c = document.querySelector('.co'); if (c) c.click(); }
      await waitFor('#view > .back', 4000);
    };
    const welcome = () => [{
      welcome: true, title: `Hi ${esc(firstName(me.name))}!`,
      body: `<p>The <b>Placements Diary</b> shows where our seniors got placed over the last three years, what they earned and how they prepared.</p>
        ${role('Your privacy', 'Names, roll numbers and classes are <b>never shown</b>. Everything here is company-level or anonymous.')}
        ${role('How to use it', 'Search a company, open it, and read the package range and the interview and internship experiences students chose to share.')}
        ${me.must_change ? '<p><b>First:</b> your password is still your roll number. Please change it from the button at the top.</p>' : ''}
        <p>A quick tour takes under a minute. Skip it now; <b>Help</b> at the top replays it.</p>`,
    }];
    const sections = () => [
      { id: 'overview', label: 'Overview & search', hint: 'Totals and the company list', steps: () => [
        { before: toHome, target: () => document.querySelector('#view > .kpis'), title: 'The big picture', body: '<p>How many students were placed in the last three years, how many companies recruited, and the highest and average package.</p>', place: 'bottom' },
        { target: '#co-q', title: 'Search a company', body: '<p>Type part of a name and the list narrows as you type.</p>', place: 'bottom' },
        { target: '.co', optional: true, title: 'One card per company', body: '<p>Students placed (full-time), interns, and the highest and average package. The last line counts the experiences students shared. <b>Click a card</b> to open the company.</p>', place: 'bottom' },
      ] },
      { id: 'company', label: 'A company page', hint: 'Packages and experiences', steps: () => [
        { before: toCompany, target: () => document.querySelector('#view > .back'), optional: true, title: 'Back to all companies', body: '<p>Use this to return to the list.</p>', place: 'bottom' },
        { target: () => document.querySelector('#view > .card .kpis')?.closest('.card'), optional: true, title: 'The summary', body: '<p>Placed and interns over the last three years, with the <b>lowest, average and highest</b> package.</p>', place: 'bottom' },
        { target: () => document.querySelector('#view .grid-2'), optional: true, title: 'Year by year', body: '<p>How many were placed each year and the package range, plus the <b>roles offered</b> and the type of offers (full-time, intern, converted &hellip;).</p>', place: 'top' },
        { target: find('#view .card', /Interview experiences/), optional: true, title: 'Interview experiences', body: '<p>Shared anonymously by seniors: number of rounds, difficulty, questions asked and tips. Great for preparing.</p>', place: 'top' },
        { target: find('#view .card', /Internship experiences/), optional: true, title: 'Internship experiences', body: '<p>What the work was, the technologies used, what they learned and a rating.</p>', place: 'top' },
      ] },
      { id: 'account', label: 'Your account', hint: 'Password and sign out', steps: () => [
        { before: toHome, target: '#chpw', title: 'Change your password', body: '<p>Your first password is your roll number. Please change it.</p>', place: 'bottom' },
        { target: '#logout', title: 'Sign out', body: '<p>Always sign out on a shared computer.</p>', place: 'bottom' },
      ] },
    ];
    const kit = TourKit.mount({
      app: 'diary', host: document.getElementById('help-host'), me, token, welcome, sections,
      current: () => (onHome() ? 'overview' : 'company'),
      snapshot: () => { const h = location.hash; return () => { if (location.hash !== h) location.hash = h; }; },
    });
    kit.autoStart();
    return kit;
  }

  // ================================================================ newsletter studio (/newsletter/)
  function studio(me, token) {
    const goTab = id => async () => { if (!document.querySelector(`#main-tabs .tab.active[data-tab="${id}"]`)) await switchTab(id); };
    const btn = re => find('button', re);
    const welcome = () => [{
      welcome: true, title: `Welcome to the Newsletter Studio, ${esc(firstName(me.name))}!`,
      body: `<p>The studio turns the department's approved entries into the <b>IT Chronicles newsletter</b>.</p>
        ${role('Who uses it', 'Only the <b>Admin and the HoD</b>. Faculty enter their work in the portal; you choose which entries go in, design the layout and build the document.')}
        <p>The tour visits every tab. Skip it now; <b>Help</b> at the top replays it, or one tab.</p>`,
    }];
    const S = [
      { id: 'responses', label: 'Entries', hint: 'What goes into the newsletter', steps: () => [
        { before: goTab('responses'), target: '#tab-responses .toolbar', title: 'Straight from the database', body: '<p>These are the approved entries of the department database, read live: there is nothing to import. Filter them by status, section and dates.</p>', place: 'bottom' },
        { target: '#responses-list', title: 'Decide what goes in', body: '<p>Every entry is in the newsletter unless you <b>reject</b> it; you can approve it again, or mark it <b>featured</b>. To change what an entry says, or which fields feed the newsletter, use the portal (Review &amp; submissions and Form builder).</p>', place: 'top' },
      ] },
      { id: 'front', label: 'Front pages', hint: "HOD's desk, vision, editorial board", steps: () => [
        { before: goTab('front'), target: '.front-bar', title: 'Front pages', body: '<p>The pages that come before the sections: HOD\'s Desk, vision and mission, editorial board. Anything left empty is simply left out. <b>Save front pages</b> when done.</p>', place: 'bottom' },
        { target: '#front-form', title: 'Fill them in', body: '<p>Type the text and upload photos right here.</p>', place: 'top' },
      ] },
      { id: 'layout', label: 'Layout', hint: 'Design how entries look', steps: () => [
        { before: goTab('layout'), target: '.layout-bar', title: 'The layout bar', body: '<p>Choose a form to preview, a saved layout, name it, then <b>Save layout</b>. Preview hides the editing handles; Undo and Reset are here too.</p>', place: 'bottom' },
        { target: '.palette', title: 'Elements', body: '<p>Drag an element onto the page, or click to add it. Each one is linked to a column of the form.</p>', place: 'right' },
        { target: '#paper', title: 'The page', body: '<p>Arrange and resize elements. This is how one entry will look in the newsletter.</p>', place: 'left' },
        { target: '.inspector', title: 'Inspector', body: '<p>Fine-tune the selected element, and choose sample data to preview with.</p>', place: 'left' },
      ] },
      { id: 'publish', label: 'Publish', hint: 'Build the Word documents', steps: () => [
        { before: goTab('publish'), target: '#publish-sections', title: 'Choose sections', body: '<p>Tick the sections to include, and build each one as its own Word document if you want.</p>', place: 'right' },
        { target: '.publish-side', title: 'Master newsletter', body: '<p>Combines every ticked section, featured items first, into <b>one Word document</b>. Front pages are included if you wish.</p>', place: 'left' },
      ] },
    ];
    const kit = TourKit.mount({
      app: 'studio', host: document.getElementById('help-host'), me, token, welcome, sections: () => S,
      current: () => document.querySelector('#main-tabs .tab.active')?.dataset.tab,
      snapshot: () => { const t = document.querySelector('#main-tabs .tab.active')?.dataset.tab || 'responses'; return () => switchTab(t); },
    });
    kit.autoStart();
    return kit;
  }

  async function fetchMe(tokenKey) {
    const token = sessionStorage.getItem(tokenKey);
    if (!token) return null;
    try { const r = await fetch('/api/auth/me', { headers: { Authorization: 'Bearer ' + token } }); return r.ok ? { me: await r.json(), token } : null; } catch (e) { return null; }
  }
  window.Tours = { portal, diary, studio, fetchMe };
})();
