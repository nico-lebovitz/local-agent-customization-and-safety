import {test} from 'node:test';
import assert from 'node:assert/strict';
import {normalizeToolMessage} from '../agent/normalize_tool_output.mjs';

const warning='/bin/bash: 1: cannot create /proc/self/oom_score_adj: Permission denied\n';

test('a completed tool result survives the known launcher warning', () => {
  const payload=JSON.stringify({completed:true,result:{count:24}});
  assert.equal(normalizeToolMessage({role:'tool',content:warning+payload}).content,payload);
});

test('actual errors, unrelated policy denials and malformed output remain visible', () => {
  for (const content of [
    warning+JSON.stringify({completed:false,error:'failed to read input'}),
    warning+JSON.stringify({completed:true,result:{},error:'failure'}),
    warning+'no JSON result',
    '/health: Permission denied\n'+JSON.stringify({completed:true,result:{}}),
  ]) assert.ok(normalizeToolMessage({role:'tool',content}).content.endsWith(content));
});

test('plain discovery output retains evidence and explains the non-fatal warning', () => {
  const content = warning + 'base\nspecialist';
  const result = normalizeToolMessage({role:'tool',content}).content;
  assert.ok(result.startsWith('Launcher diagnostic:'));
  assert.ok(result.endsWith(content));
});

test('user and assistant text are never normalized as tool output', () => {
  const content=warning+JSON.stringify({completed:true,result:{}});
  for (const role of ['user','assistant']) {
    assert.equal(normalizeToolMessage({role,content}).content,content);
  }
});
