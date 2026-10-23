/* Progressive enhancement for the existing item editor. No new backend tables or APIs. */
(function () {
  'use strict';
  const studio = window.DopeListingStudio;
  const modalRoot = document.getElementById('modal-root');
  if (!studio || !modalRoot) return;

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function field(parent, title, tag, value, options) {
    const wrapper = node('label', options && options.className || '');
    const heading = node('span', '', title);
    const input = node(tag);
    if (tag === 'textarea') input.rows = 2;
    input.value = value || '';
    if (options && options.maxLength) input.maxLength = options.maxLength;
    if (options && options.placeholder) input.placeholder = options.placeholder;
    if (options && options.type) input.type = options.type;
    if (options && options.step) input.step = options.step;
    if (options && options.min) input.min = options.min;
    if (options && options.max) input.max = options.max;
    wrapper.append(heading, input);
    parent.append(wrapper);
    return input;
  }

  function select(parent, title, choices, active) {
    const wrapper = node('label');
    wrapper.append(node('span', '', title));
    const control = node('select');
    for (const [value, label] of choices) {
      const option = node('option', '', label);
      option.value = value;
      option.selected = value === active;
      control.append(option);
    }
    wrapper.append(control);
    parent.append(wrapper);
    return control;
  }

  function enhance(form) {
    if (form.dataset.studioEnhanced === 'true') return;
    form.dataset.studioEnhanced = 'true';
    const description = form.querySelector('[name="description"]');
    if (!description) return;

    let parsed;
    try { parsed = studio.read(description.value); }
    catch (error) {
      const warning = node('div', 'wide notice small', 'Listing details contain altered markers. Edit the description manually before regenerating item details.');
      description.closest('.form-block').after(warning);
      return;
    }

    const details = node('details', 'wide listing-studio');
    if (parsed.hasSection) details.open = true;
    const summary = node('summary', '', 'Fit, measurements & condition');
    summary.append(node('span', 'listing-studio-tag', 'Seller-recorded facts'));
    details.append(summary);
    details.append(node('p', 'small muted',
      'Enter only details you personally measured or inspected. This tool never verifies brand, authenticity, fabric, fit, or condition.'));

    const basics = node('div', 'listing-studio-basics');
    const group = select(basics, 'Garment type', Object.entries(studio.GROUPS), parsed.details.group);
    const units = select(basics, 'Measurement units', [['in', 'Inches'], ['cm', 'Centimeters']], parsed.details.unit);
    details.append(basics);
    details.append(node('div', 'eyebrow', 'MEASURED DIMENSIONS — OPTIONAL'));
    const measurements = node('div', 'listing-studio-measurements');
    const measurementControls = [];
    for (const definition of studio.FIELDS) {
      const control = field(measurements, definition.label, 'input', parsed.details.measurements[definition.key] || '', {
        type: 'number', min: '0.01', max: '600', step: '0.01', placeholder: 'Not measured'
      });
      control.inputMode = 'decimal';
      measurementControls.push({ definition, wrapper: control.closest('label'), control });
    }
    details.append(measurements);

    const textFields = node('div', 'listing-studio-basics');
    const material = field(textFields, 'Fabric / material (confirmed from label)', 'input', parsed.details.material,
      { maxLength: 160, placeholder: 'e.g. 100% cotton per care label' });
    const fit = field(textFields, 'Fit notes (seller observation)', 'input', parsed.details.fit,
      { maxLength: 180, placeholder: 'e.g. relaxed, boxy shape' });
    const wear = field(textFields, 'Visible wear, repairs or defects', 'textarea', parsed.details.wear,
      { maxLength: 450, className: 'listing-studio-full', placeholder: 'Describe issues honestly; do not assume an item is flawless.' });
    details.append(textFields);

    const previewWrap = node('div', 'listing-studio-preview-wrap');
    previewWrap.append(node('div', 'eyebrow', 'LIVE LISTING DETAILS'));
    const preview = node('pre', 'listing-studio-preview');
    preview.setAttribute('aria-live', 'polite');
    previewWrap.append(preview);
    details.append(previewWrap);

    const actions = node('div', 'row wrap listing-studio-actions');
    const apply = node('button', 'btn secondary small', 'Apply to description');
    apply.type = 'button';
    actions.append(apply);
    const notice = node('p', 'small muted', 'Facts are also applied when you save the item. Your other description text is kept.');
    actions.append(notice);
    details.append(actions);
    description.closest('.form-block').after(details);

    function gather() {
      const measurements = {};
      for (const row of measurementControls) measurements[row.definition.key] = row.control.value;
      return { group: group.value, unit: units.value, measurements,
        material: material.value, fit: fit.value, wear: wear.value };
    }
    function show() {
      for (const row of measurementControls) {
        row.wrapper.hidden = !row.definition.groups.includes(group.value);
      }
      try {
        preview.textContent = studio.section(gather()) ||
          'Enter a measured dimension or inspected detail to build a listing section.';
        preview.classList.remove('studio-error');
      } catch (error) {
        preview.textContent = error.message;
        preview.classList.add('studio-error');
      }
    }
    function composeIntoDescription() {
      description.value = studio.compose(description.value, gather());
      notice.textContent = 'Details applied. Save the item to keep your changes.';
      show();
    }

    let oldUnit = units.value;
    units.addEventListener('change', () => {
      if (units.value !== oldUnit && measurementControls.some(row => row.control.value.trim())) {
        if (!window.confirm('Changing units will clear the entered measurements. Continue?')) {
          units.value = oldUnit;
          return;
        }
        for (const row of measurementControls) row.control.value = '';
      }
      oldUnit = units.value;
      show();
    });
    group.addEventListener('change', show);
    details.addEventListener('input', show);
    apply.addEventListener('click', () => {
      try { composeIntoDescription(); }
      catch (error) {
        preview.textContent = error.message;
        preview.classList.add('studio-error');
        details.open = true;
      }
    });

    form.addEventListener('submit', event => {
      try { composeIntoDescription(); }
      catch (error) {
        event.preventDefault();
        event.stopImmediatePropagation();
        preview.textContent = error.message;
        preview.classList.add('studio-error');
        details.open = true;
        preview.scrollIntoView({ block: 'nearest' });
      }
    }, true);
    show();
  }

  function scan() {
    const form = modalRoot.querySelector('#item-form');
    if (form) enhance(form);
  }
  const observer = new MutationObserver(scan);
  observer.observe(modalRoot, { childList: true });
  scan();
})();
