---
name: Incorrect or incomplete coverage result
about: A small sanitized reproduction of an unexpected verdict
---

## Expected and observed result

## Versions
BackupScope, Python, OS, restic, Docker; Linux or native Windows containers?

## Minimal sanitized reproduction
Include only redacted mount inventory, policy and a small synthetic listing.
Do not attach secrets, backup contents or full docker inspect output.

## Checks already performed
Did the unfiltered restic export exit 0? Does its hostname/tag identify the
intended snapshot? What do actual restore or integrity checks show?
