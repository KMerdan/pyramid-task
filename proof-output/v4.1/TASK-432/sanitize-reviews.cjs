const fs=require('fs'), path=require('path'), crypto=require('crypto');
function bounded(v) {
  return typeof v==='string'&&v.length>4000 ? {excerpt:v.slice(0,4000),truncated:true,
    original_chars:v.length,sha256:crypto.createHash('sha256').update(v).digest('hex')} : v;
}
for(const name of ['independent-review','focused-review']) {
  const events=fs.readFileSync('/tmp/pyramid41-hosts.7vw6LI/'+name+'.jsonl','utf8').trim().split('\n').map(JSON.parse);
  const out=[];
  for(const e of events) {
    if(e.type==='system'&&e.subtype==='init')out.push({type:'native-init',model:e.model,
      plugins:e.plugins?.filter(p=>p.name==='pyramid-task'),audit_skill_available:e.slash_commands?.includes('pyramid-task:audit')});
    else if(['assistant','user'].includes(e.type)&&e.message?.content)out.push({type:e.type,
      content:e.message.content.filter(c=>['text','tool_use','tool_result'].includes(c.type)).map(c=>
        c.type==='tool_result'?{...c,content:typeof c.content==='string'?bounded(c.content):c.content?.map(x=>x.type==='text'?{...x,text:bounded(x.text)}:x)}:c)});
    else if(e.type==='result')out.push({type:'result',result:e.result,usage:e.usage,
      duration_ms:e.duration_ms,num_turns:e.num_turns,permission_denials:e.permission_denials});
  }
  fs.writeFileSync(path.join(__dirname,name+'-trace.json'),JSON.stringify(out,null,2)+'\n');
  const tool_count=events.flatMap(e=>e.type==='assistant'?e.message.content.filter(c=>c.type==='tool_use'):[]).length;
  process.stdout.write(JSON.stringify({name,tool_count,finished:events.some(e=>e.type==='result')})+'\n');
}
