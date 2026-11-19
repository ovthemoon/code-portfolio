// Excerpt. Not runnable: browser form code of the wall page (DOM ids, layout and
// styling left out). The request id is what the server treats as "the same submission".
// Names used below but defined elsewhere: form, dialog, textInput, nameInput, submitButton,
// writeStatus, postNote and fetchSnapshot (fetch wrappers), apply (renders a snapshot), updateCount.

let requestId = crypto.randomUUID();   // issued when the page is opened
let busy = false;

// Any edit makes it a different submission, so it gets a new id.
form.addEventListener('input', () => {
  updateCount();
  requestId = crypto.randomUUID();
  writeStatus.textContent = '';
});

form.addEventListener('submit', async event => {
  event.preventDefault();
  if (busy) return;                    // one submission in flight at a time
  if (!form.reportValidity()) return;

  busy = true;
  submitButton.disabled = true;
  for (const field of form.querySelectorAll('input,textarea,select')) field.readOnly = true;

  const payload = { requestId, text: textInput.value, name: nameInput.value };
  try {
    const data = await postNote(payload);
    apply(data);
    dialog.close();
    form.reset();
    requestId = crypto.randomUUID();   // it went through: the next submission is a new one
  } catch (error) {
    // The draft and the same requestId are kept. Pressing again re-sends the same
    // submission, which the server recognises if the first attempt did go through.
    writeStatus.textContent = error.message;
    if (error.status === 409) {
      try { apply(await fetchSnapshot()); } catch { /* keep the original error and the draft */ }
    }
  } finally {
    busy = false;
    submitButton.disabled = false;
    for (const field of form.querySelectorAll('input,textarea,select')) field.readOnly = false;
  }
});
