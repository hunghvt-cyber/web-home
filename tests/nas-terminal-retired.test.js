import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync, readFileSync} from 'node:fs';
import {createAuthHandler} from '../api/auth.js';

test('web terminal page is removed and its former API returns 410',async()=>{
 assert.equal(existsSync('dist/nas/terminal/index.html'),false);
 assert.equal(existsSync('dist/vendor/xterm.js'),false);
 const req={method:'POST',query:{service:'terminal'},headers:{}};
 const res={headers:{},setHeader(k,v){this.headers[k]=v;},status(n){this.code=n;return this;},json(value){this.value=value;return value;}};
 await createAuthHandler()(req,res);
 assert.equal(res.code,410);
 assert.match(res.value.error,/ngừng hoạt động/);
});

test('homepage retains reports and Gemini shortcut without a NAS terminal shortcut',()=>{
 const html=readFileSync('dist/index.html','utf8');
 for(const phrase of ['Camera & dung lượng NAS','Đánh giá sức khỏe NAS','Google Drive → Koofr','Google Photos → Koofr'])assert.ok(html.includes(phrase));
 assert.ok(html.includes('href="/gemini/"'));
 assert.ok(!html.includes('/nas/terminal/'));
});
