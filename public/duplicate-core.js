// A single inventory represents one cloud and one scan scope. Never merge inventories.
export function findDuplicates(files) {
  if (!Array.isArray(files) || files.length > 200000) throw new Error('Danh sách file không hợp lệ hoặc vượt 200.000 mục.');
  const groups = new Map(), seen = new Set();
  let scanned = 0, skipped = 0;
  for (const file of files) {
    if (!file || file.IsDir) continue;
    if (typeof file.Path !== 'string' || !Number.isSafeInteger(file.Size) || file.Size < 0) { skipped++; continue; }
    const identity = typeof file.ID === 'string' && file.ID ? 'id:' + file.ID : 'path:' + file.Path;
    if (seen.has(identity)) { skipped++; continue; }
    seen.add(identity); scanned++;
    const hashes = file.Hashes || {};
    const hash = Object.entries(hashes).find(([name, value]) => /^(sha256|sha-256)$/i.test(name) && /^[a-f0-9]{64}$/i.test(value))
      || Object.entries(hashes).find(([name, value]) => /^md5$/i.test(name) && /^[a-f0-9]{32}$/i.test(value));
    if (!hash) { skipped++; continue; }
    const algorithm = /^md5$/i.test(hash[0]) ? 'MD5' : 'SHA256';
    const key = `${file.Size}:${algorithm}:${hash[1].toLowerCase()}`;
    if (!groups.has(key)) groups.set(key, {size: file.Size, algorithm, files: []});
    groups.get(key).files.push({path: file.Path, size: file.Size});
  }
  const duplicates = [...groups.values()].filter(group => group.files.length > 1)
    .map(group => ({...group, reclaimable: group.size * (group.files.length - 1)}))
    .sort((a, b) => b.reclaimable - a.reclaimable);
  return {scanned, skipped, groups: duplicates, reclaimable: duplicates.reduce((sum, group) => sum + group.reclaimable, 0)};
}
