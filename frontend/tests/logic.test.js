import test from 'node:test';
import assert from 'node:assert/strict';
import {answersFor, classifyFiles, groupQuestions, readableValue} from '../assets/logic.js';

const question = (id, field, candidateId = null) => ({id, data: {field, candidate_id: candidateId, status: 'open'}});
test('one chosen candidate explicitly rejects competing candidates, without duplicate answers', () => {
  const groups = groupQuestions([question('q1', 'new_unit_cost', 'f1'), question('q2', 'new_unit_cost', 'f2'), question('q3', 'new_unit_cost', 'f1'), question('q4', 'new_unit_cost')]);
  assert.deepEqual(answersFor(groups, {new_unit_cost: {candidateId: 'f1'}}), [
    {question_id: 'q1', accept_candidate: true}, {question_id: 'q2', reject_candidate: true},
  ]);
});
test('custom percent input is converted to the API ratio, including zero', () => {
  const groups = groupQuestions([question('q1', 'contribution_margin')]);
  assert.deepEqual(answersFor(groups, {contribution_margin: {value: '65'}}), [{question_id: 'q1', value: .65, unit: 'ratio'}]);
  assert.equal(answersFor(groups, {contribution_margin: {value: '0'}})[0].value, 0);
  for (const value of ['', '-1', '101', 'nope']) assert.throws(() => answersFor(groups, {contribution_margin: {value}}));
});
test('correction uses the candidate question when there is no missing-value question', () => {
  assert.deepEqual(answersFor(groupQuestions([question('q1', 'new_unit_cost', 'f1')]), {new_unit_cost: {value: '11'}}), [{question_id: 'q1', value: 11, unit: 'USD/unit'}]);
});
test('review never silently selects a candidate and validates month and order counts', () => {
  const groups = groupQuestions([question('q1', 'horizon')]);
  assert.throws(() => answersFor(groups, {}));
  for (const value of ['0', '61', '1.5']) assert.throws(() => answersFor(groups, {horizon: {value}}));
  assert.throws(() => answersFor(groupQuestions([question('q2', 'new_moq')]), {new_moq: {value: '1.5'}}));
});
test('folder selection excludes unsupported and hidden files while retaining nested paths', () => {
  const batch = classifyFiles([
    {name: 'quote.TXT', webkitRelativePath: 'Records/Quotes/quote.TXT', size: 50},
    {name: '.DS_Store', webkitRelativePath: 'Records/.DS_Store', size: 50},
    {name: 'photo.png', size: 50},
    {name: 'large.pdf', size: 6000000},
  ]);
  assert.equal(batch.supported.length, 2); assert.equal(batch.skipped.length, 2);
  assert.equal(batch.supported[0].path, 'Records/Quotes/quote.TXT');
  assert.ok(batch.supported[1].error);
});
test('financial values display percentages without treating ratios as money', () => {
  assert.equal(readableValue('.65', 'ratio'), '65%');
  assert.equal(readableValue('10', 'USD/unit'), '$10.00 per unit');
});
