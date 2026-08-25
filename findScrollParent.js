// ============================================================
// Evernote Web — Oldest Note Per Notebook
// Paste this whole script into the browser Console tab while
// on web.evernote.com / www.evernote.com/client/web, then press Enter.
// ============================================================

// ============================================================
// Error logging -- captures errors instead of relying on scrolling
// through noisy console output. Downloaded as a separate text file
// alongside the CSV when the run finishes.
// ============================================================
const scriptErrors = [];

function logError(context, err) {
  const msg = err && err.stack ? err.stack : String(err);
  const entry = `[${new Date().toISOString()}] ${context}: ${msg}`;
  scriptErrors.push(entry);
  console.error(entry);
}

window.addEventListener('error', (e) => logError('window.onerror', e.error || e.message));
window.addEventListener('unhandledrejection', (e) => logError('unhandledrejection', e.reason));

function downloadTextFile(filename, content) {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }

function findScrollParent(startEl) {
  let el = startEl;
  while (el && el !== document.body) {
    const s = getComputedStyle(el);
    if (/(auto|scroll)/.test(s.overflowY)) return el;
    el = el.parentElement;
  }
  return null;
}

async function waitForNoteRow(timeoutMs = 3000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const row = document.querySelector('[id$="_qa-NOTES_SIDEBAR_NOTE"]');
    if (row) return row;
    await wait(150);
  }
  return null;
}

function parseNoteDate(text) {
  if (!text) return null;
  const hasYear = /\d{4}/.test(text);
  const str = hasYear ? text : `${text}, ${new Date().getFullYear()}`;
  const d = new Date(str);
  return isNaN(d.getTime()) ? null : d;
}

function shouldSkipNotebook(name, stackName) {
  const exactSkips = ['Admin - Topics', 'Admin', '.Non Java', '.Scripting', 'A.I.'];
  if (exactSkips.includes(name)) return true;
  if (stackName && exactSkips.includes(stackName)) return true; // skip children of skipped stacks too
  if (/^\(Test\)/i.test(name)) return true;      // e.g. "(Test) EV Auto"
  if (/^\(Imported\)/i.test(name)) return true;  // e.g. "(Imported) JWT"
  return false;
}

function getRowTop(el) {
  const li = el.closest('li.rv-sticky-leaf-node') || el.closest('li');
  if (!li) return null;
  const m = /top:\s*([\d.]+)px/.exec(li.getAttribute('style') || '');
  return m ? parseFloat(m[1]) : null;
}

async function expandAllVisibleStacks(handledStackNames) {
  // Don't snapshot all stacks upfront -- expanding one stack shifts
  // layout and can cause the virtualized list to unmount stacks further
  // down, making any pre-captured references to them go stale/detached.
  // Instead, re-query live and handle exactly one new stack per pass.
  let progressMade = true;
  let safety = 0;
  while (progressMade && safety < 200) {
    progressMade = false;
    safety++;

    const stackTitles = [...document.querySelectorAll('#qa-NOTEBOOK_STACK_TITLE')];
    const titleEl = stackTitles.find(t => !handledStackNames.has(t.textContent.trim()));
    if (!titleEl) break;

    const name = titleEl.textContent.trim();
    handledStackNames.add(name);
    progressMade = true;

    try {
      const stackBtn = titleEl.closest('[role="treeitem"]');
      if (!stackBtn) {
        logError(`Stack "${name}"`, 'Title element had no treeitem ancestor (likely detached mid-loop) -- skipped.');
        continue;
      }

      // Click the inner toggle chevron specifically -- the outer row
      // itself may have no click handler attached (that pattern seems
      // to only apply to real notebooks, not stacks).
      const toggleEl = stackBtn.querySelector('#qa-NAV_NOTEBOOKS_TOGGLE_EXPAND_COLLAPSE') || stackBtn;

      const countBefore = document.querySelectorAll('[id^="qa-NAV_NOTEBOOK_"]').length;
      toggleEl.click();
      await wait(350);
      const countAfter = document.querySelectorAll('[id^="qa-NAV_NOTEBOOK_"]').length;
      let restored = false;
      if (countAfter <= countBefore) {
        // Count didn't grow -- we likely just collapsed an already-open
        // stack (or it's genuinely empty). Toggle back to be safe.
        toggleEl.click();
        await wait(350);
        restored = true;
      }
      const countFinal = document.querySelectorAll('[id^="qa-NAV_NOTEBOOK_"]').length;
      const line = `STACK "${name}": before=${countBefore} afterFirstClick=${countAfter} restored=${restored} final=${countFinal}`;
      console.log(line);
      scriptErrors.push(line); // also captured in the downloadable log, not just console
    } catch (err) {
      logError(`Stack "${name}"`, err);
    }
  }
}

// Processes each real notebook the moment it's found while scrolling,
// so we never rely on re-finding a virtualized-away element later.
async function processAllNotebooks(onNotebook) {
  const handledStackNames = new Set();
  await expandAllVisibleStacks(handledStackNames);

  const processed = new Set();
  let currentStackName = null; // persisted across the whole scan

  function getScrollParentFresh() {
    const anyNb = document.querySelector('[id^="qa-NAV_NOTEBOOK_"]');
    return findScrollParent(anyNb);
  }

  async function processVisible() {
    // Combine stacks + notebooks in visual (top-position) order so we
    // can track which stack each notebook currently belongs to.
    const stackEntries = [...document.querySelectorAll('#qa-NOTEBOOK_STACK_TITLE')].map(titleEl => ({
      type: 'stack',
      top: getRowTop(titleEl),
      name: titleEl.textContent.trim()
    }));
    const notebookEntries = [...document.querySelectorAll('[id^="qa-NAV_NOTEBOOK_"]')].map(a => {
      const guid = a.id.replace('qa-NAV_NOTEBOOK_', '');
      const titleEl = a.querySelector('#qa-NOTEBOOK_TITLE, [id$="NOTEBOOK_TITLE"]');
      return {
        type: 'notebook',
        top: getRowTop(a),
        guid,
        name: titleEl?.textContent?.trim() || '(unnamed)'
      };
    });

    const combined = [...stackEntries, ...notebookEntries]
      .filter(e => e.top !== null)
      .sort((a, b) => a.top - b.top);

    for (const entry of combined) {
      if (entry.type === 'stack') {
        currentStackName = entry.name;
        continue;
      }
      if (processed.has(entry.guid)) continue;
      processed.add(entry.guid);
      await onNotebook({ guid: entry.guid, name: entry.name, stackName: currentStackName });
    }
  }

  let scrollParent = getScrollParentFresh();
  if (!scrollParent) {
    await processVisible();
    return;
  }

  scrollParent.scrollTop = 0;
  await wait(200);
  await expandAllVisibleStacks(handledStackNames);
  await processVisible();

  const MAX_STEPS = 300;
  let steps = 0;
  while (steps < MAX_STEPS) {
    steps++;
    // Re-fetch fresh each iteration -- a notebook click may have just
    // happened inside processVisible(), possibly remounting this element.
    scrollParent = getScrollParentFresh();
    if (!scrollParent) {
      logError('processAllNotebooks', `Sidebar scroll container not found at step ${steps} -- stopping notebook scan early. Processed so far: ${processed.size}`);
      break;
    }
    console.log(`step ${steps}: scrollTop=${scrollParent.scrollTop} clientHeight=${scrollParent.clientHeight} scrollHeight=${scrollParent.scrollHeight} processedSoFar=${processed.size}`);

    const atBottom = scrollParent.scrollTop + scrollParent.clientHeight >= scrollParent.scrollHeight - 5;
    if (atBottom) {
      await wait(400); // settle wait for late-rendering rows / stack expansion growth
      await expandAllVisibleStacks(handledStackNames);
      await processVisible();
      scrollParent = getScrollParentFresh();
      const stillAtBottom = scrollParent && (scrollParent.scrollTop + scrollParent.clientHeight >= scrollParent.scrollHeight - 5);
      if (stillAtBottom) {
        logError('processAllNotebooks', `Stopped at step ${steps} because bottom-of-list was reached. Processed so far: ${processed.size}. Final scrollTop=${scrollParent?.scrollTop} clientHeight=${scrollParent?.clientHeight} scrollHeight=${scrollParent?.scrollHeight}`);
        break;
      }
      continue;
    }
    scrollParent.scrollTop += scrollParent.clientHeight * 0.6;
    await wait(300);
    await expandAllVisibleStacks(handledStackNames);
    await processVisible();
  }

  scriptErrors.push(`Final handled stack list (${handledStackNames.size}): ${[...handledStackNames].join(', ')}`);
}

async function collectNotesInCurrentNotebook() {
  let noteRow = await waitForNoteRow();

  if (!noteRow) {
    // Possibly stuck in List view from a prior notebook. Try forcing
    // Snippets view via the sort menu, then give it one more chance.
    logError('collectNotesInCurrentNotebook', 'No note row found initially -- attempting Snippets-view recovery.');
    const sortBtnRecovery = [...document.querySelectorAll('button')]
      .find(b => b.getAttribute('aria-label') === 'Sort and display options');
    if (sortBtnRecovery) {
      sortBtnRecovery.click();
      await wait(400);
      const snippetsOptRecovery = document.querySelector('#SNIPPETS');
      if (snippetsOptRecovery) {
        snippetsOptRecovery.click();
        await wait(500);
      } else {
        // Close the menu if we can't find the option, to avoid leaving it open
        document.body.click();
      }
    }
    noteRow = await waitForNoteRow();
    if (!noteRow) {
      logError('collectNotesInCurrentNotebook', 'Still no note row found after recovery attempt -- treating as empty.');
      return [];
    }
  }

  const sortBtn = [...document.querySelectorAll('button')]
    .find(b => b.getAttribute('aria-label') === 'Sort and display options');
  if (sortBtn) {
    sortBtn.click();
    await wait(400);

    // Defensive: make sure we're in Snippets (card) view, not List (table)
    // view -- our selectors only match Snippets markup. If the view has
    // drifted to List for any reason, force it back before sorting.
    const snippetsOpt = document.querySelector('#SNIPPETS');
    if (snippetsOpt && snippetsOpt.getAttribute('data-is-selected') !== 'true') {
      logError('collectNotesInCurrentNotebook', 'View was not set to Snippets -- forcing it back.');
      snippetsOpt.click();
      await wait(400);
      // Re-open the sort menu since clicking View as may have closed it
      sortBtn.click();
      await wait(400);
    }

    const updatedOpt = document.querySelector('#sort_by_date_updated');
    if (updatedOpt) {
      updatedOpt.click();
    } else {
      logError('collectNotesInCurrentNotebook', 'sort_by_date_updated option not found in menu -- sort may not have been applied.');
    }
    await wait(600);
  }

  const scrollParent = findScrollParent(noteRow) || noteRow.closest('ul, div');
  const seen = new Map();

  function collectVisible() {
    document.querySelectorAll('button[id$="_qa-NOTES_SIDEBAR_NOTE"]').forEach(btn => {
      const id = btn.id.split('_qa-NOTES_SIDEBAR_NOTE')[0];
      if (seen.has(id)) return;
      const titleEl = btn.querySelector('[id$="_TITLE"] span');
      const dateEl = btn.querySelector('[id$="_UPDATED"]');
      const pinned = !!btn.querySelector('[id$="_TITLE"] svg');
      seen.set(id, {
        title: titleEl?.textContent?.trim() || '(untitled)',
        dateText: dateEl?.textContent?.trim() || '',
        pinned
      });
    });
  }

  if (!scrollParent) {
    collectVisible();
    return [...seen.values()];
  }

  scrollParent.scrollTop = 0;
  await wait(300);
  collectVisible();

  // Only stop once genuinely at the bottom -- never on a transient
  // "no new notes this step" reading, since that can happen mid-list
  // if rendering lags behind the scroll. A max step cap is a safety
  // net only, not the normal exit path.
  const MAX_STEPS = 300;
  let steps = 0;
  while (steps < MAX_STEPS) {
    steps++;
    const atBottom = scrollParent.scrollTop + scrollParent.clientHeight >= scrollParent.scrollHeight - 5;
    if (atBottom) {
      // Settle wait to catch any late-rendering rows, then one final read.
      await wait(400);
      collectVisible();
      const stillAtBottom = scrollParent.scrollTop + scrollParent.clientHeight >= scrollParent.scrollHeight - 5;
      if (stillAtBottom) break;
      continue; // content grew after settling (more rows loaded); keep going
    }
    scrollParent.scrollTop += scrollParent.clientHeight * 0.6; // smaller step = more overlap
    await wait(300);
    collectVisible();
  }

  return [...seen.values()];
}

// ---- Set to true to only process a few notebooks (for testing changes) ----
const TEST_MODE = false;
const TEST_LIMIT = 15;

async function oldestNoteAcrossAllNotebooks() {
  const results = [];
  const skippedNames = [];
  let processedCount = 0;

  await processAllNotebooks(async (nb) => {
    if (TEST_MODE && processedCount >= TEST_LIMIT) return;

    if (shouldSkipNotebook(nb.name, nb.stackName)) {
      skippedNames.push(nb.name);
      return;
    }

    try {
      // Re-find the link fresh right before clicking (it was just seen
      // this exact scroll step, so it should still be rendered).
      const link = document.getElementById(`qa-NAV_NOTEBOOK_${nb.guid}`);
      if (!link) { results.push({ notebook: nb.name, stack: nb.stackName, title: '(link lost)', dateText: '', daysSince: '' }); return; }
      link.click();
      await wait(1000);

      const notes = await collectNotesInCurrentNotebook();
      const candidates = notes
        .filter(n => !n.pinned)
        .map(n => ({ ...n, parsed: parseNoteDate(n.dateText) }))
        .filter(n => n.parsed);

      if (candidates.length === 0) {
        results.push({ notebook: nb.name, stack: nb.stackName, title: notes.length ? '(only pinned notes?)' : '(empty)', dateText: '', daysSince: '' });
        processedCount++;
        return;
      }
      candidates.sort((a, b) => a.parsed - b.parsed);
      const oldest = candidates[0];
      const daysSince = Math.round((Date.now() - oldest.parsed.getTime()) / 86400000);
      results.push({ notebook: nb.name, stack: nb.stackName, title: oldest.title, dateText: oldest.dateText, daysSince });
      processedCount++;
      console.log(`${nb.name} -> ${oldest.title} (${oldest.dateText})`);
    } catch (err) {
      logError(`Notebook "${nb.name}"`, err);
      results.push({ notebook: nb.name, stack: nb.stackName, title: '(ERROR -- see error log)', dateText: '', daysSince: '' });
      processedCount++;
    }
  });

  console.log(`Skipped ${skippedNames.length}: ${skippedNames.join(', ')}`);

  // Build CSV and trigger a download -- sorted most-stale first so the
  // notebooks most in need of review float to the top.
  const escapeCsv = (val) => {
    const s = String(val ?? '');
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const sortedResults = [...results].sort((a, b) => {
    const da = typeof a.daysSince === 'number' ? a.daysSince : -1;
    const db = typeof b.daysSince === 'number' ? b.daysSince : -1;
    return db - da;
  });
  const header = 'Stack,Notebook,Oldest Note Title,Last Updated,Days Since Updated';
  const csvRows = sortedResults.map(r =>
    [r.stack, r.notebook, r.title, r.dateText, r.daysSince].map(escapeCsv).join(',')
  );
  const csv = [header, ...csvRows].join('\n');
  downloadTextFile(`evernote_oldest_notes_${new Date().toISOString().slice(0, 10)}.csv`, csv);

  // Always download an error log too, even if empty, so it's easy to
  // confirm at a glance whether anything went wrong during the run.
  const errorLogContent = scriptErrors.length
    ? scriptErrors.join('\n\n')
    : 'No errors recorded during this run.';
  downloadTextFile(`evernote_scan_errors_${new Date().toISOString().slice(0, 10)}.txt`, errorLogContent);

  console.log(`Done. Downloaded CSV with ${results.length} notebooks. ${scriptErrors.length} error(s) logged.`);
  console.table(results);
  return results;
}

(async () => {
  try {
    await oldestNoteAcrossAllNotebooks();
  } catch (err) {
    logError('Top-level run', err);
    downloadTextFile(`evernote_scan_errors_${new Date().toISOString().slice(0, 10)}.txt`, scriptErrors.join('\n\n'));
    console.error('Run failed -- error log downloaded. See details above.');
  }
})();