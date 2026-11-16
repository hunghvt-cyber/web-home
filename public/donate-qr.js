/* Build VietQR locally; no transfer details are sent to a third party. */
(()=>{
 const image=document.getElementById('donate-qr-image');
 const message=document.getElementById('donate-message-input');
 const amount=document.getElementById('donate-amount-input');
 if(!image||!message||!amount)return;
 const update=()=>{
  const params=new URLSearchParams({accountName:'HOANG VU THANH HUNG',addInfo:message.value.trim()});
  const value=amount.value.trim();
  if(value&&/^[1-9]\d{0,8}$/.test(value))params.set('amount',value);
  else if(value){amount.setCustomValidity('Nhập số tiền từ 1.000 đến 999.999.999 đồng.');amount.setAttribute('aria-invalid','true');amount.reportValidity();return;}
  amount.setCustomValidity('');
  amount.removeAttribute('aria-invalid');
  image.src='https://img.vietqr.io/image/MB-566766-qr_only.svg?'+params.toString();
  image.alt='QR chuyển khoản MB'+(value?' '+Number(value).toLocaleString('vi-VN')+' đồng':'')+(message.value.trim()?' · '+message.value.trim():'');
 };
 message.addEventListener('input',update);
 amount.addEventListener('input',update);
 update();
})();
