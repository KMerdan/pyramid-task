// Mechanical projection of owned pilot logs. Excludes account/session metadata.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
function bounded(value) {
  if (typeof value !== 'string' || value.length <= 4000) return value;
  return {excerpt:value.slice(0,4000), truncated:true, original_chars:value.length,
    sha256:crypto.createHash('sha256').update(value).digest('hex')};
}
const root = '/tmp/pyramid41-hosts.7vw6LI';
const names = ['codex-baseline', 'claude-baseline', 'codex-candidate',
  'claude-candidate-initial-blocked', 'claude-candidate',
  'codex-candidate-final', 'claude-candidate-final'];
for (const name of names) {
  const file = path.join(root, name + '.jsonl');
  if (!fs.existsSync(file)) continue;
  const events = fs.readFileSync(file, 'utf8').trim().split('\n').map(JSON.parse);
  const filtered = [];
  for (const e of events) {
    if (name.startsWith('codex')) {
      if (e.type === 'item.completed' && ['command_execution', 'agent_message'].includes(e.item?.type)) {
        const {type, command, aggregated_output, exit_code, status, text} = e.item;
        filtered.push({type, command, aggregated_output:bounded(aggregated_output), exit_code, status, text});
      } else if (e.type === 'turn.completed') filtered.push({type: e.type, usage: e.usage});
      else if (['error', 'turn.failed'].includes(e.type)) filtered.push({type:e.type, error:e.error, message:e.message});
    } else {
      if (e.type === 'system' && e.subtype === 'init') {
        filtered.push({type:'native-init', model:e.model,
          plugins:e.plugins?.filter(p=>p.name==='pyramid-task'),
          inspect_skill_available:e.slash_commands?.includes('pyramid-task:inspect')});
      } else if (['assistant', 'user'].includes(e.type) && e.message?.content) {
        filtered.push({type:e.type, content:e.message.content.filter(c=>['tool_use','tool_result','text'].includes(c.type)).map(c=>
          c.type==='tool_result' ? {...c,content:typeof c.content==='string' ? bounded(c.content) : c.content?.map(x=>x.type==='text'?{...x,text:bounded(x.text)}:x)} : c)});
      } else if (e.type === 'result') {
        const {result, usage, modelUsage, duration_ms, num_turns, permission_denials, is_error} = e;
        filtered.push({type:'result', result, usage, modelUsage, duration_ms, num_turns, permission_denials, is_error});
      }
    }
  }
  const out = path.join(__dirname, name + '-trace.json');
  fs.writeFileSync(out, JSON.stringify(filtered, null, 2) + '\n');
  const finished = name.startsWith('codex') ? events.some(e=>e.type==='turn.completed') : events.some(e=>e.type==='result');
  process.stdout.write(JSON.stringify({name,finished,bytes:fs.statSync(out).size})+'\n');
}
