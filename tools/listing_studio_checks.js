/* Deterministic standalone Listing Studio checks. Run: node tools/listing_studio_checks.js */
const assert = require('node:assert/strict');
const studio = require('../app/static/listing_studio.js');

function facts(overrides = {}) {
  return {group:'outerwear',unit:'in',material:'100% cotton per care tag',
    wear:'Small abrasion on left cuff',fit:'Boxy shape',
    measurements:{pit_to_pit:'22.50',sleeve:'25',body_length:'26'},...overrides};
}

const base = 'Vintage work jacket in navy. Photos are of the actual garment.';
const output = studio.compose(base, facts());
assert(output.startsWith(base));
assert(output.includes('Pit to pit: 22.5 in'));
assert(output.includes('Sleeve: 25 in'));
assert(output.includes('Wear / flaws: Small abrasion on left cuff'));
assert(output.includes('Fabric / materials: 100% cotton per care tag'));
assert(!output.includes('authentic'), 'No AI-invented authentication claims');
assert.equal(studio.compose(output, facts()), output, 'Reapplying details must not duplicate them');

const recovered = studio.read(output);
assert.equal(recovered.hasSection,true);
assert.equal(recovered.details.group,'outerwear');
assert.equal(recovered.details.unit,'in');
assert.equal(recovered.details.measurements.pit_to_pit,'22.5');
assert.equal(recovered.details.wear,'Small abrasion on left cuff');

const more = output + '\n\nShips in protective packaging.';
const updated = studio.compose(more,facts({wear:'Stitched repair at left cuff'}));
assert(updated.endsWith('Ships in protective packaging.'));
assert(updated.includes('Stitched repair at left cuff'));
assert(!updated.includes('Small abrasion on left cuff'));
assert.equal(updated.split(studio.OPEN).length,2);

assert.equal(studio.compose(base,studio.blank()),base);
assert.equal(studio.compose(output,studio.blank()),base, 'Clearing the wizard only removes its own block');

const cm = studio.compose('Shoes.',facts({group:'footwear',unit:'cm',material:'',
  fit:'',wear:'',measurements:{outsole:'29.5',foot_width:'10'}}));
assert(cm.includes('Outsole length: 29.5 cm'));
assert(!cm.includes('Pit to pit:'), 'Do not carry incompatible category fields');

function mustFail(fn,fragment) {
  assert.throws(fn, err => err instanceof Error && err.message.includes(fragment));
}
mustFail(()=>studio.compose(base,facts({unit:'yard'})),'measurement unit');
mustFail(()=>studio.compose(base,facts({measurements:{pit_to_pit:'0'}})),'Pit to pit');
mustFail(()=>studio.compose(base,facts({measurements:{pit_to_pit:'300'}})),'Pit to pit');
mustFail(()=>studio.compose(base,facts({measurements:{pit_to_pit:'2e2'}})),'Pit to pit');
mustFail(()=>studio.compose(base,facts({wear:'In good shape\nAuthenticity guaranteed'})),'single line');
mustFail(()=>studio.compose(base,facts({material:studio.OPEN})),'single line');
mustFail(()=>studio.compose('a'.repeat(2980),facts()),'3,000 character');
mustFail(()=>studio.compose(base+'\n'+studio.OPEN+'\nOops',facts()),'manually changed');
mustFail(()=>studio.compose(base, facts({group:'injected'})),'garment category');

// The browser uses this module, while persistence continues through the normal
// authenticated item API and account backup; no shadow database is introduced.
console.log('LISTING STUDIO CHECKS PASSED');
