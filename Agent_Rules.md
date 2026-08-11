## Agent Rules

### Response Delivery
- Each step should start with a non-verbose statement including basic info, reason for change, new code intent
- Provide exact inline PRE/POST for every changed existing production or runtime system file. Use the exact user-supplied commit as the only PRE source. If any PRE block does not exist exactly, stop and report the mismatch instead of guessing or adapting older code.
- Deliver new files and non-system files—including roadmaps, documentation, reports, tests, and other support artifacts—as a downloadable ZIP that preserves repository-relative paths. Do not place existing system files in that ZIP unless explicitly requested.
- After every PRE/POST delivery, provide only the applicable post-application instructions: data migration, tests, restart, and runtime verification. Assume every download/new file and every POST block has already been applied; do not include extraction or pre-application verification commands. Do not provide terminal commit commands. Never write to GitHub unless the user explicitly authorizes that specific write.

### BS Avoidance
- Assert before starting when a request is too large for one reliable pass, ambiguous in a way that changes the result, blocked by an unmet dependency, destructive or security-sensitive, or requires a material user choice. State the issue and propose the smallest responsible block before doing work.