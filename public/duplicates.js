import {findDuplicates} from './duplicate-core.js';
const $ = id => document.getElementById(id);
const cloud = $('duplicate-cloud'), input = $('duplicate-inventory');
let generation = 0, groups = [], shown = 0;
const bytes = value => new Intl.NumberFormat('vi-VN', {maximumFractionDigits: 2}).format(value / 1024 / 1024) + ' MiB';
function clear() {
  generation++; groups = []; shown = 0;
  $('duplicate-results').hidden = true;
  $('duplicate-groups').replaceChildren();
  $('duplicate-more').hidden = true;
  $('duplicate-status').textContent = 'Chưa có dữ liệu quét.';
}
cloud.addEventListener('change', () => {input.value = ''; clear();});
input.addEventListener('change', clear);
function showMore() {
  for (const group of groups.slice(shown, shown + 50)) {
    const details = document.createElement('details'); details.className = 'duplicate-group';
    const summary = document.createElement('summary');
    summary.textContent = `${group.files.length} bản · ${bytes(group.size)}/file · dư ${bytes(group.reclaimable)} · ${group.algorithm}`;
    details.append(summary);
    details.addEventListener('toggle', () => {
      if (!details.open || details.querySelector('ol')) return;
      const list = document.createElement('ol');
      for (const file of group.files) {const item = document.createElement('li'); item.textContent = file.path; list.append(item);}
      details.append(list);
    });
    $('duplicate-groups').append(details);
  }
  shown = Math.min(shown + 50, groups.length);
  $('duplicate-more').hidden = shown === groups.length;
}
$('duplicate-more').addEventListener('click', showMore);
$('duplicate-form').addEventListener('submit', async event => {
  event.preventDefault(); clear();
  const file = input.files[0]; if (!file) return;
  const id = generation, selectedCloud = cloud.options[cloud.selectedIndex].text;
  $('duplicate-submit').disabled = true;
  $('duplicate-status').textContent = 'Đang đọc danh sách…';
  try {
    if (file.size > 30 * 1024 * 1024) throw new Error('File vượt 30 MiB. Hãy quét từng thư mục nhỏ hơn.');
    const inventory = JSON.parse(await file.text());
    if (id !== generation) return;
    const result = findDuplicates(inventory);
    groups = result.groups;
    $('duplicate-summary').textContent = `${selectedCloud} · ${result.scanned.toLocaleString('vi-VN')} file · ${groups.length.toLocaleString('vi-VN')} nhóm trùng · dư ${bytes(result.reclaimable)}`;
    $('duplicate-results').hidden = false; showMore();
    $('duplicate-status').textContent = `${file.name}: đã phân tích. ${result.skipped.toLocaleString('vi-VN')} mục bị bỏ qua (thiếu checksum, không hợp lệ hoặc lặp bản ghi). ${groups.length ? '' : 'Không tìm thấy nhóm trùng có checksum phù hợp.'}`;
  } catch (error) {
    if (id === generation) $('duplicate-status').textContent = error instanceof SyntaxError ? 'File JSON không hợp lệ; chưa có kết quả.' : error.message;
  } finally { $('duplicate-submit').disabled = false; }
});
