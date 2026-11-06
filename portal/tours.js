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

  // ================================================================ forms page (/homepage/)
  function home(me, token) {
    const formCard = re => find('.cards .card', re);
    const sections = () => [{
      id: 'forms', label: 'The forms page', hint: 'The six forms and the buttons', steps: () => [
        { target: 'h1', title: 'The Data Collection Forum', body: '<p>Every Google Form the department uses lives on this page, so nobody has to hunt for links.</p>', place: 'bottom' },
        { target: '.cards', title: 'Six forms', body: '<p>Pick the one that matches what you want to report. Each opens in <b>Google Forms in a new tab</b>, and what you submit flows into the department database, the portal and the newsletter.</p>', place: 'top', pad: 10 },
        { target: formCard(/Departmental/), title: 'Departmental Highlights', body: '<p>Workshops, conferences, lab upgrades, club activities and milestones. Choose the convener and the other faculty involved from the list.</p>' },
        { target: formCard(/Faculty Achievements/), title: 'Faculty Achievements', body: '<p>Awards, certifications, invited lectures, FDPs and professional roles. <b>Select your own name</b> from the list: that is what puts it on your page.</p>' },
        { target: formCard(/Research/), title: 'Research & Innovation', body: '<p>Papers, patents, funded projects, consultancy and innovations. List the authors by employee ID or roll number (<b>EXT</b> for people outside the department).</p>' },
        { target: formCard(/Student Achievements/), title: 'Student Achievements', body: '<p>Competitions, hackathons, projects and higher studies, or <b>participation only</b>. Enter students by roll number, one per line.</p>' },
        { target: formCard(/Industry/), title: 'Industry, Alumni & Outreach', body: '<p>Industry visits, expert talks, MoUs, alumni interactions and community outreach. You can add the students who attended.</p>' },
        { target: formCard(/Placement/), title: 'Student Placement Details', body: '<p>This one is <b>for students</b>: tutors share it so each student records their offers and interview experience. One response per offer.</p>' },
        { target: '.portal-btn', title: 'Go to portal', body: '<p>Opens the department portal: your own activity page, and (depending on your role) students, classes, placements and analytics.</p>', place: 'bottom' },
        { target: '#signout', title: 'Sign out', body: '<p>Small icon button. Use it when you finish, especially on a shared computer.</p>', place: 'bottom' },
        { target: find('.foot a', /Newsletter/), optional: true, title: 'Newsletter studio', body: '<p>Only the <b>Admin and the HoD</b> can open the newsletter studio, where approved responses become the newsletter.</p>', place: 'top' },
      ],
    }];
    const welcome = () => [{
      welcome: true, title: `Welcome, ${esc(firstName(me.name))}!`,
      body: `<p>This is the <b>IT Department Data Collection Forum</b>: the starting point for faculty. From here you open the forms and move on to the portal.</p>
        ${role('Your job', 'Submit your work (papers, awards, events, students you mentored) through the right form. It appears on your page in the portal automatically.')}
        <p>A short tour takes about a minute. You can skip it now and replay it any time from <b>Help</b>.</p>`,
    }];
    const kit = TourKit.mount({ app: 'home', host: document.getElementById('help-host'), iconOnly: true, me, token, welcome, sections });
    kit.autoStart();
    return kit;
  }

  // ================================================================ staff portal (/portal/)
  // These rely on the portal's own globals: me, current, show(), isEditor(), hasClasses()
  function portal(me, token) {
    const has = r => me.roles.includes(r);
    const goTab = id => async () => { if (current !== id || id === 'mine') show(id); };

    const welcome = () => {
      const blocks = [];
      if (has('ADMIN')) blocks.push(role('Admin', 'You run the system: add faculty and give them roles, choose each class\'s tutor, upload form responses and placement sheets, and see every analytic.'));
      if (has('HOD')) blocks.push(role('Head of Department', 'You see every student, faculty member and chart, can explore all of the department\'s work by type, and open the Newsletter studio. Your view is read-only.'));
      if (has('PC')) blocks.push(role('Programme Coordinator', 'You see all the classes of your programme (for UG that means both G1 and G2): students, placements and statistics. Your view is read-only.'));
      if (has('TUTOR')) blocks.push(role('Class tutor', 'You look after your own class: add or remove students, set the class\'s semester, and follow its achievements, participation and placements.'));
      blocks.push(role('Faculty', blocks.length
        ? 'You also have your own page of everything you have submitted through the forms (see <b>My activities</b>).'
        : 'Your own page lists everything you have submitted through the forms, neatly sorted: papers, patents, awards, events and students you mentored.'));
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
    S.push({ id: 'basics', label: 'The top bar', hint: 'Tabs, Help, sign out', steps: () => [
      { before: () => { document.querySelector('#view') && window.scrollTo(0, 0); }, target: '#tabs', title: 'Your tabs', body: '<p>Each tab is a part of the portal. <b>What you see depends on your role</b>, so you only get what you can use. We will visit them one by one.</p>', place: 'bottom' },
      { target: '.topbar .brand', title: 'The logo', body: '<p>Takes you back to the <b>forms page</b>, where every Google Form the department uses is listed.</p>', place: 'bottom' },
      { target: '.tour-help', title: 'Help', body: '<p>Replay this tour, or have just the page you are on explained.</p>', place: 'bottom' },
      { target: '#who', title: 'Who you are', body: '<p>Your name and role(s). If you can open the Newsletter studio, its button sits right here.</p>', place: 'bottom' },
      { target: '#logout', title: 'Sign out', body: '<p>Always sign out on a shared computer.</p>', place: 'bottom' },
    ] });
    S.push({ id: 'dash', label: 'Dashboard', hint: 'Charts and totals for your scope', steps: () => [
      { before: goTab('dash'), target: '#view .filters', title: 'Choose what to look at', body: `<p>Pick an <b>academic year</b>${me.all_access ? ', a <b>programme</b>' : ''} and a <b>class</b>. Every number and chart below follows your choice.</p>${me.all_access ? '' : '<p>You only see the classes you are responsible for.</p>'}`, place: 'bottom' },
      { target: '#dash-out > .kpis', title: 'Headline numbers', body: '<p>Active students, how many have achievements, the participation rate, the placement percentage, and the highest and average package.</p>' },
      { target: '#dash-out .grid-2', title: 'Student achievements', body: '<p>By category, level, domain and year, then class-wise participation and the <b>top students</b>. Click a roll number to open that student\'s page.</p>', place: 'top' },
      { target: () => find('#dash-out h2', /Placements/)()?.nextElementSibling, title: 'Placements', body: '<p>Opted in and out, who is still unplaced, package distribution, top recruiters, offer types and the reasons students opt out.</p>' },
      ...(me.all_access ? [{ target: () => find('#dash-out h2', /Department/)()?.nextElementSibling, title: 'The whole department', body: '<p>Research funding, event participants, outreach attendance, submissions by form and year, research by indexing and quartile, faculty achievements, <b>MoU status</b> and the most active faculty.</p>' }] : []),
    ] });
    if (hasClasses()) S.push({ id: 'students', label: 'Students', hint: 'Find, add and open students', steps: () => [
      { before: goTab('students'), target: '#view .filters', title: 'Find students', body: `<p>${document.getElementById('f-grp') ? 'Choose <b>both groups, G1 or G2</b>, then a class, a status, or search by roll number or name.' : 'Pick a class, a status, or search by roll number or name.'}</p>`, place: 'bottom' },
      { target: '#st-list', title: 'The student list', body: `<p><b>Click a roll number</b> to open that student\'s page: achievements, participations, research, events and placement.</p>${isEditor() ? '<p><b>Move</b> shifts a student to another class; <b>Remove</b> takes them out of the class (their records are kept).</p>' : '<p>This list is view-only for your role.</p>'}</p>`, place: 'top' },
      { target: '#add-st', optional: true, title: 'Add a student', body: '<p>Enter a roll number and name for a student who joins your class.</p>', place: 'bottom' },
      { target: card('#view .drop'), optional: true, title: 'Upload a class list', body: '<p>Download the template, fill <b>Roll No</b> and <b>Full Name</b>, upload. Existing roll numbers are updated, and a tutor\'s students go into the tutor\'s own class.</p>', place: 'top' },
    ] });
    if (hasClasses()) S.push({ id: 'classes', label: 'Classes', hint: 'Tutor and semester of each class', steps: () => [
      { before: goTab('classes'), target: '#view [data-c]', title: 'One card per class', body: '<p>A class is known by its <b>tutor and semester</b>. Two semesters make a year, so the year and class code follow the semester. Students stay with their class as it moves up: nobody is promoted one by one.</p>', place: 'bottom' },
      { target: '#view [data-c] .sem', optional: true, title: 'Move a class on', body: '<p>Tutors (and the Admin) set the <b>semester</b> and <b>academic year</b> here, then Save.</p>', place: 'bottom' },
      { target: '#view [data-c] .tutor', optional: true, title: 'Choose the tutor', body: '<p>Only the <b>Admin</b> changes a class\'s tutor.</p>', place: 'bottom' },
      { target: '#add-class', optional: true, title: 'Add a class', body: '<p>For a new batch. Choose the programme, group, starting semester and tutor.</p>', place: 'bottom' },
      { target: '#view .graduate', optional: true, title: 'When a class finishes', body: '<p>In its last semester you can <b>mark it graduated</b>: its students become Graduated and the class closes. All records are kept.</p>', place: 'top' },
    ] });
    if (has('ADMIN')) S.push({ id: 'uploads', label: 'Data upload', hint: 'Responses and placement sheets', steps: () => [
      { before: goTab('uploads'), target: () => document.querySelectorAll('#view > .card')[0], title: 'Placement sheets', body: '<p>Download the template, fill one row per offer, upload. <b>A student already in the system is replaced</b> by the rows in this file for that academic year.</p>', place: 'bottom' },
      { target: () => document.querySelectorAll('#view > .card')[1], title: 'Form responses', body: '<p>One card per Google Form. Export the form\'s responses sheet as <b>.xlsx</b> and upload it. Uploading the same file twice never creates duplicates.</p>', place: 'bottom' },
      { target: card('#unmatched'), title: 'Roll numbers that matched nobody', body: '<p>If a roll number or employee ID on a response matches nobody, it is listed here so you can fix the student list or the form. Nothing is lost.</p>', place: 'top' },
    ] });
    if (hasClasses()) S.push({ id: 'placements', label: 'Placements', hint: 'Offers and opt-in / opt-out', steps: () => [
      { before: goTab('placements'), target: () => document.querySelector('#view [data-m]')?.parentElement, title: 'Two views', body: '<p><b>Offers</b> lists every offer (company, type, package). <b>Opt-in / opt-out</b> shows who chose to sit for placements, and why some did not.</p>', place: 'bottom' },
      { target: () => document.querySelector('#p-ay')?.closest('.filters'), title: 'Filters', body: '<p>Year, class, company, offer type, package range and search. Click a roll number to open the student\'s page.</p>', place: 'bottom' },
      { target: '#p-out', title: 'The results', body: '<p>Placement sheets are uploaded by the Admin; the data then shows up here and on the Dashboard.</p>', place: 'top' },
    ] });
    S.push({ id: 'subs', label: 'Submissions', hint: 'Every form response', steps: () => [
      { before: goTab('subs'), target: '#view .filters', title: 'Every form response', body: `<p>Filter by form, year, category, class, level, roll number, dates or words in the title.</p><p>${me.all_access ? 'You see everything.' : 'You see what you submitted' + (hasClasses() ? ', plus responses involving your students.' : '.')}</p>`, place: 'bottom' },
      { target: '#s-out', title: 'Open a response', body: '<p><b>Click a row</b> for the full answer: people involved, every detail and the links.</p>', place: 'top' },
    ] });
    if (me.all_access) S.push({ id: 'faculty', label: has('ADMIN') ? 'Faculty & roles' : 'Faculty', hint: 'Directory, activity counts, roles', steps: () => [
      { before: goTab('faculty'), target: () => document.getElementById('ff-q')?.closest('.filters'), title: 'Find faculty', body: '<p>Search, or filter by <b>designation, status, role</b>, or by what they have entered (research, achievements, events, outreach, mentoring).</p>', place: 'bottom' },
      { target: '#fac-list', title: 'The faculty table', body: `<p>The counts show how much each person has entered. <b>Click a name</b> or <b>Activities</b> to open their page.</p>${has('ADMIN') ? '<p>As Admin you can also set <b>Roles</b>, <b>Edit</b>, <b>Reset password</b> or <b>Relieve</b> someone.</p>' : ''}`, place: 'top' },
      { target: '#add-fac', optional: true, title: 'Add faculty', body: '<p>Creates the login and shows a <b>one-time temporary password</b>. Share it privately; they must change it at first sign-in.</p>', place: 'bottom' },
      { target: '#copy-choices', optional: true, title: 'Copy list for the Apps Script', body: '<p>Copies the faculty drop-down list to paste into the Google Forms script, so people choose their name instead of typing it.</p>', place: 'bottom' },
      { target: card('#view .drop'), optional: true, title: 'Upload faculty', body: '<p>Upload an Excel list: existing employee IDs are updated and new ones get temporary passwords (shown once).</p>', place: 'top' },
    ] });
    if (me.all_access) S.push({ id: 'works', label: 'By work', hint: 'One kind of work across the department', steps: () => [
      { before: goTab('works'), target: '#wk-bar', title: 'Pick a kind of work', body: '<p>Five drop-downs: <b>Research & Innovation, Faculty achievements, Departmental highlights, Industry & outreach, Student achievements</b>. Each lists its kinds (patents, journal papers, hackathons, awards &hellip;) with counts. This looks at the <b>work itself</b>, across the whole department.</p>', place: 'bottom' },
      { target: '#wk-filters', title: 'Filters about the work', body: '<p>Year, dates, search, and filters that depend on the kind: indexing and quartile for papers, level for awards, status for events. They describe the work, not the people.</p>', place: 'bottom' },
      { target: '#wk-stats', title: 'Totals', body: '<p>Totals over <b>everything that matches</b> the filters, not only what is on screen (funding, participants, prize money &hellip;).</p>', place: 'bottom' },
      { target: '#wk-results', title: 'The list', body: '<p>Each card is one piece of work. Click to open its details and evidence links; the people involved are named inside.</p>', place: 'top' },
      { target: '#w-csv', title: 'Download CSV', body: '<p>Opens a pop-up: set the <b>dates</b> at the top, <b>tick the columns</b> you want (or Select all), then download a file for Excel.</p>', place: 'bottom' },
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
      body: `<p>The studio turns the department's approved responses into the <b>IT Chronicles newsletter</b>.</p>
        ${role('Who uses it', 'Only the <b>Admin and the HoD</b>. Faculty submit through the forms; you review the responses, design the layout and build the document.')}
        <p>The tour visits every tab. Skip it now; <b>Help</b> at the top replays it, or one tab.</p>`,
    }];
    const S = [
      { id: 'overview', label: 'Overview', hint: 'Counts and recent activity', steps: () => [
        { before: goTab('overview'), target: '.stats', title: 'Where things stand', body: '<p>Responses received, those <b>needing review</b>, approved, and featured. Click any of them to open the matching list.</p>', place: 'bottom' },
        { target: '#overview-sections', title: 'Section by section', body: '<p>Responses and approved entries for each newsletter section.</p>', place: 'top' },
        { target: '#activity-log', title: 'Recent activity', body: '<p>Imports, approvals and other changes, newest first.</p>', place: 'left' },
      ] },
      { id: 'forms', label: 'Forms', hint: 'Questions and what they mean', steps: () => [
        { before: goTab('forms'), target: '#forms-list', title: 'Your forms', body: '<p>One entry per Google Form. Pick one to edit how its questions feed the newsletter.</p>', place: 'right' },
        { target: btn(/New form/), optional: true, title: 'New form', body: '<p>Add a form by pasting its response-sheet headers; the studio works out what each column means.</p>', place: 'right' },
        { target: btn(/Import from Apps Script/), optional: true, title: 'Import from Apps Script', body: '<p>Paste the Google Apps Script that built your form and every question is read in one go.</p>', place: 'right' },
        { target: '#form-editor', title: 'The form editor', body: '<p>Tell the newsletter what each question is (title, people, date, description &hellip;) and set the sub-sections.</p>', place: 'left' },
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
      { id: 'responses', label: 'Responses', hint: 'Review, approve, feature', steps: () => [
        { before: goTab('responses'), target: '#tab-responses .toolbar', title: 'Filter and add', body: '<p>Filter by status and section. <b>Import CSV</b> or <b>+ Add response</b> to bring entries in by hand.</p>', place: 'bottom' },
        { target: '#responses-list', title: 'Review each response', body: '<p>Open an entry to edit it, <b>approve or reject</b> it, or mark it <b>featured</b> for the spotlight. Only approved entries reach the newsletter.</p>', place: 'top' },
      ] },
      { id: 'publish', label: 'Publish', hint: 'Build the Word documents', steps: () => [
        { before: goTab('publish'), target: '#publish-sections', title: 'Choose sections', body: '<p>Tick the sections to include, and build each one as its own Word document if you want.</p>', place: 'right' },
        { target: '.publish-side', title: 'Master newsletter', body: '<p>Combines every ticked section, featured items first, into <b>one Word document</b>. Front pages are included if you wish.</p>', place: 'left' },
      ] },
    ];
    const kit = TourKit.mount({
      app: 'studio', host: document.getElementById('help-host'), me, token, welcome, sections: () => S,
      current: () => document.querySelector('#main-tabs .tab.active')?.dataset.tab,
      snapshot: () => { const t = document.querySelector('#main-tabs .tab.active')?.dataset.tab || 'overview'; return () => switchTab(t); },
    });
    kit.autoStart();
    return kit;
  }

  async function fetchMe(tokenKey) {
    const token = sessionStorage.getItem(tokenKey);
    if (!token) return null;
    try { const r = await fetch('/api/auth/me', { headers: { Authorization: 'Bearer ' + token } }); return r.ok ? { me: await r.json(), token } : null; } catch (e) { return null; }
  }
  window.Tours = { home, portal, diary, studio, fetchMe };
})();
