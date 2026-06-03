---
name: Web job card cover letter + inline edits
overview: "Job card cover letter (GPT-5.5), editable pane, Save, Download .txt; inline status/notes."
status: done
---

## Mission

Job detail card (`/jobs/{job_id}`): generate cover letter from résumé + job, edit in browser,
save, download `.txt`; edit status and notes without returning to the list.

## Locked decisions

- Model: `AGENTZERO_COVER_LETTER_MODEL` default `gpt-5.5` (OpenAI only)
- Storage: `output/cover_letters/{job_id}.txt`
- UI: editable textarea, Save, Download, Generate with overwrite confirm

## Task ledger

| Id | Outcome |
|----|---------|
| T01 | `agentzero/generate/cover_letter.py` + config + tests |
| T02 | Job card status/notes/reject with `return_to=detail` |
| T03 | `CoverLetterRunner` + API/download/save routes |
| T04 | `job_card.html` cover letter section |
| T05 | Docs + `.env.example` |
| T06 | PROGRESS + WORKLOG |
