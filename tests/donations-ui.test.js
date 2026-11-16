import test from 'node:test';import assert from 'node:assert/strict';import {JSDOM} from 'jsdom';import {readFileSync} from 'node:fs';
const template=readFileSync('scripts/templates/cat-desk.html','utf8'),script=readFileSync('public/donate-qr.js','utf8');
test('homepage removes incoming money statistics and transaction history',()=>{
 assert.doesNotMatch(template,/donate-earned|donate-history|donate-connection|id="donate-amount"|donations\.js|feed=donations/);
 assert.match(template,/cat-terminal[^]*mèo@homepage:~/);
});
test('QR updates locally with the entered message and optional amount',()=>{
 const dom=new JSDOM(template,{runScripts:'outside-only',url:'https://homepage.test/'}),w=dom.window;
 w.eval(script);
 const message=w.document.getElementById('donate-message-input'),amount=w.document.getElementById('donate-amount-input'),image=w.document.getElementById('donate-qr-image');
 message.value='Mua pate cho Chiken';message.dispatchEvent(new w.Event('input'));
 let url=new URL(image.src);assert.equal(url.hostname,'img.vietqr.io');assert.equal(url.searchParams.get('addInfo'),'Mua pate cho Chiken');assert.equal(url.searchParams.get('accountName'),'HOANG VU THANH HUNG');assert.equal(url.searchParams.has('amount'),false);
 amount.value='50000';amount.dispatchEvent(new w.Event('input'));url=new URL(image.src);assert.equal(url.searchParams.get('amount'),'50000');
 amount.value='100';amount.dispatchEvent(new w.Event('input'));assert.equal(image.src,url.href.replace('amount=50000','amount=100'));assert.equal(amount.value,'100');
 dom.window.close();
});
