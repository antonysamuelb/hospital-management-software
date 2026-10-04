# Searching for a patient — verified

This is the original requirement the whole project started from: *"I should
be able to query patient details using patient id or phone number."*
Verified directly against the live `deploy/dev/` instance.

Not running yet? See [`deploy/dev/README.md`](../README.md#starting-it) for
how to start the stack first.

## Short answer: yes, both work, from the same search box

1. Left menu → **Health → Patients**.
2. Click into the **FILTERS Search** box above the patient list.
3. Type either the **phone number** or the **PUID** (patient ID).
4. Press **Enter**, or click the magnifying-glass icon.

The list filters down to matching patients immediately.

## What was actually tested

| Search term | Example | Result |
|---|---|---|
| Full phone number | `9123456780` | Filtered to exactly the matching patient |
| **Partial** phone number (last 4 digits) | `6780` | Still correctly filtered to the matching patient — it's a substring match, not an exact-match-only field. Useful since staff may only recall part of a number. |
| PUID (patient ID) | `GUX953CGG` | Filtered to exactly the matching patient |

So in practice, reception/nursing staff can type whatever they have — a
full or partial phone number, or the PUID — into the one search box on the
Patients list, no need to know which field they're matching against.

## One UI quirk: clearing the search

Deleting the text in the search box and pressing **Enter** does **not**
reliably bring back the full list — the filter can stay stuck showing only
the last match. **Click the magnifying-glass search icon** (next to the box)
with the field empty to actually reset to the full patient list.

## Searching by name

Not the focus of the original requirement, but worth noting: the same
search box also matches on patient name (typing part of "Ramesh Kumar"
filters correctly too) — it's a general-purpose quick search, not
phone/PUID-specific.
