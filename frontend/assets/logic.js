export const fields = {
  current_unit_cost: ['Current supplier’s price', 'USD/unit'],
  new_unit_cost: ['New supplier’s price', 'USD/unit'],
  monthly_quantity: ['Quantity needed each month', 'units/month'],
  current_shipping: ['Current supplier’s delivery charge', 'USD'],
  new_shipping: ['New supplier’s delivery charge', 'USD'],
  switching_cost: ['One-time cost of switching', 'USD'],
  current_moq: ['Current supplier’s minimum order', 'units'],
  new_moq: ['New supplier’s minimum order', 'units'],
  horizon: ['How far ahead to compare', 'months'],
  current_escalation: ['Current supplier’s yearly price increase', 'ratio'],
  new_escalation: ['New supplier’s yearly price increase', 'ratio'],
  demand_variation: ['How much demand could vary', 'ratio'],
  cost_variation: ['How much the new price could vary', 'ratio'],
  event_cost: ['Cost of running the event', 'USD'],
  incremental_visits: ['Extra customer visits from the event', 'visits'],
  average_spend: ['Average spending per visit', 'USD/visit'],
  contribution_margin: ['Sales left after variable product costs', 'ratio'],
  repeat_rate: ['Customers expected to return', 'ratio'],
  repeat_visits: ['Extra visits per returning customer', 'visits/customer'],
  staffing_cost: ['Extra staffing cost', 'USD'],
  attendance_variation: ['How much attendance could vary', 'ratio'],
  spend_variation: ['How much customer spending could vary', 'ratio'],
  expense_variation: ['How much event costs could vary', 'ratio'],
  repeat_variation: ['How much repeat business could vary', 'ratio'],
};
export const money = value => new Intl.NumberFormat('en-US', {style: 'currency', currency: 'USD', maximumFractionDigits: 2}).format(value);
export const labelFor = field => fields[field]?.[0] || field.replaceAll('_', ' ');
export const unitFor = field => fields[field]?.[1];
export const readableUnit = unit => ({'USD': 'dollars', 'USD/unit': 'dollars per unit', 'USD/visit': 'dollars per visit', 'units/month': 'units per month', 'visits/customer': 'visits per returning customer', 'ratio': 'percent'}[unit] || unit || '');
export function readableValue(value, unit) {
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  if (unit === 'ratio') return `${Number((n * 100).toFixed(5))}%`;
  if (unit === 'USD') return money(n);
  if (unit === 'USD/unit') return `${money(n)} per unit`;
  if (unit === 'USD/visit' || unit === 'USD per visit') return `${money(n)} per visit`;
  if (unit === 'months') return `${n} months`;
  return `${n.toLocaleString('en-US')} ${unit || ''}`.trim();
}
export function groupQuestions(questions) {
  const groups = new Map();
  for (const q of questions.filter(q => q.data.status === 'open')) {
    if (!groups.has(q.data.field)) groups.set(q.data.field, []);
    groups.get(q.data.field).push(q);
  }
  return [...groups].map(([field, questions]) => ({field, questions}));
}
export function answersFor(groups, selections) {
  const answers = [];
  for (const group of groups) {
    const selected = selections[group.field];
    if (!selected) throw new Error(`Please choose an answer for “${labelFor(group.field)}”.`);
    const chosen = selected.candidateId
      ? group.questions.find(q => q.data.candidate_id === selected.candidateId)
      : group.questions.find(q => !q.data.candidate_id) || group.questions[0];
    if (!chosen) throw new Error('The question has changed. Please check the page again.');
    if (selected.candidateId) answers.push({question_id: chosen.id, accept_candidate: true});
    else {
      const unit = unitFor(group.field);
      if (!unit) throw new Error('This question needs a supported input. Please contact the developer.');
      if (String(selected.value).trim() === '') throw new Error(`Please enter “${labelFor(group.field)}”.`);
      const value = Number(selected.value);
      if (!Number.isFinite(value) || value < 0 || (unit === 'ratio' && value > 100) || (group.field === 'horizon' && (value < 1 || value > 60 || !Number.isInteger(value))) || (group.field.endsWith('_moq') && !Number.isInteger(value))) {
        throw new Error(`Please check “${labelFor(group.field)}”. Use a valid nonnegative number${unit === 'ratio' ? ' from 0 to 100' : ''}.`);
      }
      answers.push({question_id: chosen.id, value: unit === 'ratio' ? value / 100 : value, unit});
    }
    const handled = new Set([chosen.data.candidate_id]);
    for (const q of group.questions) {
      if (q.data.candidate_id && !handled.has(q.data.candidate_id)) {
        answers.push({question_id: q.id, reject_candidate: true});
        handled.add(q.data.candidate_id);
      }
    }
  }
  return answers;
}
export function classifyFiles(files, maxBytes = 5 * 1024 * 1024) {
  const supported = [], skipped = [];
  for (const file of files) {
    const path = file.webkitRelativePath || file.name;
    if (path.split('/').some(part => part.startsWith('.')) || !/\.(csv|xlsx|txt|pdf)$/i.test(file.name)) skipped.push(path);
    else {
      const error = !file.size ? 'This file is empty. Please remove it or choose a file with information in it.' : file.size > maxBytes ? 'This file is larger than 5 MB. Please use a smaller file.' : '';
      supported.push({file, path, status: error ? 'failed' : 'pending', sheet: '', error});
    }
  }
  return {supported, skipped};
}
