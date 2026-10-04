// Reproducible source identity; no host authentication or private history input.
const fs=require('fs'), path=require('path'), crypto=require('crypto');
const staging='/tmp/pyramid41-hosts.7vw6LI';
function manifest(root) {
  const rows=[];
  function walk(dir,rel='') {
    for (const ent of fs.readdirSync(dir,{withFileTypes:true})) {
      if(ent.name==='__pycache__'||ent.name.endsWith('.pyc')) continue;
      const r=path.join(rel,ent.name);
      if(ent.isDirectory()) walk(path.join(dir,ent.name),r);
      else if(ent.isFile()) rows.push({path:r,sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(dir,ent.name))).digest('hex')});
    }
  }
  walk(root); rows.sort((a,b)=>a.path.localeCompare(b.path));
  return {root,files:rows.length,digest:crypto.createHash('sha256').update(rows.map(r=>r.sha256+'  '+r.path+'\n').join('')).digest('hex'),rows};
}
const sources={baseline:manifest(path.join(staging,'baseline')),
  source:manifest(path.resolve('plugins/pyramid-task')),
  codex:manifest(path.join(staging,'codex-candidate-final/package')),
  claude:manifest(path.join(staging,'claude-candidate-final/package'))};
if(sources.source.digest!==sources.codex.digest||sources.source.digest!==sources.claude.digest) throw Error('Candidate source differs from host package');
fs.writeFileSync(path.join(__dirname,'package-identity.json'),JSON.stringify({algorithm:'SHA256 of sorted per-file SHA256 + two spaces + relative path + LF; localeCompare ordering; excludes Python bytecode',sources},null,2)+'\n');
process.stdout.write(JSON.stringify(Object.fromEntries(Object.entries(sources).map(([k,v])=>[k,{digest:v.digest,files:v.files}]))));
