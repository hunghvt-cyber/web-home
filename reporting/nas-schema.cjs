/* Shared by Node and Apps Script. Upload to GAS as Schema.gs. */
var NasReportSchema = (function () {
  function check(ok) { if (!ok) throw new Error('INVALID_SNAPSHOT'); }
  function keys(value, expected) {
    check(value && typeof value === 'object' && !Array.isArray(value));
    check(Object.keys(value).sort().join('|') === expected.split('|').sort().join('|'));
  }
  function stamp(v) { return typeof v === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(v) && Number.isFinite(Date.parse(v)); }
  function integer(v) { return v === null || Number.isSafeInteger(v) && v >= 0; }
  function validate(d) {
    keys(d,'schema|updated_at|cam1|cam2|nas|health|maintenance|retention');
    check(d.schema === 1 && (d.updated_at === null || stamp(d.updated_at)));
    ['cam1','cam2','nas','maintenance','retention'].forEach(function(k) {
      if (k === 'retention') {
        check(d[k] && typeof d[k] === 'object' && !Array.isArray(d[k]));
        check(Object.keys(d[k]).every(function(key) {
          return ['state','measured_at','result_ref','file_count','byte_count','verification_status','evidence_collected_at'].indexOf(key) >= 0;
        }));
        check(['state','measured_at'].every(function(key) { return Object.prototype.hasOwnProperty.call(d[k], key); }));
      } else {
        keys(d[k],k === 'maintenance' ? 'state|measured_at' : 'state');
      }
      check(['ok','pass','warn','fail','unknown'].indexOf(d[k].state) >= 0);
      if (k === 'maintenance' || k === 'retention') check(d[k].measured_at === null || stamp(d[k].measured_at));
      if (k === 'retention') {
        if (Object.prototype.hasOwnProperty.call(d[k], 'result_ref')) check(typeof d[k].result_ref === 'string' && /^run-[A-Za-z0-9_-]{1,80}$/.test(d[k].result_ref));
        if (Object.prototype.hasOwnProperty.call(d[k], 'file_count')) check(integer(d[k].file_count) && d[k].file_count !== null);
        if (Object.prototype.hasOwnProperty.call(d[k], 'byte_count')) check(integer(d[k].byte_count) && d[k].byte_count !== null);
        check(Object.prototype.hasOwnProperty.call(d[k], 'file_count') === Object.prototype.hasOwnProperty.call(d[k], 'byte_count'));
        if (Object.prototype.hasOwnProperty.call(d[k], 'verification_status')) {
          check(['HISTORICALLY_VERIFIED','VERIFIED_WITH_CURRENT_EVIDENCE'].indexOf(d[k].verification_status) >= 0);
          if (d[k].verification_status === 'VERIFIED_WITH_CURRENT_EVIDENCE') {
            check(d[k].state === 'pass' && stamp(d[k].evidence_collected_at));
            check(d[k].file_count === 500 && d[k].byte_count === 3915163894);
          } else {
            check(!Object.prototype.hasOwnProperty.call(d[k], 'evidence_collected_at'));
          }
        } else {
          check(!Object.prototype.hasOwnProperty.call(d[k], 'evidence_collected_at'));
        }
      }
    });
    keys(d.health,'root|vol1|ram|swap');
    ['root','vol1'].forEach(function(k) {
      keys(d.health[k],'used_percent|available_bytes'); var p=d.health[k].used_percent;
      check(p === null || typeof p === 'number' && Number.isFinite(p) && p >= 0 && p <= 100);
      check(integer(d.health[k].available_bytes));
    });
    keys(d.health.ram,'available_bytes'); check(integer(d.health.ram.available_bytes));
    keys(d.health.swap,'used_bytes|total_bytes'); var s=d.health.swap;
    check(integer(s.used_bytes) && integer(s.total_bytes));
    check((s.used_bytes === null) === (s.total_bytes === null));
    check(s.total_bytes === null || s.total_bytes > 0 && s.used_bytes <= s.total_bytes);
    check(JSON.stringify(d).length <= 2048); return d;
  }
  return {validate:validate};
})();
if (typeof module !== 'undefined') module.exports = NasReportSchema;
