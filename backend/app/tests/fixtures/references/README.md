# Reference-source fixtures (T17)

Synthetic pages in the publishers' HTML structure, written for the tests. The build
environment has no outbound network, so nothing here was fetched from CDC, WHO or NCBI,
and the wording is NOT the publishers' text. The figures follow the public schedules
closely enough for the tests to be readable, but must not be cited.

- `cdc_child_schedule.html`, `cdc_measles_vaccine.html`, `fda_caffeine.html`: catalogue pages.
- `books_esearch.json`, `books_esummary.json`, `NBK000001.html`: an NCBI Bookshelf search
  (E-utilities `db=books`) and the chapter page it points to.

To replace them with recordings, fetch the catalogue URLs in
`config/reference_sources.yaml` from a machine with network access and save the HTML
under the same names (context/MULTI_AGENT.md §7n).
