import test from 'node:test';
import assert from 'node:assert/strict';
import retired from '../lib/retired-notes.js';
import {readFileSync,existsSync} from 'node:fs';

test('all deployed legacy endpoints stop before storage, for reads and writes', async()=>{
 for(const path of ['notes','notes-save','note-share','shared-note','shared-folder']) {
  assert.equal((await import('../api/'+path+'.js')).default,retired);
  for(const method of ['GET','POST','DELETE']) {
   const res={setHeader(){},status(n){assert.equal(n,410);return this;},json(body){assert.equal(body.code,'NOTES_RETIRED');}};
   retired({method},res);
  }
 }
});
test('built pages expose Koofr and retire old shares without forwarding their tokens',()=>{
 assert.equal(existsSync('dist/notes/index.html'),false);
 const routing=JSON.parse(readFileSync('vercel.json','utf8'));
 assert.equal(routing.rewrites.find(r=>r.source==='/notes/:path*').destination,'https://hunghvt-notes.vercel.app/:path*');
 for(const path of ['share','workspace']) assert.doesNotMatch(readFileSync('dist/'+path+'/index.html','utf8'),/location.replace|textarea|account.js/);
 for(const name of ['notes','shared-note','workspace','checklist']) assert.equal(existsSync('dist/'+name+'.js'),false);
});

