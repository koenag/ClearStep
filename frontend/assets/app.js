import {money, labelFor, unitFor, readableUnit, readableValue, groupQuestions, answersFor, classifyFiles} from './logic.js';

const $ = id => document.getElementById(id);
const state = {files: [], skipped: [], businessId: null, run: null, facts: [], sources: [], groups: [], timer: null, generation: 0, busy: false};
const active = new Set(['created', 'planning', 'running', 'synthesizing']);
const storageKey = 'clearstep.current-run';
const remember = id => {try {id ? localStorage.setItem(storageKey, id) : localStorage.removeItem(storageKey);} catch { /* Storage may be disabled. */ }};
function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function showNotice(message) { $('notice').textContent = message; $('notice').hidden = !message; }
function screen(name, step) {
  const changed = $(name).hidden;
  for (const id of ['setup', 'working', 'review', 'result', 'stopped']) $(id).hidden = id !== name;
  for (let n = 1; n <= 3; n++) n === step ? $(`step-${n}`).setAttribute('aria-current', 'step') : $(`step-${n}`).removeAttribute('aria-current');
  $('support').hidden = !state.run;
  if (state.run) $('support-text').textContent = `Reference: ${state.run.id} · Status: ${state.run.data.status}`;
  if (changed) {
    const heading = $(name).querySelector('h1');
    if (heading) {heading.tabIndex = -1; heading.focus({preventScroll: true});}
  }
}
async function api(path, options = {}) {
  let response;
  try { response = await fetch(`/api${path}`, options); }
  catch { throw new Error('We couldn’t connect. Check that the app is running, then try again.'); }
  let body;
  try { body = await response.json(); } catch { throw new Error('We couldn’t read the response. Please try again.'); }
  if (!response.ok) {
    const error = new Error(body.error?.message || 'Something went wrong. Please try again.');
    error.code = body.error?.code;
    error.status = response.status;
    throw error;
  }
  return body;
}
const post = (path, body) => api(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
function setupBusy(busy) {
  state.busy = busy;
  $('start-form').setAttribute('aria-busy', String(busy));
  for (const control of $('start-form').querySelectorAll('button,textarea,input')) control.disabled = busy;
  $('start-button').textContent = busy ? 'Preparing your files…' : state.files.some(f => f.status === 'failed') ? 'Retry files and continue' : 'Help me work it out →';
}
function renderFiles() {
  $('file-list').replaceChildren(); $('file-summary').replaceChildren();
  if (state.files.length) $('file-summary').append(el('p', `${state.files.length} file${state.files.length === 1 ? '' : 's'} selected`, 'selected-summary'));
  if (state.skipped.length) {
    const details = el('details'); details.append(el('summary', `${state.skipped.length} unsupported or hidden file(s) left out`));
    details.append(el('p', state.skipped.join(', '), 'fine')); $('file-summary').append(details);
  }
  state.files.forEach((item, index) => {
    const li = el('li'), row = el('div', undefined, 'file-row');
    const description = el('div', undefined, 'file-name'); description.append(el('span', item.path));
    description.append(el('div', {pending: 'Ready to upload', uploading: 'Uploading…', uploaded: '✓ File loaded', failed: 'Needs attention'}[item.status], 'file-state'));
    const remove = el('button', 'Remove', 'text-button'); remove.type = 'button'; remove.disabled = state.busy;
    remove.setAttribute('aria-label', `Remove ${item.path}`);
    remove.addEventListener('click', () => {
      if (item.status === 'uploaded') {
        state.businessId = null;
        state.files.forEach(f => {f.status = 'pending';});
      }
      state.files.splice(index, 1); renderFiles();
    });
    row.append(description, remove); li.append(row);
    if (item.error) li.append(el('p', item.error, 'file-error'));
    if (item.code === 'sheet_required' || item.code === 'invalid_sheet') {
      const label = el('label', 'Which worksheet should we use?', 'sheet-label');
      const input = el('input'); input.type = 'text'; input.value = item.sheet; input.placeholder = 'Enter the worksheet name'; input.disabled = state.busy;
      input.addEventListener('input', () => {item.sheet = input.value;}); label.append(input); li.append(label);
    }
    $('file-list').append(li);
  });
}
function selectFiles(files) {
  const batch = classifyFiles(files);
  if (!batch.supported.length) {showNotice('There are no supported files in this selection. Choose CSV, .xlsx, .txt, or a PDF with selectable text.'); return;}
  state.files = batch.supported; state.skipped = batch.skipped; state.businessId = null;
  showNotice(''); renderFiles();
}
$('choose-folder').addEventListener('click', () => $('folder-input').click());
$('choose-files').addEventListener('click', () => $('files-input').click());
for (const id of ['folder-input', 'files-input']) $(id).addEventListener('change', event => {selectFiles([...event.target.files]); event.target.value = '';});
document.querySelectorAll('[data-example]').forEach(button => button.addEventListener('click', () => {$('question').value = button.dataset.example; $('question').focus();}));

$('start-form').addEventListener('submit', async event => {
  event.preventDefault(); if (state.busy) return;
  showNotice('');
  const question = $('question').value.trim();
  if (question.length < 3) {showNotice('Tell us a little more about the decision you’re considering.'); $('question').focus(); return;}
  if (!state.files.length) {showNotice('First, choose a folder or a few files to work from.'); $('choose-folder').focus(); return;}
  if (state.files.some(f => f.file.size > 5 * 1024 * 1024 || !f.file.size)) {showNotice('Please remove any empty files or files larger than 5 MB before continuing.'); return;}
  setupBusy(true);
  try {
    if (!state.businessId) {
      const folderName = state.files[0].path.includes('/') ? state.files[0].path.split('/')[0] : 'My business records';
      state.businessId = (await post('/businesses', {name: folderName.slice(0, 120), industry: 'Small business'})).id;
    }
    for (const item of state.files.filter(f => f.status !== 'uploaded')) {
      item.status = 'uploading'; item.error = ''; renderFiles();
      $('upload-progress').textContent = `Loading ${item.path}…`;
      const data = new FormData(); data.append('file', item.file); if (item.sheet.trim()) data.append('sheet', item.sheet.trim());
      try { const source = await api(`/businesses/${state.businessId}/sources`, {method: 'POST', body: data}); item.status = 'uploaded'; item.sourceId = source.id; item.code = null; }
      catch (error) {item.status = 'failed'; item.error = error.message; item.code = error.code;}
      renderFiles();
    }
    if (state.files.some(f => f.status !== 'uploaded')) throw new Error('Some files need attention. Check the messages above, then retry. Analysis has not started.');
    $('upload-progress').textContent = 'Starting your analysis…';
    state.run = await post('/runs', {business_id: state.businessId, question});
    remember(state.run.id); screen('working', 1); window.scrollTo({top: 0, behavior: 'smooth'});
    await refreshRun();
  } catch (error) {showNotice(error.message);}
  finally {setupBusy(false); renderFiles(); $('upload-progress').textContent = '';}
});

async function refreshRun() {
  clearTimeout(state.timer); if (!state.run) return;
  const generation = state.generation, id = state.run.id;
  try {
    const run = await api(`/runs/${id}`); if (generation !== state.generation) return;
    state.run = run; showNotice('');
    if (active.has(run.data.status)) {
      const task = run.tasks.find(t => t.data.status === 'running');
      const role = task?.data.role;
      const calculating = role === 'scenario' || run.data.status === 'synthesizing';
      $('working-title').textContent = calculating ? 'Working through the numbers' : role === 'risk' ? 'Checking the important details' : 'Looking through your information';
      $('working-description').textContent = calculating ? 'Comparing possible outcomes using your confirmed details.' : role === 'risk' ? 'Looking for missing information and things that could affect your decision.' : 'Organizing your records and finding what’s relevant to your question.';
      screen('working', calculating ? 3 : 1);
      state.timer = setTimeout(refreshRun, 1800);
    } else if (run.data.status === 'waiting_for_input') {
      [state.facts, state.sources] = await Promise.all([api(`/businesses/${run.business_id}/facts`), api(`/businesses/${run.business_id}/sources`)]);
      if (generation !== state.generation) return;
      renderReview(); screen('review', 2);
    } else if (run.data.status === 'completed' && run.data.report?.analysis) {renderResult(); screen('result', 3);}
    else renderStopped();
  } catch (error) {
    if (generation !== state.generation) return;
    if (error.status === 404) {
      renderStopped(); showNotice('This saved analysis could not be found. Please start a new question.'); return;
    }
    showNotice(`${error.message} Your analysis reference is saved in this browser. We’ll check again shortly.`);
    state.timer = setTimeout(refreshRun, 5000);
  }
}
function renderReview() {
  state.groups = groupQuestions(state.run.questions); $('review-fields').replaceChildren();
  const factMap = new Map(state.facts.map(f => [f.id, f]));
  const sourceMap = new Map(state.sources.map(s => [s.id, s.data.filename]));
  state.groups.forEach((group, index) => {
    const fieldset = el('fieldset', undefined, 'review-field'); fieldset.dataset.field = group.field;
    fieldset.append(el('legend', labelFor(group.field)));
    for (const reason of new Set(group.questions.map(q => q.data.reason))) fieldset.append(el('p', reason, 'question-reason'));
    const seen = new Set();
    for (const question of group.questions) {
      const fact = factMap.get(question.data.candidate_id); if (!fact || seen.has(fact.id)) continue; seen.add(fact.id);
      const option = el('label', undefined, 'review-option'), title = el('span', undefined, 'option-title');
      const radio = el('input'); radio.type = 'radio'; radio.name = `answer-${index}`; radio.value = fact.id; radio.required = true;
      title.append(radio, el('strong', `Use ${readableValue(fact.data.value, fact.data.unit)}`)); option.append(title);
      const evidence = el('div', undefined, 'evidence');
      evidence.append(el('p', `${fact.data.provenance === 'assumed' ? 'An assumption from' : 'Found in'} ${sourceMap.get(fact.data.source_id) || 'your records'}${fact.data.location ? ` · ${fact.data.location}` : ''}`));
      if (fact.data.evidence) {const details = el('details'); details.append(el('summary', 'See the original wording'), el('blockquote', fact.data.evidence)); evidence.append(details);}
      evidence.append(el('p', 'Choose this only if the value, unit, and time period match your business.')); option.append(evidence); fieldset.append(option);
    }
    const custom = el('label', undefined, 'review-option'), title = el('span', undefined, 'option-title');
    const radio = el('input'); radio.type = 'radio'; radio.name = `answer-${index}`; radio.value = 'custom'; radio.required = true;
    title.append(radio, el('span', seen.size ? 'Use a different number' : 'Enter the number')); custom.append(title);
    const row = el('span', undefined, 'value-input');
    const input = el('input'); input.type = 'number'; input.min = group.field === 'horizon' ? '1' : '0'; input.step = group.field === 'horizon' || group.field.endsWith('_moq') ? '1' : 'any'; input.disabled = true; input.required = true; input.dataset.value = 'true';
    if (unitFor(group.field) === 'ratio') input.max = '100'; if (group.field === 'horizon') input.max = '60';
    input.setAttribute('aria-label', `${labelFor(group.field)} (${unitFor(group.field) === 'ratio' ? 'percent' : unitFor(group.field) || 'value'})`);
    row.append(input, el('span', unitFor(group.field) === 'ratio' ? '% (for example, enter 20 for 20%)' : readableUnit(unitFor(group.field)))); custom.append(row); fieldset.append(custom);
    fieldset.addEventListener('change', () => {input.disabled = !radio.checked; if (radio.checked) input.focus();});
    $('review-fields').append(fieldset);
  });
}
$('review-form').addEventListener('submit', async event => {
  event.preventDefault(); if (state.busy) return;
  showNotice(''); const selections = {};
  state.groups.forEach((group, index) => {
    const selected = $('review-form').querySelector(`input[name="answer-${index}"]:checked`);
    if (selected) selections[group.field] = selected.value === 'custom' ? {value: selected.closest('fieldset').querySelector('[data-value]').value} : {candidateId: selected.value};
  });
  let answers;
  try {answers = answersFor(state.groups, selections);} catch (error) {showNotice(error.message); return;}
  state.busy = true; const button = $('review-form').querySelector('[type=submit]'); button.disabled = true; button.textContent = 'Saving your details…';
  try {await post(`/runs/${state.run.id}/answers`, {answers}); await refreshRun(); window.scrollTo({top: 0, behavior: 'smooth'});}
  catch (error) {showNotice(error.message);}
  finally {state.busy = false; button.disabled = false; button.textContent = 'Continue with these details →';}
});

function renderResult() {
  const report = state.run.data.report, analysis = report.analysis;
  const base = analysis.scenarios.find(s => s.name === 'Base case')?.result;
  const card = el('article', undefined, 'card answer-card');
  const heading = el('div', undefined, 'answer-heading'), text = el('div'); text.append(el('p', 'YOUR DECISION, A LITTLE CLEARER', 'eyebrow'), el('h1', 'Here’s what the numbers show.'));
  const download = el('button', 'Save this answer', 'button secondary'); download.type = 'button'; download.addEventListener('click', downloadAnswer);
  heading.append(text, download); card.append(heading, el('p', state.run.data.question, 'answer-question'), el('p', report.summary, 'answer-summary'));
  if (base) {
    const metrics = el('div', undefined, 'metrics');
    const values = [
      ['Estimated net benefit', money(base.net_benefit), `Over ${base.horizon} months, after modeled costs`],
      ['Cash needed at the start', money(base.upfront_cash), analysis.decision_type === 'supplier_switch' ? 'Includes switching and the first purchase' : 'Event and extra staffing costs'],
      [analysis.decision_type === 'supplier_switch' ? 'When switching pays back' : 'Extra visits needed to break even', analysis.decision_type === 'supplier_switch' ? base.break_even_month === null ? 'Not within this period' : `Month ${base.break_even_month}` : base.break_even_visits === null ? 'Not achievable with these inputs' : String(base.break_even_visits), 'Under the base assumptions'],
    ];
    for (const [title, value, note] of values) {const box = el('div', undefined, 'metric'); box.append(el('small', title), el('strong', value), el('span', note)); metrics.append(box);} card.append(metrics);
  }
  const scenarios = el('section', undefined, 'answer-section'); scenarios.append(el('h2', 'What if things turn out differently?'));
  const scroll = el('div', undefined, 'table-scroll'), table = el('table'), head = el('thead'), header = el('tr');
  header.append(el('th', 'Illustrative scenario'), el('th', 'Estimated net benefit')); head.append(header); table.append(head);
  const body = el('tbody'); for (const s of analysis.scenarios) {const tr = el('tr'); tr.append(el('td', {'Pessimistic': 'Less favorable assumptions', 'Base case': 'Base assumptions', 'Optimistic': 'More favorable assumptions'}[s.name] || s.name), el('td', money(s.result.net_benefit))); body.append(tr);} table.append(body); scroll.append(table); scenarios.append(scroll, el('p', analysis.scenario_note, 'source-note')); card.append(scenarios);
  if (report.qualitative_commentary) {const section = el('section', undefined, 'answer-section'); section.append(el('h2', 'What this means for your decision'), el('p', report.qualitative_commentary)); card.append(section);}
  const risks = el('section', undefined, 'answer-section'); risks.append(el('h2', 'Keep these things in mind')); const list = el('ul');
  for (const risk of [...new Set([...(report.risk_findings || []).map(f => f.description), ...(analysis.risks || []), ...(report.limitations || [])])]) list.append(el('li', risk)); risks.append(list); card.append(risks);
  const assumptions = el('details', undefined, 'answer-section'); assumptions.append(el('summary', 'See the numbers used'));
  const inputs = el('ul'); for (const [field, value] of Object.entries(analysis.inputs)) inputs.append(el('li', `${labelFor(field)}: ${readableValue(value, unitFor(field))}`)); assumptions.append(inputs); card.append(assumptions);
  const actions = el('div', undefined, 'review-actions'), next = el('button', 'Ask a new question', 'button primary'); next.type = 'button'; next.addEventListener('click', reset); actions.append(next); card.append(actions);
  $('result').replaceChildren(card);
}
function downloadAnswer() {
  const report = state.run.data.report, analysis = report.analysis;
  const text = [state.run.data.question, '', report.summary, '', report.qualitative_commentary, '', 'Possible outcomes', ...analysis.scenarios.map(s => `${s.name}: ${money(s.result.net_benefit)}`), analysis.scenario_note, '', 'Numbers used', ...Object.entries(analysis.inputs).map(([field, value]) => `${labelFor(field)}: ${readableValue(value, unitFor(field))}`), '', 'Things to keep in mind', ...(report.risk_findings || []).map(f => f.description), ...analysis.risks, ...report.limitations, '', `Reference: ${state.run.id}`].join('\n');
  const url = URL.createObjectURL(new Blob([text], {type: 'text/plain;charset=utf-8'})); const a = el('a'); a.href = url; a.download = 'my-business-answer.txt'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function renderStopped() {
  const status = state.run.data.status;
  const messages = {
    blocked: ['A detail needs a closer look.', 'The analysis found something that needs clarification before it can give you a reliable financial answer.'],
    unsupported: ['Let’s try a different question.', 'Right now we can compare two suppliers or estimate whether a promotional event covers its costs. Start a new question about one of those decisions.'],
    canceled: ['Your analysis has been stopped.', 'No further analysis will continue for this question.'],
    limit_reached: ['We reached the analysis limit.', 'This attempt stopped before it could finish. Try a more focused question or a smaller set of relevant files.'],
    interrupted: ['Your analysis was interrupted.', 'The app may have restarted. You can start a new question when you’re ready.'],
    failed: ['We couldn’t finish this answer.', 'Something prevented this analysis from finishing. Your files and any saved work are still stored.'],
  };
  const [title, message] = messages[status] || messages.failed;
  $('stopped-title').textContent = title; $('stopped-message').textContent = message; $('stopped-details').replaceChildren();
  for (const task of state.run.tasks || []) if (task.data.result?.status === 'blocked') $('stopped-details').append(el('p', task.data.result.summary));
  if (state.run.data.error) {const details = el('details'); details.append(el('summary', 'More about what happened'), el('p', state.run.data.error.message)); $('stopped-details').append(details);}
  screen('stopped', 2);
}
function reset() {
  clearTimeout(state.timer); state.generation++; state.run = null; state.businessId = null; state.files = []; state.skipped = []; state.facts = []; state.sources = []; state.groups = []; remember(null);
  $('question').value = ''; showNotice(''); renderFiles(); screen('setup', 1); window.scrollTo({top: 0, behavior: 'smooth'}); $('choose-folder').focus();
}
document.querySelectorAll('.new-question').forEach(button => button.addEventListener('click', reset));
document.querySelectorAll('.stop-button').forEach(button => button.addEventListener('click', async () => {
  if (!state.run || state.busy) return; button.disabled = true;
  try {await post(`/runs/${state.run.id}/cancel`, {}); state.generation++; clearTimeout(state.timer); await refreshRun();} catch (error) {showNotice(error.message);} finally {button.disabled = false;}
}));
$('refresh-run').addEventListener('click', refreshRun);
let saved; try {saved = localStorage.getItem(storageKey);} catch { /* Storage may be disabled. */ }
if (saved && /^run_[a-f0-9]+$/.test(saved)) {
  state.run = {id: saved, data: {status: 'created'}}; screen('working', 1);
  const abandon = el('button', 'Stop and start a new question', 'text-button'); abandon.type = 'button';
  abandon.addEventListener('click', async () => {
    abandon.disabled = true;
    try {if (active.has(state.run?.data.status) || state.run?.data.status === 'waiting_for_input') await post(`/runs/${state.run.id}/cancel`, {}); reset();}
    catch (error) {if (error.status === 404) reset(); else showNotice(error.message);}
    finally {abandon.disabled = false;}
  }); $('working').append(abandon);
  refreshRun();
}
