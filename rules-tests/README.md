# rules-tests

~50 lines of Node against `../firestore.rules` using
`@firebase/rules-unit-testing` (Node-only — the one real cost of Python, §10).

Must cover: a signed-in non-admin is denied every read, and an admin is allowed.
