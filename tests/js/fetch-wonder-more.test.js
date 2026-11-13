// Run: node --test tests/js/fetch-wonder-more.test.js
// Checks the CDC WONDER download script for the added indicators against a mock request form,
// so the categories it sends can be reviewed without a CDC WONDER session.
const test = require('node:test');
const assert = require('node:assert');
const W = require('../../scripts/fetch_wonder_more.js');

const opts = (pairs) => ({ options: pairs.map(([value, text]) => ({ value, text })) });
const months = [['00', 'No prenatal care'], ...Array.from({ length: 10 }, (_, i) => [String(i + 1).padStart(2, '0'),
  `${i + 1}${['st', 'nd', 'rd'][i] || 'th'} month`]), ['99', 'Unknown or Not Stated']];
const yesno = [['*All*', 'All'], ['1', 'Yes'], ['2', 'No'], ['9', 'Unknown or Not Stated']];
const FORM = {
  elements: {
    B_1: opts([['*None*', 'None'], ['D149.V21-level1', 'State of Residence'], ['D149.V21-level2', 'County of Residence'],
      ['D149.V20', 'Year'], ['D149.V8', 'Month Prenatal Care Began'], ['D149.V9', 'Infant Birth Weight 12'],
      ['D149.V32', 'OE Gestational Age Recode 10'], ['D149.V17', 'Gestational Hypertension'], ['D149.V49', "Mother's Single Race 15"],
      ['D149.V110', 'Source of Payment for Delivery'], ['D149.V71', "Mother's Pre-pregnancy BMI"], ['D149.V18', 'Gestational Diabetes'],
      ['D149.V10', 'Tobacco Use'], ['D149.V12', 'Delivery Method'], ['D149.V13', 'Live Birth Order'], ['D149.V14', 'Plurality'],
      ['D149.V15', 'Fetal Presentation'], ['D149.V43', "Mother's Hispanic Origin"]]),
    'V_D149.V8': opts([['*All*', 'All'], ...months]),
    'V_D149.V9': opts([['*All*', 'All'], ['01', '499 grams or less'], ['02', '500 - 999 grams'], ['03', '1000 - 1499 grams'],
      ['04', '1500 - 1999 grams'], ['05', '2000 - 2499 grams'], ['06', '2500 - 2999 grams'], ['07', '3000 - 3499 grams'],
      ['08', '3500 - 3999 grams'], ['09', '4000 - 4499 grams'], ['10', '4500 - 4999 grams'], ['11', '5000 - 8165 grams'], ['99', 'Unknown or Not Stated']]),
    'V_D149.V32': opts([['*All*', 'All'], ['01', 'Under 20 weeks'], ['02', '20 - 27 weeks'], ['03', '28 - 31 weeks'], ['04', '32 - 33 weeks'],
      ['05', '34 - 36 weeks'], ['06', '37 - 38 weeks'], ['07', '39 weeks'], ['08', '40 weeks'], ['09', '41 weeks or more'], ['99', 'Unknown or Not Stated']]),
    'V_D149.V17': opts(yesno), 'V_D149.V18': opts(yesno), 'V_D149.V10': opts(yesno),
    'V_D149.V71': opts([['*All*', 'All'], ['1', 'Underweight <18.5'], ['2', 'Normal 18.5-24.9'], ['3', 'Overweight 25.0-29.9'],
      ['4', 'Obesity I 30.0-34.9'], ['5', 'Obesity II 35.0-39.9'], ['6', 'Extreme Obesity III >39.9'], ['9', 'Unknown or Not Stated']]),
    'V_D149.V12': opts([['*All*', 'All'], ['1', 'Vaginal'], ['2', 'Cesarean'], ['9', 'Unknown or Not Stated']]),
    'V_D149.V13': opts([['*All*', 'All'], ['1', '1'], ['2', '2'], ['3', '3'], ['8', '8 or more'], ['99', 'Unknown or Not Stated']]),
    'V_D149.V14': opts([['*All*', 'All'], ['1', 'Single'], ['2', 'Twin'], ['3', 'Triplet or more']]),
    'V_D149.V15': opts([['*All*', 'All'], ['1', 'Cephalic'], ['2', 'Breech'], ['3', 'Other'], ['9', 'Unknown or Not Stated']]),
    'V_D149.V110': opts([['*All*', 'All'], ['1', 'Medicaid'], ['2', 'Private Insurance'], ['3', 'Self Pay'], ['4', 'Other'], ['9', 'Unknown or Not Stated']]),
    'V_D149.V43': opts([['*All*', 'All'], ['1', 'Hispanic or Latino'], ['2', 'Not Hispanic or Latino'], ['9', 'Unknown or Not Stated']]),
    'V_D149.V49': opts([['*All*', 'All'], ['1', 'White'], ['2', 'Black'], ['4', 'Asian Indian'], ['5', 'Chinese'], ['11', 'Hawaiian']]),
  },
  querySelectorAll: () => [{ name: 'O_prenatal', value: 'D149.V8' }, { name: 'O_oe_gestation', value: 'D149.V32' }],
};

test('finds every variable and the categories each indicator uses', () => {
  const R = W.resolve(FORM);
  assert.deepEqual(R.missing, []);
  assert.equal(R.vars.prenatal.radio, 'O_prenatal');
  assert.equal(R.vars.bmi.code, 'D149.V71');
  const { plan, problems } = W.plan(R);
  assert.deepEqual(problems, []);
  const lab = k => plan[k].numLabels;
  assert.deepEqual(lab('no_first_trimester_care'), ['No prenatal care', ...months.slice(4, 11).map(m => m[1])]);
  assert.deepEqual(lab('late_no_prenatal_care'), ['No prenatal care', '7th month', '8th month', '9th month', '10th month']);
  assert.equal(plan.no_first_trimester_care.den.length, 11);  // unknown left out
  assert.deepEqual(lab('prepregnancy_obesity'), ['Obesity I 30.0-34.9', 'Obesity II 35.0-39.9', 'Extreme Obesity III >39.9']);
  assert.equal(lab('prepregnancy_overweight_obesity').length, 4);
  assert.deepEqual(plan.prepregnancy_obesity.denLabels.length, 6);
  assert.deepEqual(lab('preterm_birth'), ['Under 20 weeks', '20 - 27 weeks', '28 - 31 weeks', '32 - 33 weeks', '34 - 36 weeks']);
  assert.equal(plan.preterm_birth.den.length, 9);
  assert.equal(lab('low_birth_weight').length, 5);
  assert.deepEqual(lab('ntsv_cesarean'), ['Cesarean']);
  assert.deepEqual(plan.ntsv_cesarean.denLabels, ['Vaginal', 'Cesarean']);
  const L = plan.ntsv_cesarean.limits;
  assert.deepEqual(L.lbo.labels, ['1']);
  assert.deepEqual(L.plurality.labels, ['Single']);
  assert.deepEqual(L.presentation.labels, ['Cephalic']);
  assert.deepEqual(L.oe10.labels, ['37 - 38 weeks', '39 weeks', '40 weeks', '41 weeks or more']);
});

test('stops when a variable is not on the form', () => {
  const f = { ...FORM, elements: { ...FORM.elements, B_1: opts(FORM.elements.B_1.options.filter(o => o.text !== 'Tobacco Use').map(o => [o.value, o.text])) } };
  const R = W.resolve(f);
  assert.equal(R.missing.length, 1);
  assert.match(R.missing[0], /tobacco/);
  assert.match(W.plan(R).problems.join(), /smoking_during_pregnancy/);
});

const EXPORT = ['"Notes"\t"County of Residence"\t"County of Residence Code"\t"Year"\t"Year Code"\t"Births"',
  '\t"Middlesex County, MA"\t"25017"\t"2023"\t"2023"\t"4000"',
  '\t"Unidentified Counties, MA"\t"25999"\t"2023"\t"2023"\t"900"',
  '\t"Suffolk County, MA"\t"25025"\t"2023"\t"2023"\t"Suppressed"',
  '"Total"\t\t\t\t\t"4900"',
  '"---"', '"Dataset: Natality, 2016-2024 expanded"', '"Query Parameters:"', '"Live Birth Order: 1"', '"Plurality: Single"',
  '"Fetal Presentation: Cephalic"', '"OE Gestational Age Recode 10: 37 - 38 weeks; 39 weeks; 40 weeks; 41 weeks or more"', '"---"'].join('\n');

test('parses an export, drops unidentified counties and keeps suppressed counts empty', () => {
  const e = W.parseExport(EXPORT);
  assert.equal(e.rows.length, 3);
  const N = W.keyed(W.parseExport(EXPORT.replace('"4000"', '"1000"')));
  const rows = W.tidyRows(N, W.keyed(e), 'ntsv_cesarean', 'county');
  assert.deepEqual(rows, ['25017,"Middlesex County",MA,2023,ntsv_cesarean,"All",1000,4000',
    '25025,"Suffolk County",MA,2023,ntsv_cesarean,"All",,']);
  const { plan } = W.plan(W.resolve(FORM));
  assert.doesNotThrow(() => W.checkLimits(e.footer, plan.ntsv_cesarean.limits));
  const noLimit = W.parseExport(EXPORT.replace('"Plurality: Single"\n', ''));
  assert.throws(() => W.checkLimits(noLimit.footer, plan.ntsv_cesarean.limits), /Plurality/);
});

test('state rows use two-letter codes and labelled groups', () => {
  const e = W.parseExport(['"Notes"\t"State of Residence"\t"State of Residence Code"\t"Year"\t"Year Code"\t"Mother\'s Hispanic Origin"\t"Mother\'s Hispanic Origin Code"\t"Births"',
    '\t"New Hampshire"\t"33"\t"2023"\t"2023"\t"Hispanic or Latino"\t"1"\t"700"',
    '\t"New Hampshire"\t"33"\t"2023"\t"2023"\t"Unknown or Not Stated"\t"9"\t"40"', '"---"'].join('\n'));
  const rows = W.tidyRows(W.keyed(e, 1), W.keyed(e, 1), 'gestational_diabetes', 'state', g => 'Hispanic origin: ' + g);
  assert.deepEqual(rows, ['NH,"New Hampshire",NH,2023,gestational_diabetes,"Hispanic origin: Hispanic or Latino",700,700']);
});
