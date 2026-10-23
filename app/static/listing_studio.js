/* Dope Stuff Listing Studio: seller-entered facts only.
 * This module never verifies condition/authenticity, guesses dimensions or posts to marketplaces.
 * The managed human-readable section lives in the existing description field, preserving
 * export/restore and avoiding a schema migration during the pilot.
 */
(function (root, factory) {
  const studio = factory();
  if (typeof module === 'object' && module.exports) module.exports = studio;
  if (root) root.DopeListingStudio = studio;
})(typeof window === 'object' ? window : null, function () {
  'use strict';

  const OPEN = '[ITEM DETAILS — SELLER PROVIDED]';
  const CLOSE = '[/ITEM DETAILS]';
  const LIMIT = 3000;
  const GROUPS = Object.freeze({
    tops: 'Tops / knitwear',
    outerwear: 'Outerwear',
    bottoms: 'Trousers / jeans',
    dresses: 'Dresses / skirts',
    footwear: 'Footwear',
    other: 'Other'
  });
  const FIELDS = Object.freeze([
    { key: 'pit_to_pit', label: 'Pit to pit', groups: ['tops', 'outerwear', 'dresses'] },
    { key: 'shoulder', label: 'Shoulder', groups: ['tops', 'outerwear', 'dresses'] },
    { key: 'sleeve', label: 'Sleeve', groups: ['tops', 'outerwear', 'dresses'] },
    { key: 'body_length', label: 'Length', groups: ['tops', 'outerwear', 'dresses', 'bottoms'] },
    { key: 'waist', label: 'Waist (flat)', groups: ['bottoms', 'dresses'] },
    { key: 'hip', label: 'Hip (flat)', groups: ['bottoms', 'dresses'] },
    { key: 'inseam', label: 'Inseam', groups: ['bottoms'] },
    { key: 'rise', label: 'Rise', groups: ['bottoms'] },
    { key: 'leg_opening', label: 'Leg opening', groups: ['bottoms'] },
    { key: 'outsole', label: 'Outsole length', groups: ['footwear'] },
    { key: 'foot_width', label: 'Sole width', groups: ['footwear'] }
  ]);

  const blank = () => ({ group: 'tops', unit: 'in', material: '', wear: '', fit: '', measurements: {} });

  function textLine(value, label, max) {
    const valueText = String(value == null ? '' : value).trim();
    if (valueText.length > max || /[\r\n\u0000-\u001f]/.test(valueText) ||
        valueText.includes(OPEN) || valueText.includes(CLOSE)) {
      throw new Error(label + ' must be a single line of at most ' + max + ' characters.');
    }
    return valueText;
  }

  function normalize(details) {
    if (!Object.prototype.hasOwnProperty.call(GROUPS, details.group)) {
      throw new Error('Select a valid garment category.');
    }
    if (!['cm', 'in'].includes(details.unit)) throw new Error('Select a valid measurement unit.');
    const result = {
      group: details.group,
      unit: details.unit,
      material: textLine(details.material, 'Fabric notes', 160),
      wear: textLine(details.wear, 'Condition notes', 450),
      fit: textLine(details.fit, 'Fit notes', 180),
      measurements: {}
    };
    for (const field of FIELDS) {
      if (!field.groups.includes(result.group)) continue;
      const raw = String((details.measurements || {})[field.key] ?? '').trim();
      if (!raw) continue;
      if (!/^\d{1,3}(?:\.\d{1,2})?$/.test(raw)) {
        throw new Error(field.label + ': enter a positive number with at most two decimals.');
      }
      const numeric = Number(raw);
      if (!Number.isFinite(numeric) || numeric <= 0 || numeric > (result.unit === 'cm' ? 600 : 240)) {
        throw new Error(field.label + ': check the measurement and selected units.');
      }
      result.measurements[field.key] = String(numeric);
    }
    return result;
  }

  function section(details) {
    const d = normalize(details);
    const relevant = FIELDS.filter(f => Object.prototype.hasOwnProperty.call(d.measurements, f.key));
    if (!relevant.length && !d.material && !d.wear && !d.fit) return '';
    const lines = [
      OPEN,
      'Garment type: ' + GROUPS[d.group]
    ];
    if (relevant.length) {
      lines.push('Measurements (approximate, taken by seller):');
      for (const field of relevant) lines.push(field.label + ': ' + d.measurements[field.key] + ' ' + d.unit);
    }
    if (d.material) lines.push('Fabric / materials: ' + d.material);
    if (d.fit) lines.push('Fit notes: ' + d.fit);
    if (d.wear) lines.push('Wear / flaws: ' + d.wear);
    lines.push(CLOSE);
    return lines.join('\n');
  }

  function split(description) {
    const original = String(description || '');
    const begin = original.indexOf(OPEN);
    if (begin < 0) return { before: original, managed: '', after: '' };
    const finish = original.indexOf(CLOSE, begin + OPEN.length);
    if (finish < 0 || original.indexOf(OPEN, begin + OPEN.length) >= 0) {
      throw new Error('The existing item details section has been manually changed. Review it before regenerating.');
    }
    return {
      before: original.slice(0, begin),
      managed: original.slice(begin, finish + CLOSE.length),
      after: original.slice(finish + CLOSE.length)
    };
  }

  function read(description) {
    const parts = split(description);
    const d = blank();
    if (!parts.managed) return { details: d, hasSection: false };
    const lines = parts.managed.split(/\r?\n/).slice(1, -1);
    for (const line of lines) {
      let recognized = false;
      if (line.startsWith('Garment type: ')) {
        const label = line.slice('Garment type: '.length);
        const found = Object.keys(GROUPS).find(k => GROUPS[k] === label);
        if (!found) throw new Error('The stored garment category was manually changed.');
        d.group = found;
        recognized = true;
      } else if (line === 'Measurements (approximate, taken by seller):') {
        recognized = true;
      } else if (line.startsWith('Fabric / materials: ')) {
        d.material = line.slice('Fabric / materials: '.length);
        recognized = true;
      } else if (line.startsWith('Wear / flaws: ')) {
        d.wear = line.slice('Wear / flaws: '.length);
        recognized = true;
      } else if (line.startsWith('Fit notes: ')) {
        d.fit = line.slice('Fit notes: '.length);
        recognized = true;
      } else {
        for (const field of FIELDS) {
          const prefix = field.label + ': ';
          if (!line.startsWith(prefix)) continue;
          const match = /^(\d+(?:\.\d{1,2})?) (cm|in)$/.exec(line.slice(prefix.length));
          if (!match) break;
          d.measurements[field.key] = match[1];
          d.unit = match[2];
          recognized = true;
          break;
        }
      }
      // Never silently replace seller prose manually added within our block.
      if (!recognized && line.trim()) {
        throw new Error('The existing item details section has manual edits. Edit its text directly before regenerating.');
      }
    }
    return { details: d, hasSection: true };
  }

  function compose(description, details) {
    const parts = split(description);
    const managed = section(details);
    const fragments = [parts.before.trim(), managed, parts.after.trim()].filter(Boolean);
    const result = fragments.join('\n\n');
    if (result.length > LIMIT) throw new Error('Description exceeds the 3,000 character limit. Shorten your notes.');
    return result;
  }

  return Object.freeze({ OPEN, CLOSE, LIMIT, GROUPS, FIELDS, blank, read, normalize, section, compose });
});
